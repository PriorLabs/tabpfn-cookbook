"""Shared helpers for cookbook notebooks and markdown."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

ALLOWED_FRONTMATTER_KEYS = frozenset(
    {
        "title",
        "description",
        "icon",
        "cookbookTags",
        "feature_in_doc",
        "authors",
        "colab_url",
    }
)
AUTHOR_SOCIAL_KEYS = frozenset({"github", "linkedin", "twitter", "x"})
COOKBOOKS_REPO = "PriorLabs/tabpfn-cookbook"
COOKBOOKS_RAW_BRANCH = "main"
COOKBOOKS_RAW_BASE_URL = (
    f"https://raw.githubusercontent.com/{COOKBOOKS_REPO}/{COOKBOOKS_RAW_BRANCH}"
)

FRONTMATTER_BLOCK_RE = re.compile(r"^---\r?\n([\s\S]*?)\r?\n---", re.MULTILINE)


@dataclass(frozen=True)
class MdxBlockMarkers:
    start: str
    end: str


AUTHOR_BLOCK = MdxBlockMarkers(
    "{/* cookbook-authors:start process_markdown.py */}",
    "{/* cookbook-authors:end process_markdown.py */}",
)
COLAB_BLOCK = MdxBlockMarkers(
    "{/* cookbook-colab:start process_markdown.py */}",
    "{/* cookbook-colab:end process_markdown.py */}",
)
META_BLOCK = MdxBlockMarkers(
    "{/* cookbook-meta:start process_markdown.py */}",
    "{/* cookbook-meta:end process_markdown.py */}",
)

# Back-compat aliases used in older docs / comments
AUTHOR_BLOCK_START = AUTHOR_BLOCK.start
AUTHOR_BLOCK_END = AUTHOR_BLOCK.end
COLAB_BLOCK_START = COLAB_BLOCK.start
COLAB_BLOCK_END = COLAB_BLOCK.end
META_BLOCK_START = META_BLOCK.start
META_BLOCK_END = META_BLOCK.end


def discover_slug_paths(
    directory: Path,
    *,
    extension: str,
    slug: str | None = None,
    label: str = "file",
    only_slugs: list[str] | frozenset[str] | None = None,
) -> list[Path]:
    """Return paths under ``directory`` for ``--slug`` / ``--all`` CLIs."""
    ext = extension if extension.startswith(".") else f".{extension}"

    if slug:
        path = directory / f"{slug}{ext}"
        if not path.exists():
            raise FileNotFoundError(f"{label.capitalize()} not found: {path}")
        return [path]

    if only_slugs is not None:
        return [directory / f"{name}{ext}" for name in sorted(only_slugs)]

    return sorted(directory.glob(f"*{ext}"))


def try_split_frontmatter(text: str) -> tuple[str | None, str]:
    """Soft split: return ``(None, text)`` if no frontmatter block is present."""
    stripped = text.strip()
    match = FRONTMATTER_BLOCK_RE.match(stripped)
    if not match:
        return None, text
    remainder = stripped[match.end() :].lstrip("\n")
    return match.group(0).strip(), remainder


def extract_frontmatter_yaml(text: str) -> str:
    match = FRONTMATTER_BLOCK_RE.match(text.strip())
    if not match:
        raise ValueError("missing YAML frontmatter block (expected --- at top)")
    return match.group(1)


def format_yaml_error(error: yaml.YAMLError) -> str:
    if isinstance(error, yaml.MarkedYAMLError) and error.problem_mark is not None:
        mark = error.problem_mark
        line = mark.line + 1
        column = mark.column + 1
        detail = error.problem or str(error)
        return f"invalid YAML frontmatter on line {line}, column {column}: {detail}"
    return f"invalid YAML frontmatter: {error}"


def parse_frontmatter_text(text: str) -> dict[str, object]:
    yaml_text = extract_frontmatter_yaml(text)

    try:
        parsed = yaml.safe_load(yaml_text)
    except yaml.YAMLError as error:
        raise ValueError(format_yaml_error(error)) from error

    if parsed is None:
        parsed = {}
    if not isinstance(parsed, dict):
        raise ValueError("frontmatter must be a YAML mapping")

    frontmatter: dict[str, object] = {}
    for key, value in parsed.items():
        if not isinstance(key, str):
            raise ValueError(f"frontmatter keys must be strings, got {type(key).__name__}")
        if key not in ALLOWED_FRONTMATTER_KEYS:
            raise ValueError(
                f"unknown frontmatter key {key!r} (allowed: {', '.join(sorted(ALLOWED_FRONTMATTER_KEYS))})"
            )
        frontmatter[key] = value

    return frontmatter


def split_mdx_document(text: str) -> tuple[str, str, str]:
    match = re.match(r"^(---\r?\n[\s\S]*?\r?\n---)\r?\n?", text)
    if not match:
        raise ValueError("missing YAML frontmatter block (expected --- at top)")

    frontmatter_block = match.group(1)
    body = text[match.end() :]
    return frontmatter_block, body, text


def dump_frontmatter_block(frontmatter: dict[str, object]) -> str:
    dumped = yaml.safe_dump(
        frontmatter,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )
    return f"---\n{dumped.rstrip()}\n---"


def normalize_mdx_block(block: str) -> str:
    return "\n".join(line.rstrip() for line in block.strip().splitlines())


def strip_mdx_block(body: str, markers: MdxBlockMarkers) -> str:
    pattern = re.compile(
        rf"\s*{re.escape(markers.start)}[\s\S]*?{re.escape(markers.end)}\s*\n?",
        re.MULTILINE,
    )
    return pattern.sub("", body, count=1).lstrip("\n")


def extract_mdx_block(body: str, markers: MdxBlockMarkers) -> str | None:
    match = re.search(
        rf"{re.escape(markers.start)}([\s\S]*?){re.escape(markers.end)}",
        body,
    )
    if not match:
        return None
    return f"{markers.start}{match.group(1)}{markers.end}"


def wrap_mdx_block(markers: MdxBlockMarkers, *inner_lines: str) -> str:
    return "\n".join([markers.start, *inner_lines, markers.end])


def inject_mdx_block(body: str, markers: MdxBlockMarkers, block: str | None) -> str:
    body = strip_mdx_block(body, markers)
    if not block:
        return body
    if body:
        return f"{block}\n{body}"
    return f"{block}\n"


def remediation_command(*, slug: str, has_notebook: bool) -> str:
    if has_notebook:
        return f"python3 scripts/convert_to_markdown.py --slug {slug}"
    return f"python3 scripts/process_markdown.py --slug {slug}"


def injected_block_errors(
    *,
    source: str,
    existing: str | None,
    expected: str | None,
    remediation: str,
    missing_message: str,
    stale_message: str,
    orphan_message: str,
) -> list[str]:
    if expected is None:
        if existing:
            return [f"{source}: {orphan_message}"]
        return []

    if not existing:
        return [f"{source}: {missing_message} Run: {remediation}"]

    if normalize_mdx_block(existing) != normalize_mdx_block(expected):
        return [f"{source}: {stale_message} Run: {remediation}"]

    return []


SOCIAL_ICON_SVGS = {
    "github": (
        "GitHub",
        '<svg className="cookbook-author-icon" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 0C5.374 0 0 5.373 0 12c0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/></svg>',
    ),
    "linkedin": (
        "LinkedIn",
        '<svg className="cookbook-author-icon" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 1 1 0-4.124 2.062 2.062 0 0 1 0 4.124zM7.119 20.452H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/></svg>',
    ),
    "x": (
        "X",
        '<svg className="cookbook-author-icon" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg>',
    ),
}


def render_social_link(platform: str, url: str) -> str:
    label, icon_svg = SOCIAL_ICON_SVGS[platform]
    safe_url = html.escape(url, quote=True)
    return (
        f'<a href="{safe_url}" className="cookbook-author-icon-link" '
        f'aria-label="{label}" target="_blank" rel="noopener noreferrer">'
        f"{icon_svg}</a>"
    )


def render_author_entry(author: dict[str, str]) -> str:
    links: list[str] = []
    if author.get("github"):
        links.append(render_social_link("github", author["github"]))
    if author.get("linkedin"):
        links.append(render_social_link("linkedin", author["linkedin"]))

    x_url = author.get("x") or author.get("twitter")
    if x_url:
        links.append(render_social_link("x", x_url))

    parts = [f'<span className="cookbook-author-name">{html.escape(author["name"])}</span>']
    if links:
        parts.append(f'<span className="cookbook-author-links">{"".join(links)}</span>')

    return f'<span className="cookbook-author-entry">{"".join(parts)}</span>'


def render_authors_block(authors: list[dict[str, str]]) -> str:
    entries: list[str] = []
    for index, author in enumerate(authors):
        if index > 0:
            entries.append('<span className="cookbook-author-separator" aria-hidden="true">·</span>')
        entries.append(render_author_entry(author))

    return wrap_mdx_block(
        AUTHOR_BLOCK,
        '<div className="cookbook-authors">',
        '  <div className="cookbook-author-bar">',
        '    <span className="cookbook-author-by">By</span>',
        f'    <span className="cookbook-author-list">{"".join(entries)}</span>',
        "  </div>",
        "</div>",
    )


def colab_url_for_notebook(slug: str) -> str:
    return (
        f"https://colab.research.google.com/github/{COOKBOOKS_REPO}/blob/"
        f"{COOKBOOKS_RAW_BRANCH}/notebooks/{slug}.ipynb"
    )


def ensure_colab_url(content: str, slug: str) -> str:
    """Set frontmatter ``colab_url`` for a notebook-backed recipe."""
    _, body, _ = split_mdx_document(content)
    frontmatter = parse_frontmatter_text(content)
    frontmatter["colab_url"] = colab_url_for_notebook(slug)
    if body:
        return f"{dump_frontmatter_block(frontmatter)}\n{body.lstrip(chr(10))}"
    return f"{dump_frontmatter_block(frontmatter)}\n"


def render_colab_block(colab_url: str) -> str:
    safe_url = html.escape(colab_url, quote=True)
    # Official Colab monogram (Simple Icons / brand mark), single fill #F9AB00.
    colab_icon = (
        '<svg className="cookbook-colab-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">'
        '<path fill="#F9AB00" d="M16.9414 4.9757a7.033 7.033 0 0 0-4.9308 2.0646 7.033 7.033 0 0 0-.1232 9.8068l2.395-2.395a3.6455 3.6455 0 0 1 5.1497-5.1478l2.397-2.3989a7.033 7.033 0 0 0-4.8877-1.9297zM7.07 4.9855a7.033 7.033 0 0 0-4.8878 1.9316l2.3911 2.3911a3.6434 3.6434 0 0 1 5.0227.1271l1.7341-2.9737-.0997-.0802A7.033 7.033 0 0 0 7.07 4.9855zm15.0093 2.1721l-2.3892 2.3911a3.6455 3.6455 0 0 1-5.1497 5.1497l-2.4067 2.4068a7.0362 7.0362 0 0 0 9.9456-9.9476zM1.932 7.1674a7.033 7.033 0 0 0-.002 9.6816l2.397-2.397a3.6434 3.6434 0 0 1-.004-4.8916zm7.664 7.4235c-1.38 1.3816-3.5863 1.411-5.0168.1134l-2.397 2.395c2.4693 2.3328 6.263 2.5753 9.0072.5455l.1368-.1115z"/>'
        "</svg>"
    )
    return wrap_mdx_block(
        COLAB_BLOCK,
        '<div className="cookbook-colab">',
        f'  <a href="{safe_url}" className="cookbook-colab-button" '
        'target="_blank" rel="noopener noreferrer">',
        f"    {colab_icon}",
        '    <span className="cookbook-colab-label">Open in Colab</span>',
        "  </a>",
        "</div>",
    )


def inject_author_block(body: str, authors: list[dict[str, str]] | None) -> str:
    block = render_authors_block(authors) if authors else None
    return inject_mdx_block(body, AUTHOR_BLOCK, block)


def inject_colab_block(body: str, colab_url: str | None) -> str:
    if not colab_url or not str(colab_url).strip():
        return inject_mdx_block(body, COLAB_BLOCK, None)
    return inject_mdx_block(body, COLAB_BLOCK, render_colab_block(str(colab_url).strip()))


def render_meta_block(
    authors: list[dict[str, str]] | None,
    colab_url: str | None,
) -> str | None:
    """Authors (left) and Colab (right) on one horizontal row."""
    parts: list[str] = []
    if authors:
        parts.append(render_authors_block(authors))
    if colab_url and str(colab_url).strip():
        parts.append(render_colab_block(str(colab_url).strip()))
    if not parts:
        return None
    return wrap_mdx_block(
        META_BLOCK,
        '<div className="cookbook-meta">',
        *parts,
        "</div>",
    )


def process_markdown_content(content: str) -> str:
    frontmatter_block, body, _ = split_mdx_document(content)
    frontmatter = parse_frontmatter_text(content)
    authors = frontmatter.get("authors")
    colab_url = frontmatter.get("colab_url")

    # Meta wraps both; also strip legacy standalone author/colab blocks.
    body = strip_mdx_block(body, META_BLOCK)
    body = strip_mdx_block(body, AUTHOR_BLOCK)
    body = strip_mdx_block(body, COLAB_BLOCK)

    meta = render_meta_block(
        authors if isinstance(authors, list) else None,
        str(colab_url) if isinstance(colab_url, str) else None,
    )
    new_body = inject_mdx_block(body, META_BLOCK, meta)

    if new_body:
        return f"{frontmatter_block}\n{new_body}"
    return f"{frontmatter_block}\n"


def author_block_is_current(
    content: str,
    *,
    source: str,
    has_notebook: bool = False,
) -> list[str]:
    frontmatter = parse_frontmatter_text(content)
    _, body, _ = split_mdx_document(content)
    authors = frontmatter.get("authors")
    existing = extract_mdx_block(body, AUTHOR_BLOCK)
    expected = render_authors_block(authors) if isinstance(authors, list) and authors else None
    remediation = remediation_command(slug=Path(source).stem, has_notebook=has_notebook)

    return injected_block_errors(
        source=source,
        existing=existing,
        expected=expected,
        remediation=remediation,
        missing_message="authors found in frontmatter but author block is missing.",
        stale_message="author block is out of date.",
        orphan_message="remove stale author block or add authors to frontmatter",
    )


def colab_block_is_current(
    content: str,
    *,
    source: str,
    has_notebook: bool = False,
) -> list[str]:
    frontmatter = parse_frontmatter_text(content)
    _, body, _ = split_mdx_document(content)
    colab_url = frontmatter.get("colab_url")
    existing = extract_mdx_block(body, COLAB_BLOCK)
    slug = Path(source).stem
    remediation = remediation_command(slug=slug, has_notebook=has_notebook)

    if has_notebook:
        expected_url = colab_url_for_notebook(slug)
        if not isinstance(colab_url, str) or colab_url.strip() != expected_url:
            return [
                f"{source}: notebook recipes must set colab_url to {expected_url!r}. "
                f"Run: {remediation}"
            ]
        return injected_block_errors(
            source=source,
            existing=existing,
            expected=render_colab_block(expected_url),
            remediation=remediation,
            missing_message="colab_url is set but Open in Colab button is missing.",
            stale_message="Open in Colab button is out of date.",
            orphan_message="remove stale Open in Colab button or add colab_url to frontmatter",
        )

    if not colab_url:
        return injected_block_errors(
            source=source,
            existing=existing,
            expected=None,
            remediation=remediation,
            missing_message="",
            stale_message="",
            orphan_message="remove stale Open in Colab button or add colab_url to frontmatter",
        )

    if not isinstance(colab_url, str) or not colab_url.strip():
        return [f"{source}: colab_url must be a non-empty string when set"]

    return injected_block_errors(
        source=source,
        existing=existing,
        expected=render_colab_block(colab_url.strip()),
        remediation=remediation,
        missing_message="colab_url is set but Open in Colab button is missing.",
        stale_message="Open in Colab button is out of date.",
        orphan_message="remove stale Open in Colab button or add colab_url to frontmatter",
    )


def parse_mdx_frontmatter(path: Path) -> dict[str, object]:
    return parse_frontmatter_text(path.read_text(encoding="utf-8"))


def cell_source(cell: dict) -> str:
    source = cell.get("source", "")
    if isinstance(source, list):
        return "".join(source)
    return source


ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

# stdout lines dropped as progress/log noise rather than real results.
OUTPUT_NOISE_LINE_RE = re.compile(
    r"^\s*(?:"
    r"\d{1,2}:\d{2}\b"  # MM:SS progress timestamps (e.g. tabpfn-client spinner)
    r"|Found existing access token"  # tabpfn-client auth notice
    r"|(?:WARNING|INFO|DEBUG|ERROR|CRITICAL):"  # logging-module lines on stdout
    r")"
)

# execute_result / display_data text/plain reprs that are objects, not data.
OUTPUT_REPR_NOISE_RE = re.compile(
    r"^<.*\b(?:matplotlib|Axes|Figure|module|object at 0x)\b.*>$"
)

# Cell tags that suppress output rendering (Jupyter Book convention).
OUTPUT_SKIP_TAGS = frozenset({"hide-output", "remove-output", "no-output"})

_OUTPUT_PLAIN_MIME = "text/plain"


def cell_tags(cell: dict) -> set[str]:
    tags = cell.get("metadata", {}).get("tags", [])
    if isinstance(tags, list):
        return {str(tag).strip() for tag in tags}
    return set()


def is_command_cell(source: str) -> bool:
    """True when every code line is a shell (`!`) or magic (`%`) command."""
    code_lines = [
        line.strip()
        for line in source.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    if not code_lines:
        return False
    return all(line.startswith(("!", "%")) for line in code_lines)


def _output_stream_text(output: dict) -> str:
    text = output.get("text") or ""
    return "".join(text) if isinstance(text, list) else str(text)


def _output_plain_text(output: dict) -> str | None:
    data = output.get("data") or {}
    plain = data.get(_OUTPUT_PLAIN_MIME)
    if plain is None:
        return None
    return "".join(plain) if isinstance(plain, list) else str(plain)


def clean_output_text(text: str) -> str:
    text = ANSI_ESCAPE_RE.sub("", text).replace("\r\n", "\n")

    lines: list[str] = []
    for raw_line in text.split("\n"):
        # Progress bars overwrite via \r; keep the last non-empty segment.
        # Trailing \r alone would make split("\r")[-1] == "", so strip first.
        segments = raw_line.rstrip("\r").split("\r")
        segment = next((part for part in reversed(segments) if part != ""), "")
        if OUTPUT_NOISE_LINE_RE.match(segment):
            continue
        lines.append(segment.rstrip())

    collapsed: list[str] = []
    previous_blank = False
    for line in lines:
        is_blank = not line
        if is_blank and previous_blank:
            continue
        collapsed.append(line)
        previous_blank = is_blank

    return "\n".join(collapsed).strip("\n")


def extract_cell_output(cell: dict) -> str | None:
    """Return cleaned textual output for a code cell, or None to render nothing."""
    if cell.get("cell_type") != "code":
        return None
    if OUTPUT_SKIP_TAGS & cell_tags(cell):
        return None
    if is_command_cell(cell_source(cell)):
        return None

    chunks: list[str] = []
    for output in cell.get("outputs") or []:
        otype = output.get("output_type")
        if otype == "stream":
            if output.get("name") == "stderr":
                continue
            chunks.append(_output_stream_text(output))
        elif otype in ("execute_result", "display_data"):
            plain = _output_plain_text(output)
            if plain is None:
                continue
            if OUTPUT_REPR_NOISE_RE.match(plain.strip()):
                continue
            chunks.append(plain if plain.endswith("\n") else plain + "\n")
        # 'error' outputs (tracebacks) are intentionally dropped.

    cleaned = clean_output_text("".join(chunks))
    return cleaned or None


def render_output_block(output_text: str) -> str:
    fence = "```"
    while fence in output_text:
        fence += "`"
    return f"{fence}console\n{output_text}\n{fence}"


def validate_frontmatter(frontmatter: dict[str, object], *, source: str) -> list[str]:
    errors: list[str] = []

    for key in ("title", "description"):
        value = frontmatter.get(key)
        if not value or not str(value).strip():
            errors.append(f"{source}: missing required frontmatter field {key!r}")

    if "icon" in frontmatter and not str(frontmatter["icon"]).strip():
        errors.append(f"{source}: icon must be a non-empty string when set")

    if "feature_in_doc" in frontmatter and not str(frontmatter["feature_in_doc"]).strip():
        errors.append(f"{source}: feature_in_doc must be a non-empty string when set")

    if "colab_url" in frontmatter:
        value = frontmatter.get("colab_url")
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{source}: colab_url must be a non-empty string when set")
        elif not value.strip().startswith("https://colab.research.google.com/"):
            errors.append(f"{source}: colab_url must be a Google Colab URL")

    tags = frontmatter.get("cookbookTags")
    if tags is not None:
        if not isinstance(tags, list) or not tags:
            errors.append(f"{source}: cookbookTags must be a non-empty list")
        elif any(not str(tag).strip() for tag in tags):
            errors.append(f"{source}: cookbookTags entries must be non-empty strings")

    authors = frontmatter.get("authors")
    if authors is not None:
        if not isinstance(authors, list) or not authors:
            errors.append(f"{source}: authors must be a non-empty list")
            return errors

        for index, author in enumerate(authors, start=1):
            if not isinstance(author, dict):
                errors.append(f"{source}: authors[{index}] must be an object")
                continue

            if not str(author.get("name", "")).strip():
                errors.append(f"{source}: authors[{index}] is missing name")

            unknown = set(author) - {"name", *AUTHOR_SOCIAL_KEYS}
            if unknown:
                errors.append(
                    f"{source}: authors[{index}] has unknown fields: {', '.join(sorted(unknown))}"
                )

            for social_key in AUTHOR_SOCIAL_KEYS - {"x"}:
                value = author.get(social_key)
                if value is not None and not str(value).strip():
                    errors.append(f"{source}: authors[{index}].{social_key} must be a URL")

    return errors


YOUTUBE_URL_RE = re.compile(
    r"(?:https?://)?(?:www\.)?"
    r"(?:youtu\.be/([\w-]{11})|youtube\.com/watch\?v=([\w-]{11})|youtube\.com/embed/([\w-]{11}))",
    re.IGNORECASE,
)

YOUTUBE_MARKDOWN_LINK_RE = re.compile(
    r"\[([^\]]+)\]\((https?://[^)]+)\)",
    re.IGNORECASE,
)

STANDALONE_YOUTUBE_LINE_RE = re.compile(
    r"^\s*(https?://(?:www\.)?(?:youtu\.be/[\w-]+|youtube\.com/(?:watch\?v=[\w-]+|embed/[\w-]+))[^\s]*)\s*$",
    re.IGNORECASE | re.MULTILINE,
)

VISUAL_MARKDOWN_IMAGE_RE = re.compile(
    r"!\[([^\]]*)\]\((?:\.\./)?visuals/([^)]+)\)"
)


def visual_raw_url(relative_path: str) -> str:
    return f"{COOKBOOKS_RAW_BASE_URL}/visuals/{relative_path.lstrip('/')}"


def transform_visual_paths_for_mdx(text: str) -> str:
    def replace_visual(match: re.Match[str]) -> str:
        alt, path = match.group(1), match.group(2).strip()
        return f"![{alt}]({visual_raw_url(path)})"

    return VISUAL_MARKDOWN_IMAGE_RE.sub(replace_visual, text)


def extract_youtube_id(url: str) -> str | None:
    match = YOUTUBE_URL_RE.search(url)
    if not match:
        return None
    return next(group for group in match.groups() if group)


def youtube_embed_block(video_id: str, title: str = "YouTube video player") -> str:
    safe_title = title.replace('"', "&quot;")
    return (
        "<iframe\n"
        '  className="w-full aspect-video rounded-xl"\n'
        f'  src="https://www.youtube.com/embed/{video_id}"\n'
        f'  title="{safe_title}"\n'
        '  allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"\n'
        "  allowFullScreen\n"
        "></iframe>"
    )


def transform_markdown_for_mintlify(text: str) -> str:
    def replace_link(match: re.Match[str]) -> str:
        label, url = match.group(1).strip(), match.group(2).strip()
        video_id = extract_youtube_id(url)
        if not video_id:
            return match.group(0)

        label_lower = label.lower()
        if label_lower == "youtube" or label_lower.startswith("youtube:"):
            title = label.split(":", 1)[1].strip() if ":" in label else "YouTube video player"
            return youtube_embed_block(video_id, title or "YouTube video player")

        return match.group(0)

    def replace_standalone_line(match: re.Match[str]) -> str:
        video_id = extract_youtube_id(match.group(1))
        if not video_id:
            return match.group(0)
        return youtube_embed_block(video_id)

    text = YOUTUBE_MARKDOWN_LINK_RE.sub(replace_link, text)
    text = STANDALONE_YOUTUBE_LINE_RE.sub(replace_standalone_line, text)
    return transform_visual_paths_for_mdx(text)
