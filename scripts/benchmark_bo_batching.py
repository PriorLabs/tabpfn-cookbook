"""Measure BO inference batching, cache precision, and packed attention on CUDA."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import statistics
import time
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any, Callable, Iterator

import numpy as np
import torch
from botorch.test_functions import Hartmann
from tabpfn import TabPFNRegressor
from tabpfn.inference import _batch_member_inputs
from tabpfn.settings import settings
from tabpfn_extensions.bayesian_optimization.bo import _aligned, _ei_no_grad


def emit(**row: Any) -> None:
    print(json.dumps(row, allow_nan=False), flush=True)


def measure(call: Callable[[], Any], repeats: int) -> tuple[Any, dict[str, Any]]:
    call()
    torch.cuda.synchronize()
    torch.cuda.reset_peak_memory_stats()
    samples = []
    for _ in range(repeats):
        torch.cuda.synchronize()
        start = time.perf_counter()
        result = call()
        torch.cuda.synchronize()
        samples.append(1000 * (time.perf_counter() - start))
    return result, {
        "median_ms": statistics.median(samples),
        "samples_ms": samples,
        "peak_allocated_mb": torch.cuda.max_memory_allocated() / 2**20,
    }


def agreement(actual: torch.Tensor, expected: torch.Tensor) -> dict[str, Any]:
    a, b = actual.float().cpu(), expected.float().cpu()
    if not torch.isfinite(a).all() or not torch.isfinite(b).all():
        raise ValueError("Nonfinite predictions")
    delta = (a - b).abs()
    return {
        "max_abs_error": delta.max().item(),
        "relative_l2_error": (delta.norm() / b.norm().clamp_min(1e-20)).item(),
        "allclose_rtol_1e-3_atol_1e-5": torch.allclose(a, b, rtol=1e-3, atol=1e-5),
    }


@contextmanager
def estimator_batching(enabled: bool) -> Iterator[None]:
    previous = settings.tabpfn.max_batched_estimator_rows
    settings.tabpfn.max_batched_estimator_rows = None if enabled else 0
    try:
        yield
    finally:
        settings.tabpfn.max_batched_estimator_rows = previous


def regressor(checkpoint: Path, mode: str, precision: str | None) -> TabPFNRegressor:
    return TabPFNRegressor(
        model_path=checkpoint,
        n_estimators=8,
        device="cuda",
        random_state=0,
        fit_mode=mode,
        kv_cache_precision=precision,
        inference_config={"FINGERPRINT_FEATURE": False},
    )


def dataset(
    n_train: int, n_test: int, seed: int
) -> tuple[np.ndarray, np.ndarray, torch.Tensor]:
    points = torch.quasirandom.SobolEngine(6, scramble=True, seed=seed).draw(
        n_train + n_test
    )
    x, candidates = points[:n_train], points[n_train:]
    return x.numpy(), Hartmann(dim=6, negate=True)(x).numpy(), candidates


def cache_and_ensemble(args: argparse.Namespace) -> None:
    configs = [
        ("serial_estimators", "fit_preprocessors", None, False),
        ("batched_estimators", "fit_preprocessors", None, True),
        ("cache_unquantized", "fit_with_cache", "auto", True),
        ("cache_default", "fit_with_cache", None, True),
    ]
    for n_train in (20, 50):
        references: dict[int, torch.Tensor] = {}
        for name, mode, precision, batching in configs:
            with estimator_batching(batching):
                reg = regressor(args.checkpoint, mode, precision)
                x, y, _ = dataset(n_train, 1, 0)
                _, fit_timing = measure(partial(reg.fit, x, y), args.repeats)
                emit(section="fit", config=name, n_train=n_train, **fit_timing)
                for n_test in (104, 512, 1024):
                    _, _, candidates = dataset(n_train, n_test, 1)
                    ei, timing = measure(
                        partial(_ei_no_grad, reg, candidates, float(y.max())),
                        args.repeats,
                    )
                    if name == "serial_estimators":
                        references[n_test] = ei.clone()
                    reference = references[n_test]
                    selected = int(ei.argmax())
                    emit(
                        section="predict_ei",
                        config=name,
                        n_train=n_train,
                        n_test=n_test,
                        **timing,
                        **agreement(ei, reference),
                        same_argmax=selected == int(reference.argmax()),
                        reference_ei_loss=(
                            reference.max() - reference[selected]
                        ).item(),
                        cache_groups=getattr(reg.executor_, "cache_groups", None),
                    )
                del reg


def dataset_api(args: argparse.Namespace) -> None:
    data = [dataset(50, 104, seed) for seed in range(4)]
    xs, ys, candidates = zip(*data)
    tests = [x.numpy() for x in candidates]
    reg = regressor(args.checkpoint, "fit_preprocessors", None)

    def sequential() -> list[Any]:
        outputs = []
        for x, y, test in zip(xs, ys, tests):
            reg.fit(x, y)
            outputs.append(reg.predict(test, output_type="full"))
        return outputs

    with estimator_batching(True):
        reference, serial_timing = measure(sequential, args.repeats)
        results, batch_timing = measure(
            lambda: reg.predict_batched(list(xs), list(ys), tests, output_type="full"),
            args.repeats,
        )
    emit(
        section="dataset_api",
        config="sequential_fit_predict",
        datasets=4,
        **serial_timing,
    )
    for index, (result, expected) in enumerate(zip(results, reference)):
        logits, bardist = _aligned(result)
        ref_logits, ref_bardist = _aligned(expected)
        best = float(ys[index].max())
        ei = bardist.ei(logits, best, maximize=True)
        ref_ei = ref_bardist.ei(ref_logits, best, maximize=True)
        emit(
            section="dataset_api_agreement",
            dataset=index,
            **agreement(ei, ref_ei),
            same_argmax=int(ei.argmax()) == int(ref_ei.argmax()),
        )
    emit(
        section="dataset_api", config="batched_fit_predict", datasets=4, **batch_timing
    )


@dataclass
class Forward:
    model: torch.nn.Module
    x: torch.Tensor
    y: torch.Tensor
    kwargs: dict[str, Any]

    def run(self) -> torch.Tensor:
        with torch.inference_mode(), torch.autocast("cuda", dtype=torch.float16):
            return self.model(self.x, self.y, **self.kwargs)


def capture(reg: TabPFNRegressor, candidates: torch.Tensor) -> list[Forward]:
    calls: list[Forward] = []

    def record(
        model: torch.nn.Module,
        inputs: tuple[Any, ...],
        kwargs: dict[str, Any],
        output: Any,
    ) -> None:
        calls.append(Forward(model, inputs[0].clone(), inputs[1].clone(), dict(kwargs)))

    handles = [
        cache.get(torch.device("cuda")).register_forward_hook(record, with_kwargs=True)
        for cache in reg.executor_.model_caches
    ]
    try:
        reg.predict(candidates.numpy(), output_type="full")
    finally:
        for handle in handles:
            handle.remove()
    return calls


def merge(calls: list[Forward]) -> Forward:
    first = calls[0]
    kwargs = dict(first.kwargs)
    kwargs["categorical_inds"] = [
        c for call in calls for c in call.kwargs["categorical_inds"]
    ]
    if "kv_cache" in kwargs:
        # concatenate consumes its input caches; preserve the sequential reference.
        caches = [deepcopy(call.kwargs["kv_cache"]) for call in calls]
        kwargs["kv_cache"] = type(caches[0]).concatenate(caches)
    x, y = _batch_member_inputs([c.x for c in calls], [c.y for c in calls])
    return Forward(first.model, x, y, kwargs)


def run_forwards(calls: list[Forward]) -> list[torch.Tensor]:
    return [call.run() for call in calls]


def forward_batching(args: argparse.Namespace) -> None:
    for mode in ("fit_preprocessors", "fit_with_cache"):
        calls: list[Forward] = []
        regs = []
        with estimator_batching(False):
            for seed in range(4):
                x, y, candidates = dataset(50, 104, seed)
                reg = regressor(args.checkpoint, mode, "auto")
                reg.fit(x, y)
                calls.extend(capture(reg, candidates))
                regs.append(reg)
        groups: dict[tuple[Any, ...], list[int]] = {}
        for index, call in enumerate(calls):
            key = (
                tuple(call.x.shape),
                tuple(call.y.shape),
                repr(call.kwargs["performance_options"]),
            )
            groups.setdefault(key, []).append(index)
        start = time.perf_counter()
        combined = [merge([calls[i] for i in indices]) for indices in groups.values()]
        torch.cuda.synchronize()
        merge_ms = 1000 * (time.perf_counter() - start)
        reference, serial_timing = measure(partial(run_forwards, calls), args.repeats)
        outputs, batch_timing = measure(partial(run_forwards, combined), args.repeats)
        errors = []
        for output, indices in zip(outputs, groups.values()):
            expected = torch.cat([reference[i] for i in indices], dim=1)
            errors.append(agreement(output, expected))
        emit(
            section="prepared_forward",
            config=mode,
            datasets=4,
            sequential=serial_timing,
            batched=batch_timing,
            merge_ms=merge_ms,
            forward_calls=len(calls),
            batched_calls=len(combined),
            batch_sizes=[c.x.shape[1] for c in combined],
            agreement=errors,
        )
        del calls, combined, regs, reg, reference, outputs


def packed_attention(args: argparse.Namespace) -> None:
    from torch.nn.attention.flex_attention import flex_attention

    reg = regressor(args.checkpoint, "fit_with_cache", "auto")
    x, y, candidates = dataset(50, 104, 0)
    reg.fit(x, y)
    reg.predict(candidates.numpy())
    module = next(
        m for m in reg.models_[0].modules() if hasattr(m, "num_kv_heads_test")
    )
    heads = module.num_heads
    kv_heads = module.num_kv_heads_test or module.num_kv_heads
    dim = module.head_dim
    compiled_flex = torch.compile(flex_attention, dynamic=False)
    for n_keys in (20, 50):
        for n_queries in (104, 512, 1024):
            attention_case(
                heads, kv_heads, dim, n_keys, n_queries, compiled_flex, args.repeats
            )


def attention_case(
    heads: int,
    kv_heads: int,
    dim: int,
    n_keys: int,
    n_queries: int,
    compiled_flex: Callable[..., torch.Tensor],
    repeats: int,
) -> None:
    from torch.nn.attention.flex_attention import create_block_mask

    torch.manual_seed(0)
    batch = 4
    q = torch.randn(batch, heads, n_queries, dim, device="cuda", dtype=torch.float16)
    k = torch.randn(batch, kv_heads, n_keys, dim, device="cuda", dtype=torch.float16)
    v = torch.randn_like(k)
    qp = q.transpose(1, 2).reshape(1, batch * n_queries, heads, dim).transpose(1, 2)
    kp = k.transpose(1, 2).reshape(1, batch * n_keys, kv_heads, dim).transpose(1, 2)
    vp = v.transpose(1, 2).reshape(1, batch * n_keys, kv_heads, dim).transpose(1, 2)

    def mask(
        b: torch.Tensor, h: torch.Tensor, qi: torch.Tensor, ki: torch.Tensor
    ) -> torch.Tensor:
        return qi // n_queries == ki // n_keys

    start = time.perf_counter()
    block_mask = create_block_mask(
        mask,
        B=1,
        H=None,
        Q_LEN=batch * n_queries,
        KV_LEN=batch * n_keys,
        device="cuda",
        BLOCK_SIZE=32,
    )
    dense_mask = (
        torch.arange(batch * n_queries, device="cuda")[:, None] // n_queries
        == torch.arange(batch * n_keys, device="cuda")[None, :] // n_keys
    )
    torch.cuda.synchronize()
    mask_ms = 1000 * (time.perf_counter() - start)

    def unpack(output: torch.Tensor) -> torch.Tensor:
        return (
            output.transpose(1, 2).reshape(batch, n_queries, heads, dim).transpose(1, 2)
        )

    def serial() -> torch.Tensor:
        return torch.cat(
            [
                torch.nn.functional.scaled_dot_product_attention(
                    q[i : i + 1], k[i : i + 1], v[i : i + 1], enable_gqa=True
                )
                for i in range(batch)
            ]
        )

    methods = {
        "sequential_sdpa": serial,
        "batched_sdpa": lambda: torch.nn.functional.scaled_dot_product_attention(
            q, k, v, enable_gqa=True
        ),
        "packed_dense_mask": lambda: unpack(
            torch.nn.functional.scaled_dot_product_attention(
                qp, kp, vp, attn_mask=dense_mask, enable_gqa=True
            )
        ),
        "packed_flex_mask": lambda: unpack(
            compiled_flex(qp, kp, vp, block_mask=block_mask, enable_gqa=True)
        ),
    }
    reference = serial()
    for name, call in methods.items():
        start = time.perf_counter()
        call()
        torch.cuda.synchronize()
        first_call_ms = 1000 * (time.perf_counter() - start)
        output, timing = measure(call, max(20, repeats))
        emit(
            section="attention_kernel",
            config=name,
            batch=batch,
            heads=heads,
            kv_heads=kv_heads,
            head_dim=dim,
            n_keys=n_keys,
            n_queries=n_queries,
            first_call_ms=first_call_ms,
            mask_build_ms=mask_ms,
            **timing,
            **agreement(output, reference),
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument(
        "--sections",
        nargs="+",
        choices=["cache", "datasets", "forward", "attention"],
        default=["cache", "datasets", "forward", "attention"],
    )
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be positive")
    torch.set_num_threads(2)
    if not torch.cuda.is_available():
        raise RuntimeError("This benchmark requires CUDA")
    emit(
        section="metadata",
        gpu=torch.cuda.get_device_name(),
        torch=torch.__version__,
        tabpfn=importlib.metadata.version("tabpfn"),
        checkpoint=str(args.checkpoint),
        dataset="Hartmann-6",
        data_seeds=list(range(4)),
        model_seed=0,
        n_estimators=8,
        repeats=args.repeats,
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    )
    sections = {
        "cache": cache_and_ensemble,
        "datasets": dataset_api,
        "forward": forward_batching,
        "attention": packed_attention,
    }
    failures = []
    for name in args.sections:
        try:
            sections[name](args)
        except Exception as error:  # noqa: BLE001 -- save independent sections, then fail the job
            import traceback

            traceback.print_exc()
            failures.append(name)
            emit(section="error", benchmark=name, error=repr(error))
    if failures:
        raise RuntimeError(f"Failed sections: {failures}")
    emit(section="complete")


if __name__ == "__main__":
    main()
