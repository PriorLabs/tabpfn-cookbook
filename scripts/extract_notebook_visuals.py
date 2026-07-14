#!/usr/bin/env python3
"""Extract notebook plot outputs into visuals/ and reference them from notebooks."""

from __future__ import annotations

import argparse
import base64
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cookbook_utils import discover_slug_paths

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOKS_DIR = ROOT / "notebooks"
VISUALS_DIR = ROOT / "visuals"

# cell_index -> (filename, alt text)
NOTEBOOK_IMAGE_NAMES: dict[str, dict[int, tuple[str, str]]] = {
    "experiment_with_thinking_mode": {
        23: ("naticus-results.png", "NATICUSdroid results"),
        33: ("coupon-results.png", "In-vehicle coupon results"),
    },
    "interpret_results": {
        12: ("shap-beeswarm.png", "SHAP beeswarm plot"),
        14: ("partial-dependence.png", "Partial dependence plots"),
        17: ("high-risk-patient.png", "Highest-risk patient explanation"),
        18: ("low-risk-patient.png", "Lowest-risk patient explanation"),
        19: ("borderline-patient.png", "Borderline patient explanation"),
    },
    "predictive_distribution": {
        15: ("sample-prediction-0.png", "Predicted distribution for sample 0"),
        16: ("sample-prediction-10.png", "Predicted distribution for sample 10"),
        23: ("uncertainty-band.png", "Uncertainty band plot"),
    },
}

IMAGE_MIME_EXTENSIONS = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--all",
        action="store_true",
        help="Process every notebook that has configured image outputs.",
    )
    parser.add_argument(
        "--slug",
        help="Process a single notebook by slug (filename without .ipynb).",
    )
    return parser.parse_args()


def extract_image_bytes(outputs: list[dict]) -> tuple[bytes, str] | None:
    for output in outputs:
        data = output.get("data", {})
        for mime, extension in IMAGE_MIME_EXTENSIONS.items():
            if mime not in data:
                continue
            payload = data[mime]
            if isinstance(payload, list):
                payload = "".join(payload)
            return base64.b64decode(payload), extension
    return None


def strip_image_outputs(outputs: list[dict]) -> list[dict]:
    cleaned: list[dict] = []
    for output in outputs:
        data = output.get("data", {})
        if any(mime in data for mime in IMAGE_MIME_EXTENSIONS):
            continue
        cleaned.append(output)
    return cleaned


def markdown_image_cell(slug: str, filename: str, alt: str) -> dict:
    return {
        "cell_type": "markdown",
        "metadata": {},
        "source": [f"![{alt}](../visuals/{slug}/{filename})\n"],
    }


def has_following_visual_cell(cells: list[dict], cell_index: int, slug: str, filename: str) -> bool:
    next_index = cell_index + 1
    if next_index >= len(cells):
        return False

    next_cell = cells[next_index]
    if next_cell.get("cell_type") != "markdown":
        return False

    source = next_cell.get("source", "")
    if isinstance(source, list):
        source = "".join(source)

    return f"../visuals/{slug}/{filename}" in source


def process_notebook(notebook_path: Path) -> list[str]:
    slug = notebook_path.stem
    image_names = NOTEBOOK_IMAGE_NAMES.get(slug, {})
    if not image_names:
        return []

    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    cells = notebook.get("cells", [])
    output_dir = VISUALS_DIR / slug
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []

    insertions: list[tuple[int, dict]] = []
    for cell_index, (filename, alt) in sorted(image_names.items()):
        if cell_index >= len(cells):
            raise ValueError(f"{notebook_path.name}: cell index {cell_index} is out of range")

        cell = cells[cell_index]
        if cell.get("cell_type") != "code":
            raise ValueError(
                f"{notebook_path.name}: expected code cell at index {cell_index}, "
                f"got {cell.get('cell_type')!r}"
            )

        extracted = extract_image_bytes(cell.get("outputs", []))
        if extracted is None:
            image_path = output_dir / filename
            if not image_path.exists():
                raise ValueError(
                    f"{notebook_path.name}: no image output in cell {cell_index} "
                    f"and missing file {image_path.relative_to(ROOT)}"
                )
        else:
            image_bytes, extension = extracted
            if not filename.endswith(extension):
                filename = f"{Path(filename).stem}{extension}"
            image_path = output_dir / filename
            image_path.write_bytes(image_bytes)
            written.append(image_path.relative_to(ROOT).as_posix())

        cell["outputs"] = strip_image_outputs(cell.get("outputs", []))
        if has_following_visual_cell(cells, cell_index, slug, filename):
            continue
        insertions.append((cell_index + 1, markdown_image_cell(slug, filename, alt)))

    for offset, (cell_index, new_cell) in enumerate(insertions):
        cells.insert(cell_index + offset, new_cell)

    notebook_path.write_text(
        json.dumps(notebook, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return written


def main() -> int:
    args = parse_args()
    if not args.all and not args.slug:
        print("Pass --all or --slug <name>", file=sys.stderr)
        return 1

    try:
        notebooks = discover_slug_paths(
            NOTEBOOKS_DIR,
            extension=".ipynb",
            slug=args.slug,
            label="notebook",
            only_slugs=None if args.slug else list(NOTEBOOK_IMAGE_NAMES),
        )
    except FileNotFoundError as error:
        print(error, file=sys.stderr)
        return 1

    errors = 0
    for notebook_path in notebooks:
        try:
            written = process_notebook(notebook_path)
            if written:
                print(f"{notebook_path.name}:")
                for path in written:
                    print(f"  - {path}")
            else:
                print(f"{notebook_path.name}: no configured images")
        except ValueError as error:
            print(f"  - {error}", file=sys.stderr)
            errors += 1

    if errors:
        return 1

    print(f"Updated {len(notebooks) - errors} notebook(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
