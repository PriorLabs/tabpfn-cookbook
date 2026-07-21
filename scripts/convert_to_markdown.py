#!/usr/bin/env python3
"""Convert notebooks into Mintlify-ready markdown files.

Author blocks and Colab buttons are injected automatically from frontmatter.
Embedded plot outputs are written to ``visuals/<slug>/`` and inserted into the
MDX as conversion walks the notebook. The notebook file is not modified.

Manual markdown image cells that already point at ``../visuals/...`` are left
as-is (paths are rewritten to raw GitHub URLs). If a code cell has both an
embedded plot and a following manual visuals markdown cell, the file named by
that markdown cell is refreshed and the markdown cell supplies the MDX image.

For markdown-only recipes, use ``process_markdown.py`` instead.
"""

from __future__ import annotations

import argparse
import base64
import json
import re
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
VISUALS_DIR = ROOT / "visuals"

IMAGE_MIME_EXTENSIONS = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
}

VISUAL_MARKDOWN_REF_RE = re.compile(
    r"!\[([^\]]*)\]\(\.\./visuals/([^)]+)\)"
)


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


def extract_image_outputs(outputs: list[dict] | None) -> list[tuple[bytes, str]]:
    images: list[tuple[bytes, str]] = []
    for output in outputs or []:
        data = output.get("data") or {}
        for mime, extension in IMAGE_MIME_EXTENSIONS.items():
            if mime not in data:
                continue
            payload = data[mime]
            if isinstance(payload, list):
                payload = "".join(payload)
            images.append((base64.b64decode(payload), extension))
            break
    return images


def parse_visual_markdown_ref(source: str, slug: str) -> tuple[str, str] | None:
    match = VISUAL_MARKDOWN_REF_RE.search(source)
    if not match:
        return None
    alt, path = match.group(1), match.group(2).strip()
    if not path.startswith(f"{slug}/"):
        return None
    return Path(path).name, alt


def following_visual_ref(cells: list[dict], cell_index: int, slug: str) -> tuple[str, str] | None:
    next_index = cell_index + 1
    if next_index >= len(cells):
        return None
    next_cell = cells[next_index]
    if next_cell.get("cell_type") != "markdown":
        return None
    return parse_visual_markdown_ref(cell_source(next_cell), slug)


def preceding_heading_alt(cells: list[dict], cell_index: int) -> str | None:
    for index in range(cell_index - 1, -1, -1):
        cell = cells[index]
        if cell.get("cell_type") != "markdown":
            continue
        for line in cell_source(cell).splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                return stripped.lstrip("#").strip()
    return None


def write_visual(slug: str, filename: str, image_bytes: bytes) -> Path:
    output_dir = VISUALS_DIR / slug
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / filename
    path.write_bytes(image_bytes)
    return path


def next_auto_filename(plot_index: int, extension: str) -> str:
    """Stable per-run name; overwrites the same slot so convert stays idempotent."""
    return f"plot-{plot_index:02d}{extension}"


def emit_plot_images(
    *,
    cells: list[dict],
    cell_index: int,
    slug: str,
    plot_counter: list[int],
) -> list[str]:
    """Write embedded plot outputs and return MDX image markdown blocks to insert.

    Returns an empty list when a following markdown cell already references
    ``../visuals/<slug>/...`` (that cell will emit the image). Embedded bytes
    still refresh that named file when present.
    """
    cell = cells[cell_index]
    images = extract_image_outputs(cell.get("outputs"))
    if not images:
        return []

    manual = following_visual_ref(cells, cell_index, slug)
    blocks: list[str] = []

    for image_offset, (image_bytes, extension) in enumerate(images):
        if manual is not None and image_offset == 0:
            filename, _alt = manual
            if not filename.endswith(extension):
                filename = f"{Path(filename).stem}{extension}"
            write_visual(slug, filename, image_bytes)
            continue

        plot_counter[0] += 1
        filename = next_auto_filename(plot_counter[0], extension)
        alt = preceding_heading_alt(cells, cell_index) or f"Plot {plot_counter[0]}"
        write_visual(slug, filename, image_bytes)
        blocks.append(
            transform_markdown_for_mintlify(
                f"![{alt}](../visuals/{slug}/{filename})"
            )
        )

    return blocks


def notebook_to_mdx(notebook: dict, *, slug: str) -> str:
    body_parts: list[str] = []
    frontmatter: str | None = None
    frontmatter_consumed = False
    cells = notebook.get("cells", [])
    plot_counter = [0]

    for cell_index, cell in enumerate(cells):
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
                body_parts.extend(
                    emit_plot_images(
                        cells=cells,
                        cell_index=cell_index,
                        slug=slug,
                        plot_counter=plot_counter,
                    )
                )

    if not frontmatter:
        raise ValueError("missing frontmatter in first markdown cell")

    body = "\n\n".join(body_parts).rstrip()
    if body:
        return f"{frontmatter}\n{body}\n"
    return f"{frontmatter}\n"


def convert_notebook_to_mdx(notebook_path: Path) -> str:
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    return ensure_colab_url(notebook_to_mdx(notebook, slug=notebook_path.stem), notebook_path.stem)


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
