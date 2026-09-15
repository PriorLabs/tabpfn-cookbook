#!/usr/bin/env python3
"""Re-execute cookbook notebooks headlessly and refresh their saved outputs.

Each notebook runs in its own ephemeral ``uv run`` environment built from the
``pip install`` lines in the notebook itself, so the packages match what a
Colab user gets. Cells that only run ``pip install`` are skipped during
execution (their packages are already installed) and their outputs cleared.
The notebook is rewritten in place with fresh outputs, then converted to MDX
unless ``--no-convert`` is given.

Notebooks read the API token through ``google.colab.userdata``. Outside Colab
that module does not exist, so ``scripts/colab_shim`` is put on ``PYTHONPATH``
and resolves ``userdata.get(name)`` to the environment variable of the same
name. Set ``TABPFN_TOKEN`` before running.

Model overrides pass straight through the environment, for example
``TABPFN_CLIENT_API_URL`` for a staging API or ``TABPFN_MODEL_CACHE_DIR`` for
local weights. Revert any code-level override before committing so the
published notebook keeps the default constructor.

Examples::

    uv run python scripts/rerun_notebooks.py                 # model-dependent set
    uv run python scripts/rerun_notebooks.py --slug quickstart
    uv run python scripts/rerun_notebooks.py --all --skip pretrain_nanotabpfn
"""

from __future__ import annotations

import argparse
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cookbook_utils import cell_source, discover_slug_paths, is_command_cell

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOKS_DIR = ROOT / "notebooks"
SCRIPTS_DIR = ROOT / "scripts"
COLAB_SHIM_DIR = SCRIPTS_DIR / "colab_shim"
EXECUTOR = SCRIPTS_DIR / "_execute_notebook.py"
WORK_DIR = ROOT / ".rerun"

# Notebooks whose saved outputs come from a TabPFN model (hosted API or the
# local ``tabpfn`` package) and therefore change with every model release.
# The remaining notebooks train their own model or use a separate stack.
MODEL_DEPENDENT_SLUGS = (
    "quickstart",
    "insurance_claim_modeling",
    "predictive_distribution",
    "tabpfn_vs_xgboost",
    "experiment_with_thinking_mode",
    "generate_synthetic_data",
    "faster_performance_with_cache",
    "forecast_spare_parts_demand",
    "bayesian_optimization",
    "interpret_results",
    "decoder_readout",
)
# Not in the list: time_series_interpretability. tabpfn-time-series loads its
# own time-series checkpoint, so the default model release does not affect it.

# Packages the in-kernel executor needs on top of the notebook's own. Colab
# ships ipywidgets, so tqdm and friends expect it. Nothing else is added on
# purpose: a notebook that imports a package its install line does not list
# should fail here, because it also fails for anyone running it outside Colab.
EXECUTOR_PACKAGES = ("nbclient>=0.10", "nbformat>=5.10", "ipykernel>=6.29", "ipywidgets>=8")

