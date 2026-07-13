#!/usr/bin/env python3
"""Validate cookbook notebooks and generated markdown for CI and local use."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from convert_to_markdown import convert_notebook_to_mdx
from cookbook_utils import (
    author_block_is_current,
    parse_mdx_frontmatter,
    process_markdown_content,
    validate_frontmatter,
)

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOKS_DIR = ROOT / "notebooks"
MARKDOWNS_DIR = ROOT / "markdowns"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base",
        help="Git ref to compare against (default: auto-detect in CI, else HEAD).",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Validate every markdown file and require all notebooks to be converted.",
    )
    return parser.parse_args()


def run_git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def resolve_base_ref(explicit_base: str | None) -> str | None:
    if explicit_base:
        return explicit_base

    for env_var in ("GITHUB_BASE_REF", "GITHUB_EVENT_BEFORE"):
        value = __import__("os").environ.get(env_var)
        if value and value != "0000000000000000000000000000000000000000":
            if env_var == "GITHUB_BASE_REF":
                fetch = run_git("fetch", "origin", value, "--depth=1")
                if fetch.returncode == 0:
                    return f"origin/{value}"
            return value

    head = run_git("rev-parse", "HEAD")
    if head.returncode != 0:
        return None

    merge_base = run_git("merge-base", "HEAD", "origin/main")
    if merge_base.returncode == 0 and merge_base.stdout.strip():
        return merge_base.stdout.strip()

    parent = run_git("rev-parse", "HEAD~1")
    if parent.returncode == 0:
        return parent.stdout.strip()

    return None


def changed_files(base_ref: str | None) -> set[str]:
    if base_ref is None:
        notebooks = {f"notebooks/{path.name}" for path in NOTEBOOKS_DIR.glob("*.ipynb")}
        markdowns = {f"markdowns/{path.name}" for path in MARKDOWNS_DIR.glob("*.mdx")}
        return notebooks | markdowns

    diff = run_git("diff", "--name-only", f"{base_ref}...HEAD")
    if diff.returncode != 0:
        diff = run_git("diff", "--name-only", base_ref, "HEAD")
    if diff.returncode != 0:
        return set()

    return {line.strip() for line in diff.stdout.splitlines() if line.strip()}


def markdown_paths_from_changes(changed: set[str]) -> list[Path]:
    paths: set[Path] = set()

    for name in changed:
        if name.startswith("markdowns/") and name.endswith(".mdx"):
            paths.add(ROOT / name)
        if name.startswith("notebooks/") and name.endswith(".ipynb"):
            paths.add(MARKDOWNS_DIR / f"{Path(name).stem}.mdx")

    return sorted(path for path in paths if path.exists())


def all_markdown_paths() -> list[Path]:
    return sorted(MARKDOWNS_DIR.glob("*.mdx"))


def check_notebooks_converted() -> bool:
    stale: list[str] = []

    for notebook_path in sorted(NOTEBOOKS_DIR.glob("*.ipynb")):
        markdown_name = f"{notebook_path.stem}.mdx"
        markdown_path = MARKDOWNS_DIR / markdown_name

        try:
            expected = process_markdown_content(convert_notebook_to_mdx(notebook_path))
        except ValueError as error:
            print(f"{notebook_path.name}: {error}", file=sys.stderr)
            return False

        if not markdown_path.exists():
            stale.append(markdown_name)
            continue

        actual = markdown_path.read_text(encoding="utf-8")
        if actual != expected:
            stale.append(markdown_name)

    if not stale:
        return True

    print(
        "Generated markdown is out of date.\n"
        "Run: python3 scripts/convert_to_markdown.py --all\n"
        "Then commit the updated files under markdowns/.",
        file=sys.stderr,
    )
    for name in stale:
        print(f"  - markdowns/{name}", file=sys.stderr)

    return False


def validate_markdown_files(paths: list[Path]) -> bool:
    ok = True

    for path in paths:
        label = path.relative_to(ROOT).as_posix()
        content = path.read_text(encoding="utf-8")
        try:
            frontmatter = parse_mdx_frontmatter(path)
        except ValueError as error:
            print(f"{label}: {error}", file=sys.stderr)
            ok = False
            continue

        for error in validate_frontmatter(frontmatter, source=label):
            print(error, file=sys.stderr)
            ok = False

        has_notebook = (NOTEBOOKS_DIR / f"{path.stem}.ipynb").exists()
        for error in author_block_is_current(content, source=label, has_notebook=has_notebook):
            print(error, file=sys.stderr)
            ok = False

    return ok


def main() -> int:
    args = parse_args()
    base_ref = None if args.all else resolve_base_ref(args.base)
    changed = changed_files(base_ref)

    notebook_changes = [
        name for name in changed if name.startswith("notebooks/") and name.endswith(".ipynb")
    ]
    markdown_changes = [
        name for name in changed if name.startswith("markdowns/") and name.endswith(".mdx")
    ]

    ok = True

    if args.all:
        if not check_notebooks_converted():
            ok = False
        if not validate_markdown_files(all_markdown_paths()):
            ok = False
        if ok:
            print("Cookbook validation passed.")
        return 0 if ok else 1

    if notebook_changes:
        print(
            "Notebook changes detected; checking generated markdown is up to date:\n"
            + "\n".join(f"  - {name}" for name in notebook_changes)
        )
        if not check_notebooks_converted():
            ok = False

    markdown_paths = markdown_paths_from_changes(changed)
    if markdown_changes and not notebook_changes:
        print(
            "Markdown-only changes detected; validating frontmatter:\n"
            + "\n".join(f"  - {name}" for name in markdown_changes)
        )
    elif markdown_paths and notebook_changes:
        print("Validating frontmatter for affected markdown files.")

    if markdown_paths and not validate_markdown_files(markdown_paths):
        ok = False

    if not notebook_changes and not markdown_changes:
        print("No cookbook notebook or markdown changes detected; skipping checks.")
        return 0

    if ok:
        print("Cookbook validation passed.")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
