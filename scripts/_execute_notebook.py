#!/usr/bin/env python3
"""Execute one notebook in place. Runs inside the env that rerun_notebooks.py builds.

Only ``nbclient`` and ``nbformat`` are imported here, so this script must run
with the notebook's own packages installed; ``rerun_notebooks.py`` takes care
of that. Cells passed via ``--skip-cell`` are not executed and lose their
outputs. Notebook-level metadata is kept exactly as it was so the diff is
limited to cell outputs and execution counts.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
import time
from pathlib import Path

import nbformat
from nbclient import NotebookClient
from nbclient.exceptions import CellExecutionError, CellTimeoutError, DeadKernelError
from nbformat.v4.nbjson import JSONReader
from nbformat.v4.rwbase import split_lines, strip_transient

SKIP_TAG = "skip-execution"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("notebook", type=Path)
    parser.add_argument("--timeout", type=int, default=3600, help="Per-cell timeout in seconds.")
    parser.add_argument("--skip-cell", type=int, action="append", default=[], help="Cell index to skip (repeatable).")
    parser.add_argument("--failed-copy", type=Path, help="Where to write the partially executed notebook on failure.")
    return parser.parse_args()


def detect_indent(text: str) -> int:
    """Indentation of the notebook JSON: Jupyter writes 1 space, Colab exports 2."""
    match = re.search(r'\n( +)"', text)
    return len(match.group(1)) if match else 1


def write_notebook(path: Path, notebook: nbformat.NotebookNode, indent: int) -> None:
    # Same layout as nbformat's JSONWriter (sorted keys, split lines) without
    # running validation, which would add cell ids, and with the file's own
    # indentation so the diff is limited to the executed cells.
    prepared = strip_transient(split_lines(copy.deepcopy(notebook)))
    text = json.dumps(prepared, sort_keys=True, indent=indent, separators=(",", ": "), ensure_ascii=False)
    path.write_text(text + "\n", encoding="utf-8")


def coalesce_streams(outputs: list) -> list:
    """Merge adjacent stream outputs and apply carriage returns, as notebook UIs do.

    nbclient stores every stream write separately, so a spinner that redraws its
    line with ``\\r`` leaves dozens of one-line outputs. Jupyter and Colab merge
    those and keep only the last redraw, so the saved notebook should too.
    """
    merged: list = []
    for output in outputs:
        if (
            output.get("output_type") == "stream"
            and merged
            and merged[-1].get("output_type") == "stream"
            and merged[-1].get("name") == output.get("name")
        ):
            merged[-1]["text"] += output["text"]
        else:
            merged.append(output)
    for output in merged:
        if output.get("output_type") != "stream" or "\r" not in output["text"]:
            continue
        lines = []
        for line in output["text"].split("\n"):
            lines.append(line.rsplit("\r", 1)[-1] if "\r" in line else line)
        output["text"] = "\n".join(lines)
    return merged


def main() -> int:
    args = parse_args()
    # JSONReader joins multi-line sources without validating, so cells keep
    # their ids (or lack of them) exactly as on disk.
    text = args.notebook.read_text(encoding="utf-8")
    indent = detect_indent(text)
    notebook = JSONReader().reads(text)
    original_metadata = copy.deepcopy(notebook.metadata)
    cells = notebook.cells

    skipped: list[tuple[int, list[str] | None]] = []
    for index in args.skip_cell:
        cell = cells[index]
        tags = cell.metadata.get("tags")
        skipped.append((index, copy.deepcopy(tags)))
        cell.metadata["tags"] = [*(tags or []), SKIP_TAG]

    code_cells = sum(1 for cell in cells if cell.cell_type == "code")
    started = time.monotonic()
    last = [started]

    def report_progress(cell, cell_index, execute_reply=None, **_):
        now = time.monotonic()
        first_line = cell.source.strip().splitlines()[0] if cell.source.strip() else ""
        done = sum(1 for c in cells[: cell_index + 1] if c.cell_type == "code")
        print(
            f"[{args.notebook.stem}] cell {done}/{code_cells} done in {now - last[0]:.0f}s "
            f"(total {now - started:.0f}s): {first_line[:70]}",
            file=sys.stderr,
            flush=True,
        )
        last[0] = now

    client = NotebookClient(
        notebook,
        timeout=args.timeout,
        kernel_name="python3",
        record_timing=False,
        resources={"metadata": {"path": str(args.notebook.parent)}},
        on_cell_executed=report_progress,
    )
    failure: Exception | None = None
    try:
        client.execute()
    except (CellExecutionError, CellTimeoutError, DeadKernelError) as error:
        # A raising cell, a cell over the timeout, or a kernel that died: keep
        # the outputs gathered so far in the failed copy either way.
        failure = error

    for index, tags in skipped:
        cell = cells[index]
        if tags is None:
            cell.metadata.pop("tags", None)
        else:
            cell.metadata["tags"] = tags
        cell.outputs = []
        cell.execution_count = None
    for cell in cells:
        if cell.cell_type == "code":
            cell.metadata.pop("execution", None)
            cell.outputs = coalesce_streams(cell.outputs)
    notebook.metadata = original_metadata

    if failure is not None:
        if args.failed_copy:
            args.failed_copy.parent.mkdir(parents=True, exist_ok=True)
            write_notebook(args.failed_copy, notebook, indent)
            print(f"Partially executed notebook written to {args.failed_copy}", file=sys.stderr)
        print(str(failure), file=sys.stderr)
        return 1

    write_notebook(args.notebook, notebook, indent)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