PIP_INSTALL_RE = re.compile(r"pip3?\s+install\s+(.*)$")
PIP_FLAGS_WITH_VALUE = {"-i", "--index-url", "--extra-index-url", "-f", "--find-links", "-r", "--requirement"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--slug", action="append", help="Notebook slug to run (repeatable).")
    selection.add_argument("--all", action="store_true", help="Run every notebook under notebooks/.")
    parser.add_argument("--skip", action="append", default=[], help="Slug to leave out (repeatable).")
    parser.add_argument("--python", default="3.12", help="Python version for the ephemeral env (default: 3.12, Colab's).")
    parser.add_argument("--with", dest="extra_with", action="append", default=[], help="Extra package spec for every env (repeatable).")
    parser.add_argument("--timeout", type=int, default=3600, help="Per-cell timeout in seconds (default: 3600).")
    parser.add_argument("--no-convert", action="store_true", help="Do not run convert_to_markdown.py afterwards.")
    parser.add_argument("--keep-going", action="store_true", help="Continue with the next notebook after a failure.")
    parser.add_argument("--dry-run", action="store_true", help="Print the commands without executing anything.")
    return parser.parse_args()


def pip_requirements(notebook_path: Path) -> list[str]:
    """Package specs from every ``pip install`` line in the notebook, in order."""
    import json

    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    specs: list[str] = []
    for cell in notebook.get("cells", []):
        if cell.get("cell_type") != "code":
            continue
        for line in cell_source(cell).splitlines():
            match = PIP_INSTALL_RE.search(line.strip())
            if not match:
                continue
            tokens = shlex.split(match.group(1))
            skip_next = False
            for token in tokens:
                if skip_next:
                    skip_next = False
                    continue
                if token in PIP_FLAGS_WITH_VALUE:
                    skip_next = True
                    continue
                if token.startswith("-"):
                    continue
                if token not in specs:
                    specs.append(token)
    return specs


def pip_only_cell_indices(notebook_path: Path) -> list[int]:
    """Indices of code cells made up entirely of ``!``/``%`` commands that install packages."""
    import json

    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    indices = []
    for index, cell in enumerate(notebook.get("cells", [])):
        if cell.get("cell_type") != "code":
            continue
        source = cell_source(cell)
        if is_command_cell(source) and "pip install" in source:
            indices.append(index)
    return indices


def build_command(notebook_path: Path, args: argparse.Namespace) -> list[str]:
    # A user-level `exclude-newer` in uv.toml would silently hide a TabPFN
    # release from the last few days, which is exactly when reruns happen.
    # Pin the cutoff to now so the freshest packages resolve, like on Colab.
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    command = ["uv", "run", "--no-project", "--refresh", "--exclude-newer", now, "--python", args.python]
    for spec in [*pip_requirements(notebook_path), *args.extra_with, *EXECUTOR_PACKAGES]:
        command += ["--with", spec]
    command += ["python", str(EXECUTOR), str(notebook_path), "--timeout", str(args.timeout)]
    for index in pip_only_cell_indices(notebook_path):
        command += ["--skip-cell", str(index)]
    command += ["--failed-copy", str(WORK_DIR / f"{notebook_path.stem}.failed.ipynb")]
    return command


def kernel_environment() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(COLAB_SHIM_DIR), env.get("PYTHONPATH", "")) if part
    )
    # Never open a browser for the tabpfn login flow on a headless run.
    env.setdefault("TABPFN_NO_BROWSER", "1")
    return env


def run_notebook(notebook_path: Path, args: argparse.Namespace) -> bool:
    command = build_command(notebook_path, args)
    print(f"\n=== {notebook_path.name}")
    print("    " + " ".join(shlex.quote(part) for part in command))
    if args.dry_run:
        return True
    started = time.monotonic()
    result = subprocess.run(command, cwd=NOTEBOOKS_DIR, env=kernel_environment())
    elapsed = time.monotonic() - started
    if result.returncode != 0:
        print(f"    FAILED after {elapsed:.0f}s (exit {result.returncode})", file=sys.stderr)
        return False
    print(f"    done in {elapsed:.0f}s")
    if not args.no_convert:
        convert = ["uv", "run", "python", str(SCRIPTS_DIR / "convert_to_markdown.py"), "--slug", notebook_path.stem]
        if subprocess.run(convert, cwd=ROOT).returncode != 0:
            print("    convert_to_markdown.py failed", file=sys.stderr)
            return False
    return True


def main() -> int:
    args = parse_args()
    if shutil.which("uv") is None:
        print("uv is required: https://docs.astral.sh/uv/", file=sys.stderr)
        return 1
    if not os.environ.get("TABPFN_TOKEN") and not args.dry_run:
        print("Warning: TABPFN_TOKEN is not set; hosted-API notebooks will fail to authenticate.", file=sys.stderr)

    if args.all:
        paths = discover_slug_paths(NOTEBOOKS_DIR, extension=".ipynb", label="notebook")
    elif args.slug:
        paths = [
            path
            for slug in args.slug
            for path in discover_slug_paths(NOTEBOOKS_DIR, extension=".ipynb", slug=slug, label="notebook")
        ]
    else:
        paths = [NOTEBOOKS_DIR / f"{slug}.ipynb" for slug in MODEL_DEPENDENT_SLUGS]
    paths = [path for path in paths if path.stem not in set(args.skip)]
    missing = [path.name for path in paths if not path.exists()]
    if missing:
        print(f"Missing notebooks: {', '.join(missing)}", file=sys.stderr)
        return 1

    WORK_DIR.mkdir(exist_ok=True)
    failures: list[str] = []
    for path in paths:
        if not run_notebook(path, args):
            failures.append(path.name)
            if not args.keep_going:
                break

    print()
    if failures:
        print(f"Failed: {', '.join(failures)}", file=sys.stderr)
        print(f"Partially executed copies are under {WORK_DIR.relative_to(ROOT)}/", file=sys.stderr)
        return 1
    if not args.dry_run:
        print(f"Re-executed {len(paths)} notebook(s). Review the diff, then run: uv run python scripts/validate.py --all")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
