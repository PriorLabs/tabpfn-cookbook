"""Shared helpers for cookbook notebooks and markdown."""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

import yaml

ALLOWED_FRONTMATTER_KEYS = frozenset(
    {"title", "description", "icon", "cookbookTags", "feature_in_doc", "authors"}
)
AUTHOR_SOCIAL_KEYS = frozenset({"github", "linkedin", "twitter", "x"})
AUTHOR_BLOCK_START = "{/* cookbook-authors:start process_markdown.py */}"
AUTHOR_BLOCK_END = "{/* cookbook-authors:end process_markdown.py */}"
COOKBOOKS_REPO = "PriorLabs/prior-cookbook"
COOKBOOKS_RAW_BRANCH = "main"
COOKBOOKS_RAW_BASE_URL = (
    f"https://raw.githubusercontent.com/{COOKBOOKS_REPO}/{COOKBOOKS_RAW_BRANCH}"
)


def extract_frontmatter_yaml(text: str) -> str:
    match = re.match(r"^---\r?\n([\s\S]*?)\r?\n---", text.strip())
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


def strip_author_block(body: str) -> str:
    pattern = re.compile(
        rf"\s*{re.escape(AUTHOR_BLOCK_START)}[\s\S]*?{re.escape(AUTHOR_BLOCK_END)}\s*\n?",
        re.MULTILINE,
    )
    return pattern.sub("", body, count=1).lstrip("\n")


def extract_author_block(body: str) -> str | None:
    match = re.search(
        rf"{re.escape(AUTHOR_BLOCK_START)}([\s\S]*?){re.escape(AUTHOR_BLOCK_END)}",
        body,
    )
    if not match:
        return None
    return f"{AUTHOR_BLOCK_START}{match.group(1)}{AUTHOR_BLOCK_END}"


def normalize_author_block(block: str) -> str:
    return "\n".join(line.rstrip() for line in block.strip().splitlines())


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

    lines = [
        AUTHOR_BLOCK_START,
        '<div className="cookbook-authors">',
        '  <div className="cookbook-author-bar">',
        '    <span className="cookbook-author-by">By</span>',
        f'    <span className="cookbook-author-list">{"".join(entries)}</span>',
        "  </div>",
        "</div>",
        AUTHOR_BLOCK_END,
    ]
    return "\n".join(lines)


def inject_author_block(body: str, authors: list[dict[str, str]] | None) -> str:
    body = strip_author_block(body)
    if not authors:
        return body

    block = render_authors_block(authors)
    if body:
        return f"{block}\n{body}"
    return f"{block}\n"


def process_markdown_content(content: str) -> str:
    frontmatter_block, body, _ = split_mdx_document(content)
    frontmatter = parse_frontmatter_text(content)
    authors = frontmatter.get("authors")
    new_body = inject_author_block(body, authors if isinstance(authors, list) else None)

    if new_body:
        return f"{frontmatter_block}\n{new_body}"
    return f"{frontmatter_block}\n"


def author_remediation_command(*, slug: str, has_notebook: bool) -> str:
    if has_notebook:
        return f"python3 scripts/convert_to_markdown.py --slug {slug}"
    return f"python3 scripts/process_markdown.py --slug {slug}"


def author_block_is_current(
    content: str,
    *,
    source: str,
    has_notebook: bool = False,
) -> list[str]:
    frontmatter = parse_frontmatter_text(content)
    _, body, _ = split_mdx_document(content)
    authors = frontmatter.get("authors")
    existing = extract_author_block(body)

    if not authors:
        if existing:
            return [f"{source}: remove stale author block or add authors to frontmatter"]
        return []

    slug = Path(source).stem
    remediation = author_remediation_command(slug=slug, has_notebook=has_notebook)
    expected = render_authors_block(authors)  # type: ignore[arg-type]
    if not existing:
        return [
            f"{source}: authors found in frontmatter but author block is missing. "
            f"Run: {remediation}"
        ]

    if normalize_author_block(existing) != normalize_author_block(expected):
        return [
            f"{source}: author block is out of date. "
            f"Run: {remediation}"
        ]

    return []


def strip_author_block_from_document(content: str) -> str:
    frontmatter_block, body, _ = split_mdx_document(content)
    body = strip_author_block(body)
    if body:
        return f"{frontmatter_block}\n{body}"
    return f"{frontmatter_block}\n"


def parse_mdx_frontmatter(path: Path) -> dict[str, object]:
    return parse_frontmatter_text(path.read_text(encoding="utf-8"))


def cell_source(cell: dict) -> str:
    source = cell.get("source", "")
    if isinstance(source, list):
        return "".join(source)
    return source


def parse_notebook_frontmatter(path: Path) -> dict[str, object]:
    notebook = json.loads(path.read_text(encoding="utf-8"))
    first_markdown = next(
        (cell for cell in notebook.get("cells", []) if cell.get("cell_type") == "markdown"),
        None,
    )
    if not first_markdown:
        raise ValueError("notebook has no markdown cells")

    text = cell_source(first_markdown).strip()
    return parse_frontmatter_text(text)


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
