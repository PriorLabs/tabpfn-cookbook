#!/usr/bin/env python3
"""Convert notebooks into Mintlify-ready markdown files.

Author blocks and Colab buttons are injected automatically from frontmatter.
For markdown-only recipes, use ``process_markdown.py`` instead.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cookbook_utils import (
    cell_source,
    discover_slug_paths,
    ensure_colab_url,
    extract_cell_output,
    process_markdown_content,
    render_output_block,
    transform_markdown_for_mintlify,
    try_split_frontmatter,
)

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
                extracted, remainder = try_split_frontmatter(text)
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
                output_text = extract_cell_output(cell)
                if output_text:
                    body_parts.append(render_output_block(output_text))

    if not frontmatter:
        raise ValueError("missing frontmatter in first markdown cell")

    body = "\n\n".join(body_parts).rstrip()
    if body:
        return f"{frontmatter}\n{body}\n"
    return f"{frontmatter}\n"


def convert_notebook_to_mdx(notebook_path: Path) -> str:
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    return ensure_colab_url(notebook_to_mdx(notebook), notebook_path.stem)


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
        notebooks = discover_slug_paths(
            NOTEBOOKS_DIR, extension=".ipynb", slug=args.slug, label="notebook"
        )
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
