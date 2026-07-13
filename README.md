# Prior Cookbooks

Source notebooks for Prior Labs documentation recipes. Notebooks are converted to Mintlify MDX and published via the [docs](https://github.com/PriorLabs/docs) repository.

## Contributing

We welcome recipe contributions from the community. Published recipes appear on [docs.priorlabs.ai](https://docs.priorlabs.ai) under the Cookbook tab.

Every recipe needs **YAML frontmatter** so it can be published on the docs site. Add it in:

- **Notebooks** — first markdown cell of `notebooks/*.ipynb`
- **Markdown-only recipes** — top of `markdowns/*.mdx`

**Required:** `title`, `description`  
**Optional:** `icon`, `cookbookTags`, `feature_in_doc`, `authors`

See [Frontmatter](#frontmatter) for the full template and field descriptions.

### Authors (optional)

Add `authors` to frontmatter in a notebook or markdown file:

```yaml
authors:
  - name: Alex Rivera
    github: https://github.com/priorlabs
    linkedin: https://www.linkedin.com/company/prior-labs
    twitter: https://twitter.com/priorlabs
```

Supported social fields: `github`, `linkedin`, `x` (`twitter` is also accepted for X).

- **Notebook recipes** — author blocks are added when you run `convert_to_markdown.py` (included automatically).
- **Markdown-only recipes** — after adding or editing `authors` in frontmatter, run `process_markdown.py`.

Validation fails if `authors` is in frontmatter but the rendered author block is missing or out of date.

### Embedded videos

Recipes can include YouTube walkthroughs. In a **notebook** markdown cell, use either:

```markdown
[youtube: Optional title](https://youtu.be/VIDEO_ID)
```

or put a YouTube URL on its own line:

```markdown
https://youtu.be/VIDEO_ID
```

`convert_to_markdown.py` turns these into Mintlify-ready `<iframe>` embeds ([docs](https://www.mintlify.com/docs/create/image-embeds)). See `notebooks/api-quickstart.ipynb` for a live example.

For **markdown-only** recipes, paste the same `<iframe>` block directly into `markdowns/*.mdx`.

### How to contribute

1. **Fork** this repository and create a branch from `main`.
2. **Add or edit a recipe** using one of the two paths below.
3. **Validate locally** before opening a pull request:
   ```bash
   python3 scripts/validate.py --all
   ```
4. **Open a pull request** with a short description of what the recipe covers and who it’s for.

A maintainer will review your PR. CI runs the same checks as `validate.py` — if it passes, you’re in good shape.

### Two ways to add a recipe

**Option A — Notebook (recommended for code-heavy recipes)**

1. Add or edit a file in `notebooks/`, e.g. `notebooks/my-recipe.ipynb`.
2. Add [frontmatter](#frontmatter) to the **first markdown cell**.
3. Run the converter and commit:
   ```bash
   python3 scripts/convert_to_markdown.py --slug my-recipe
   git add notebooks/my-recipe.ipynb markdowns/my-recipe.mdx
   ```

**Option B — Markdown only (for prose-heavy or hand-authored recipes)**

1. Add `markdowns/my-recipe.mdx` with [frontmatter](#frontmatter) at the top.
2. If you set `authors`, run `python3 scripts/process_markdown.py --slug my-recipe`.
3. No notebook or conversion step otherwise — CI validates frontmatter and author blocks.

### What we look for

- Clear title and description so readers know what they’ll learn
- Runnable or realistic code examples where applicable
- Links to related docs pages when helpful
- Recipes that fit existing tags (`api`, `use-case`, `interpretability`, `integration`, etc.) or a short note in the PR if you’re introducing a new topic

Questions or ideas before you start? Open an issue or reach us at [hello@priorlabs.ai](mailto:hello@priorlabs.ai).

## Layout

```
notebooks/     # Author recipes here (.ipynb with YAML frontmatter in cell 0)
markdowns/     # Generated MDX (or hand-written MDX without a notebook)
scripts/
  convert_to_markdown.py
  process_markdown.py
  validate.py
```

## Frontmatter

The first markdown cell of each notebook (or the top of each `.mdx` file) must include:

```markdown
---
title: "Recipe title"
description: "Short summary for the docs site."
icon: "bolt"
cookbookTags:
  - api
feature_in_doc: classification
authors:
  - name: Alex Rivera
    github: https://github.com/priorlabs
    linkedin: https://www.linkedin.com/company/prior-labs
---
```

Required: `title`, `description`  
Optional: `icon`, `cookbookTags`, `feature_in_doc`, `authors`

## Workflow

### Edit a notebook

```bash
# edit notebooks/my-recipe.ipynb
python3 scripts/convert_to_markdown.py --all   # or --slug my-recipe
git add notebooks/ markdowns/
```

### Add markdown only (no notebook)

Create `markdowns/my-recipe.mdx` directly with valid frontmatter. If you set `authors`, run:

```bash
python3 scripts/process_markdown.py --slug my-recipe   # or --all
```

### Validate locally

```bash
python3 scripts/validate.py --all
```

On a branch with changes:

```bash
python3 scripts/validate.py
```

## CI

Pull requests and pushes to `main` run `.github/workflows/docs-sync.yml`:

### Job 1 — `validate`
Runs on every cookbook PR update and every push to `main`. Checks notebooks, markdown, and author blocks.

### Job 2 — `publish-docs-preview` (PRs only)
After validation passes:

1. Clones your **staging docs branch** (`DOCS_PREVIEW_BRANCH` — the branch that already has the fetch-at-build setup).
2. Creates/updates a **per-PR branch** on `docs`, e.g. `cookbook/pr-42`.
3. Commits only `.cookbooks-source.json` pointing at the PR’s cookbook repo + branch (works for forks).
4. Triggers a **Mintlify preview** for that `cookbook/pr-*` branch.

When Mintlify builds that branch, `fetch-cookbooks.mjs` reads `.cookbooks-source.json` and pulls `markdowns/` from the **PR branch** (not `main`).

### Job 3 — `refresh-docs-preview` (merge to `main` only)
After cookbooks land on `prior-cookbook` `main`, redeploys your **staging** docs branch (`DOCS_PREVIEW_BRANCH`). That branch has no `.cookbooks-source.json`, so the build pulls cookbooks from `prior-cookbook` `main`.

### Job 4 — `cleanup-docs-preview` (PR closed)
Deletes the temporary `cookbook/pr-*` branch on `docs`.

**Job 2 vs job 3:** Job 2 is *per open PR* → temporary preview with that PR’s cookbooks. Job 3 is *after merge* → refresh your long-lived staging preview with the latest cookbooks on `main`.

### Repository secrets and variables

Configure in **Settings → Secrets and variables → Actions** on `prior-cookbook`:

| Name | Type | Purpose |
|------|------|---------|
| `DOCS_REPO_TOKEN` | **Secret** | Push preview branches to `PriorLabs/docs` |
| `MINTLIFY_API_KEY` | **Secret** | Mintlify admin API key (`mint_…`) |
| `MINTLIFY_PROJECT_ID` | **Secret** | Mintlify project ID |
| `DOCS_PREVIEW_BRANCH` | **Variable** | Your staging docs branch (base for previews + target for post-merge redeploy) |

On `PriorLabs/docs`, set `COOKBOOKS_GITHUB_TOKEN` if cookbook sources are private.

Validation rules:

- **Notebook changed** → fails if `markdowns/` is not up to date (run `convert_to_markdown.py`, which includes author blocks)
- **Authors in frontmatter** → fails if the rendered author block is missing or out of date
- **Markdown only changed** → validates frontmatter and author blocks (run `process_markdown.py` when `authors` is set)
