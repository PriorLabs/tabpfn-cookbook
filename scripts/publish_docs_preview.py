#!/usr/bin/env python3
"""Create or update a Mintlify preview branch on the docs repo for a cookbook PR."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS_REPO = "PriorLabs/docs"
SOURCE_FILE = ".cookbooks-source.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docs-dir", type=Path, required=True, help="Checked-out docs repository.")
    parser.add_argument("--base-branch", required=True, help="Docs branch to base previews on.")
    parser.add_argument("--preview-branch", required=True, help="Docs preview branch to create or update.")
    parser.add_argument("--cookbooks-repo", required=True, help="owner/repo for cookbook markdown source.")
    parser.add_argument("--cookbooks-ref", required=True, help="Branch on the cookbook repo to fetch.")
    parser.add_argument("--pr-number", type=int, required=True, help="Pull request number for commit message.")
    return parser.parse_args()


def run(cmd: list[str], *, cwd: Path | None = None) -> None:
    subprocess.run(cmd, cwd=cwd, check=True)


def main() -> int:
    args = parse_args()
    docs_dir = args.docs_dir.resolve()
    token = os.environ.get("DOCS_REPO_TOKEN")
    if not token:
        print("DOCS_REPO_TOKEN is required.", file=sys.stderr)
        return 1

    remote = (
        f"https://x-access-token:{token}@github.com/{DOCS_REPO}.git"
        if token
        else f"https://github.com/{DOCS_REPO}.git"
    )

    run(["git", "remote", "set-url", "origin", remote], cwd=docs_dir)
    run(["git", "fetch", "origin", args.base_branch, "--depth", "1"], cwd=docs_dir)
    run(["git", "checkout", "-B", args.preview_branch, f"origin/{args.base_branch}"], cwd=docs_dir)

    source = {
        "repo": args.cookbooks_repo,
        "ref": args.cookbooks_ref,
    }
    (docs_dir / SOURCE_FILE).write_text(f"{json.dumps(source, indent=2)}\n", encoding="utf-8")

    run(["git", "add", SOURCE_FILE], cwd=docs_dir)
    diff = subprocess.run(["git", "diff", "--staged", "--quiet"], cwd=docs_dir, check=False)
    if diff.returncode != 0:
        run(
            [
                "git",
                "commit",
                "-m",
                (
                    f"Cookbook preview for prior-cookbook#{args.pr_number} "
                    f"({args.cookbooks_repo}@{args.cookbooks_ref})"
                ),
            ],
            cwd=docs_dir,
        )
    run(["git", "push", "origin", args.preview_branch, "--force"], cwd=docs_dir)

    print(f"Pushed docs preview branch {args.preview_branch}")
    print(f"Cookbook source: {args.cookbooks_repo}@{args.cookbooks_ref}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
