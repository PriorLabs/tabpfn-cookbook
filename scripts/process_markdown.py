#!/usr/bin/env python3
"""Inject or refresh Mintlify author / Colab blocks in markdown files.

Use this for markdown-only recipes (no matching notebook). Notebook recipes
get these blocks automatically from ``convert_to_markdown.py``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cookbook_utils import discover_slug_paths, process_markdown_content

ROOT = Path(__file__).resolve().parents[1]
MARKDOWNS_DIR = ROOT / "markdowns"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--all",
        action="store_true",
        help="Process every markdown file in markdowns/.",
    )
    parser.add_argument(
        "--slug",
        help="Process a single markdown file by slug (filename without .mdx).",
    )
    return parser.parse_args()


def process_file(path: Path) -> bool:
    original = path.read_text(encoding="utf-8")
    updated = process_markdown_content(original)
    if updated == original:
        return False

    path.write_text(updated, encoding="utf-8")
    return True


def main() -> int:
    args = parse_args()
    if not args.all and not args.slug:
        print("Pass --all or --slug <name>", file=sys.stderr)
        return 1

    try:
        paths = discover_slug_paths(
            MARKDOWNS_DIR, extension=".mdx", slug=args.slug, label="markdown file"
        )
    except FileNotFoundError as error:
        print(error, file=sys.stderr)
        return 1

    changed = 0
    for path in paths:
        if process_file(path):
            changed += 1
            print(f"Updated {path.relative_to(ROOT)}")

    if changed == 0:
        print("No markdown files needed processing.")
    else:
        print(f"Processed {changed} markdown file(s).")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
