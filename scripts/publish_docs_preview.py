#!/usr/bin/env python3
"""Materialize cookbook markdown into a docs branch for Mintlify.

Mintlify only serves files present on the docs branch — it does not run
``fetch-cookbooks.mjs`` with GitHub tokens. This script therefore copies
generated markdown into ``cookbook/``, runs ``npm run sync``, and pushes
the result to a bot-managed docs branch.

Modes:

* Ephemeral preview (``--preview-branch cookbook/pr-<N> --force-push``):
  force-push a throwaway branch and let the caller trigger a Mintlify preview.
* Publish via PR (``--open-pr``): force-push a bot-managed sync branch and
  open/reuse a pull request into ``--base-branch``. Skips push and PR when
  cookbooks are already in sync. The base branch is never written to directly.
* Direct publish: pass the same value for ``--base-branch`` and
  ``--preview-branch`` (plain push, no ``--force-push``). Unused by CI today;
  kept for local/manual use.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

DOCS_REPO = "PriorLabs/docs"


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
        "--open-pr",
        action="store_true",
        help=(
            "Open (or reuse) a pull request from --preview-branch into --base-branch "
            "on the docs repo instead of publishing straight to the base branch. "
            "Requires the gh CLI and GH_TOKEN in the environment."
        ),
    )
    parser.add_argument(
        "--force-push",
        action="store_true",
        help=(
            "Force-push the target branch. Use only for ephemeral bot branches "
            "(e.g. cookbook/pr-<N>). A direct push to a shared branch (Option A) "
            "should omit this so a diverged branch is rejected instead of clobbered. "
            "Implied when --open-pr is set."
        ),
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


def run_docs_sync(docs_dir: Path) -> None:
    # Cookbook markdown is already in cookbook/; only regenerate nav / stubs.
    run(["npm", "ci"], cwd=docs_dir)
    run(["npm", "run", "sync"], cwd=docs_dir)


def commit_message(*, pr_number: int | None, repo: str, ref: str) -> str:
    if pr_number is not None:
        return f"Cookbook preview for prior-cookbook#{pr_number} ({repo}@{ref})"
    return f"Refresh cookbooks from {repo}@{ref}"


def write_github_output(**values: str) -> None:
    """Expose step outputs to the surrounding GitHub Actions job (no-op locally)."""
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as handle:
        for key, value in values.items():
            handle.write(f"{key}={value}\n")


def ensure_pull_request(*, base: str, head: str, title: str, body: str) -> tuple[str, bool]:
    """Return (pr_url, created). Reuses an open PR if one already targets base<-head."""
    existing = subprocess.run(
        [
            "gh", "pr", "list",
            "-R", DOCS_REPO,
            "--head", head,
            "--base", base,
            "--state", "open",
            "--json", "url",
            "--jq", ".[0].url // \"\"",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if existing:
        return existing, False

    created = subprocess.run(
        [
            "gh", "pr", "create",
            "-R", DOCS_REPO,
            "--head", head,
            "--base", base,
            "--title", title,
            "--body", body,
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    url = created.splitlines()[-1] if created else ""
    return url, True


def stage_preview_files(docs_dir: Path) -> None:
    paths = [
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

    if args.open_pr and args.preview_branch == args.base_branch:
        print(
            "--open-pr requires --preview-branch to differ from --base-branch so the "
            "base branch (e.g. main) is never written to directly.",
            file=sys.stderr,
        )
        return 1

    remote = f"https://x-access-token:{token}@github.com/{DOCS_REPO}.git"

    configure_git_identity(docs_dir)
    run(["git", "remote", "set-url", "origin", remote], cwd=docs_dir)
    run(["git", "fetch", "origin", args.base_branch, "--depth", "1"], cwd=docs_dir)
    run(["git", "checkout", "-B", args.preview_branch, f"origin/{args.base_branch}"], cwd=docs_dir)

    copied = copy_markdowns(markdowns_dir, docs_dir / "cookbook")
    print(f"Copied {len(copied)} cookbook file(s) into {docs_dir / 'cookbook'}")

    if not args.skip_npm:
        run_docs_sync(docs_dir)

    stage_preview_files(docs_dir)
    diff = subprocess.run(["git", "diff", "--staged", "--quiet"], cwd=docs_dir, check=False)
    changed = diff.returncode != 0
    if changed:
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

    # Force-push only for ephemeral bot branches (--force-push) or PR sync
    # branches (--open-pr). A direct push to a shared branch is a plain push so a
    # diverged branch is rejected rather than clobbered. For --open-pr with no
    # content changes, skip push and PR entirely.
    if args.open_pr and not changed:
        print(f"No cookbook changes relative to {args.base_branch}; skipping push and PR.")
        write_github_output(
            head_branch=args.preview_branch,
            changed="false",
            pr_url="",
            pr_created="false",
        )
        return 0

    push_cmd = ["git", "push", "origin", args.preview_branch]
    if args.force_push or args.open_pr:
        push_cmd.append("--force")
    run(push_cmd, cwd=docs_dir)
    print(f"Pushed docs branch {args.preview_branch}")
    print(f"Cookbook source: {args.cookbooks_repo}@{args.cookbooks_ref}")

    pr_url = ""
    pr_created = False
    if args.open_pr:
        title = f"Sync cookbooks from {args.cookbooks_repo}@{args.cookbooks_ref}"
        body = (
            f"Automated cookbook sync from `{args.cookbooks_repo}@{args.cookbooks_ref}`.\n\n"
            f"Merging this PR publishes the latest cookbooks to `{args.base_branch}` "
            f"on `{DOCS_REPO}`."
        )
        pr_url, pr_created = ensure_pull_request(
            base=args.base_branch,
            head=args.preview_branch,
            title=title,
            body=body,
        )
        action = "Opened" if pr_created else "Updated existing"
        print(f"{action} docs PR into {args.base_branch}: {pr_url or '(no url returned)'}")

    write_github_output(
        head_branch=args.preview_branch,
        changed=str(changed).lower(),
        pr_url=pr_url,
        pr_created=str(pr_created).lower(),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
