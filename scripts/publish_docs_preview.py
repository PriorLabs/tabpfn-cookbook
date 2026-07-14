#!/usr/bin/env python3
"""Materialize cookbook markdown into a docs branch for Mintlify previews.

Mintlify only serves files present on the docs branch — it does not run
``fetch-cookbooks.mjs`` with GitHub tokens. This script therefore copies
generated markdown into ``cookbook/``, runs ``npm run sync``, and pushes
the result to a docs preview (or staging) branch.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

DOCS_REPO = "PriorLabs/docs"
SOURCE_FILE = ".cookbooks-source.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docs-dir", type=Path, required=True, help="Checked-out docs repository.")
    parser.add_argument("--base-branch", required=True, help="Docs branch to base the preview on.")
    parser.add_argument(
        "--preview-branch",
        required=True,
        help="Docs branch to create/update (e.g. cookbook/pr-12 or staging branch).",
    )
    parser.add_argument(
        "--markdowns-dir",
        type=Path,
        required=True,
        help="Directory of .mdx cookbook files to copy (usually prior-cookbook/markdowns).",
    )
    parser.add_argument("--cookbooks-repo", required=True, help="owner/repo of the cookbook source.")
    parser.add_argument("--cookbooks-ref", required=True, help="Branch/ref the markdowns came from.")
    parser.add_argument(
        "--pr-number",
        type=int,
        default=None,
        help="Pull request number for commit message (optional for merge refreshes).",
    )
    parser.add_argument(
        "--skip-npm",
        action="store_true",
        help="Skip npm ci / npm run sync (for debugging).",
    )
    return parser.parse_args()


def run(cmd: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
    subprocess.run(cmd, cwd=cwd, check=True, env=env)


def configure_git_identity(docs_dir: Path) -> None:
    run(["git", "config", "user.name", "github-actions[bot]"], cwd=docs_dir)
    run(
        ["git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"],
        cwd=docs_dir,
    )


def copy_markdowns(markdowns_dir: Path, cookbook_dir: Path) -> list[Path]:
    if not markdowns_dir.is_dir():
        raise FileNotFoundError(f"Markdown directory not found: {markdowns_dir}")

    cookbook_dir.mkdir(parents=True, exist_ok=True)
    for path in cookbook_dir.glob("*.mdx"):
        if path.name != "index.mdx":
            path.unlink()

    copied: list[Path] = []
    for source in sorted(markdowns_dir.glob("*.mdx")):
        destination = cookbook_dir / source.name
        shutil.copy2(source, destination)
        copied.append(destination)

    if not copied:
        raise FileNotFoundError(f"No .mdx files found in {markdowns_dir}")

    return copied


def write_source_file(docs_dir: Path, *, repo: str, ref: str) -> None:
    source = {"repo": repo, "ref": ref}
    (docs_dir / SOURCE_FILE).write_text(f"{json.dumps(source, indent=2)}\n", encoding="utf-8")


def run_docs_sync(docs_dir: Path) -> None:
    # Cookbook markdown is already in cookbook/; only regenerate nav / stubs.
    run(["npm", "ci"], cwd=docs_dir)
    run(["npm", "run", "sync"], cwd=docs_dir)


def commit_message(*, pr_number: int | None, repo: str, ref: str) -> str:
    if pr_number is not None:
        return f"Cookbook preview for prior-cookbook#{pr_number} ({repo}@{ref})"
    return f"Refresh cookbooks from {repo}@{ref}"


def stage_preview_files(docs_dir: Path) -> None:
    paths = [
        SOURCE_FILE,
        "cookbook",
        "docs.json",
        "capabilities",
    ]
    run(["git", "add", "-f", *paths], cwd=docs_dir)


def main() -> int:
    args = parse_args()
    docs_dir = args.docs_dir.resolve()
    markdowns_dir = args.markdowns_dir.resolve()
    token = os.environ.get("DOCS_REPO_TOKEN")
    if not token:
        print("DOCS_REPO_TOKEN is required.", file=sys.stderr)
        return 1

    remote = f"https://x-access-token:{token}@github.com/{DOCS_REPO}.git"

    configure_git_identity(docs_dir)
    run(["git", "remote", "set-url", "origin", remote], cwd=docs_dir)
    run(["git", "fetch", "origin", args.base_branch, "--depth", "1"], cwd=docs_dir)
    run(["git", "checkout", "-B", args.preview_branch, f"origin/{args.base_branch}"], cwd=docs_dir)

    write_source_file(docs_dir, repo=args.cookbooks_repo, ref=args.cookbooks_ref)
    copied = copy_markdowns(markdowns_dir, docs_dir / "cookbook")
    print(f"Copied {len(copied)} cookbook file(s) into {docs_dir / 'cookbook'}")

    if not args.skip_npm:
        run_docs_sync(docs_dir)

    stage_preview_files(docs_dir)
    diff = subprocess.run(["git", "diff", "--staged", "--quiet"], cwd=docs_dir, check=False)
    if diff.returncode != 0:
        run(
            [
                "git",
                "commit",
                "-m",
                commit_message(
                    pr_number=args.pr_number,
                    repo=args.cookbooks_repo,
                    ref=args.cookbooks_ref,
                ),
            ],
            cwd=docs_dir,
        )
    else:
        print("No docs changes to commit.")

    run(["git", "push", "origin", args.preview_branch, "--force"], cwd=docs_dir)

    print(f"Pushed docs branch {args.preview_branch}")
    print(f"Cookbook source: {args.cookbooks_repo}@{args.cookbooks_ref}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
