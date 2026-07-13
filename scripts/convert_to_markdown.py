#!/usr/bin/env python3
"""Convert notebooks into Mintlify-ready markdown files.

Author blocks are injected automatically when ``authors`` is set in frontmatter.
For markdown-only recipes, use ``process_markdown.py`` instead.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cookbook_utils import cell_source, process_markdown_content, transform_markdown_for_mintlify

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOKS_DIR = ROOT / "notebooks"
MARKDOWNS_DIR = ROOT / "markdowns"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--all",
        action="store_true",
        help="Convert every notebook in notebooks/.",
    )
    parser.add_argument(
        "--slug",
        help="Convert a single notebook by slug (filename without .ipynb).",
    )
    return parser.parse_args()


def split_frontmatter(text: str) -> tuple[str | None, str]:
    match = re.match(r"^---\r?\n([\s\S]*?)\r?\n---\r?\n?", text.strip())
    if not match:
        return None, text
    return match.group(0).strip(), text[match.end() :].lstrip("\n")


def discover_notebooks(slug: str | None) -> list[Path]:
    if slug:
        path = NOTEBOOKS_DIR / f"{slug}.ipynb"
        if not path.exists():
            raise FileNotFoundError(f"Notebook not found: {path}")
        return [path]

    return sorted(NOTEBOOKS_DIR.glob("*.ipynb"))


def notebook_to_mdx(notebook: dict) -> str:
    body_parts: list[str] = []
    frontmatter: str | None = None
    frontmatter_consumed = False

    for cell in notebook.get("cells", []):
        cell_type = cell.get("cell_type")

        if cell_type == "markdown":
            text = cell_source(cell).strip()
            if not text:
                continue

            if not frontmatter_consumed:
                extracted, remainder = split_frontmatter(text)
                if extracted:
                    frontmatter = extracted
                    frontmatter_consumed = True
                    if remainder.strip():
                        body_parts.append(transform_markdown_for_mintlify(remainder.strip()))
                    continue

            body_parts.append(transform_markdown_for_mintlify(text))
            continue

        if cell_type == "code":
            code = cell_source(cell).rstrip("\n")
            if code:
                body_parts.append(f"```python\n{code}\n```")

    if not frontmatter:
        raise ValueError("missing frontmatter in first markdown cell")

    body = "\n\n".join(body_parts).rstrip()
    if body:
        return f"{frontmatter}\n{body}\n"
    return f"{frontmatter}\n"


def convert_notebook_to_mdx(notebook_path: Path) -> str:
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    return notebook_to_mdx(notebook)


def convert_notebook(notebook_path: Path) -> Path:
    mdx = process_markdown_content(convert_notebook_to_mdx(notebook_path))
    output_path = MARKDOWNS_DIR / f"{notebook_path.stem}.mdx"
    output_path.write_text(mdx, encoding="utf-8")
    return output_path


def main() -> int:
    args = parse_args()
    if not args.all and not args.slug:
        print("Pass --all or --slug <name>", file=sys.stderr)
        return 1

    MARKDOWNS_DIR.mkdir(parents=True, exist_ok=True)

    try:
        notebooks = discover_notebooks(args.slug)
    except FileNotFoundError as error:
        print(error, file=sys.stderr)
        return 1

    errors = 0
    for notebook_path in notebooks:
        try:
            output_path = convert_notebook(notebook_path)
            print(f"Wrote {output_path.relative_to(ROOT)}")
        except ValueError as error:
            print(f"  - {notebook_path.name}: {error}", file=sys.stderr)
            errors += 1

    if errors:
        return 1

    print(f"Converted {len(notebooks) - errors} notebook(s) to {MARKDOWNS_DIR.relative_to(ROOT)}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
