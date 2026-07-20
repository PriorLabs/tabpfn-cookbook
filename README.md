# TabPFN Cookbook

Source notebooks for TabPFN Cookbooks. Published on [docs.priorlabs.ai](https://docs.priorlabs.ai) (Cookbook tab). Converted to Mintlify MDX and shipped via [PriorLabs/docs](https://github.com/PriorLabs/docs).

## How to contribute

### 1. Fork and branch

1. Fork [PriorLabs/tabpfn-cookbook](https://github.com/PriorLabs/tabpfn-cookbook).
2. Create a branch from `main`, e.g. `git checkout -b my-recipe`.

Install local tooling once:

```bash
pip install -r requirements.txt
```

### 2. Choose how you’ll author the recipe

| Path | Use when | Source of truth |
|------|----------|-----------------|
| **Notebook** (recommended) | Code-heavy walkthroughs | `notebooks/<slug>.ipynb` → generates `markdowns/<slug>.mdx` |
| **Markdown only** | Prose-heavy / hand-authored pages | `markdowns/<slug>.mdx` only |

Pick a short `slug` (filename without extension), e.g. `my-recipe`.

### 3a. Contribute a notebook

1. **Create or edit** `notebooks/<slug>.ipynb`.
2. **Add YAML frontmatter** in the **first markdown cell** (see [Frontmatter](#frontmatter)). At minimum: `title` and `description`.
3. **Write and run** the notebook so useful cell outputs are present (prints, tables). Install/`!pip` noise is stripped on conversion; keep meaningful stdout.
4. **Plots (optional):** if the notebook has chart images you want on the docs site, extract them into `visuals/`:
   - Add an entry for your slug in `scripts/extract_notebook_visuals.py` (`NOTEBOOK_IMAGE_NAMES`: cell index → filename + alt text).
   - Then run:
     ```bash
     python3 scripts/extract_notebook_visuals.py --slug <slug>
     ```
   - That writes PNGs under `visuals/<slug>/` and inserts markdown image cells in the notebook. If you’re unsure, open a PR without plots and ask a maintainer to help wire visuals.
5. **Convert** the notebook to Mintlify MDX (also injects author block + Colab button when applicable):
   ```bash
   python3 scripts/convert_to_markdown.py --slug <slug>
   ```
6. **Validate**:
   ```bash
   python3 scripts/validate.py --all
   ```
7. **Commit** the notebook, generated markdown, and any new visuals:
   ```bash
   git add notebooks/<slug>.ipynb markdowns/<slug>.mdx visuals/<slug>/
   git commit -m "Add <slug> cookbook"
   ```

Do **not** hand-edit `markdowns/<slug>.mdx` for notebook recipes — re-run `convert_to_markdown.py` after notebook changes.

### 3b. Contribute markdown only (no notebook)

1. **Create** `markdowns/<slug>.mdx` with [frontmatter](#frontmatter) at the top.
2. If you set `authors` and/or `colab_url`, inject the Mintlify blocks:
   ```bash
   python3 scripts/process_markdown.py --slug <slug>
   ```
3. **Validate**:
   ```bash
   python3 scripts/validate.py --all
   ```
4. **Commit** `markdowns/<slug>.mdx` (do **not** run `convert_to_markdown.py` for these).

### 4. Open a pull request

1. Push your branch and open a PR against `main`.
2. In the PR description, say what the recipe teaches and who it’s for.
3. CI runs the same checks as `validate.py`. Fix any failures locally and push again.

A maintainer will review. Same-repo PRs get a Mintlify docs preview comment when opened; fork PRs still get validation.

### Script cheat sheet

| Script | When to run |
|--------|-------------|
| `python3 scripts/convert_to_markdown.py --slug <slug>` | After editing a **notebook** (or `--all`) |
| `python3 scripts/process_markdown.py --slug <slug>` | After editing `authors` / `colab_url` on a **markdown-only** recipe |
| `python3 scripts/extract_notebook_visuals.py --slug <slug>` | To pull plot images out of a notebook into `visuals/` |
| `python3 scripts/validate.py --all` | Before opening or updating a PR |

### What we look for

- Clear title and description so readers know what they’ll learn
- Runnable or realistic code examples where applicable
- Links to related docs pages when helpful
- Recipes that fit existing tags (`api`, `use-case`, `interpretability`, `integration`, etc.) or a short note in the PR if you’re introducing a new topic

### Optional recipe features

**Authors** — add to frontmatter:

```yaml
authors:
  - name: Alex Rivera
    github: https://github.com/priorlabs
    linkedin: https://www.linkedin.com/company/prior-labs
    twitter: https://twitter.com/priorlabs
```

Supported social fields: `github`, `linkedin`, `x` (`twitter` is also accepted for X). For notebooks, author blocks are injected by `convert_to_markdown.py`. For markdown-only, run `process_markdown.py` after changing authors.

**Open in Colab** — for notebooks, `colab_url` is set automatically by `convert_to_markdown.py`. Do not set it by hand. Markdown-only recipes may set `colab_url` and then run `process_markdown.py`.

**YouTube** — in a notebook markdown cell:

```markdown
[youtube: Optional title](https://youtu.be/VIDEO_ID)
```

or a bare YouTube URL on its own line. Conversion turns these into embeds. For markdown-only recipes, paste the `<iframe>` embed yourself.

Questions? Open an issue or email [hello@priorlabs.ai](mailto:hello@priorlabs.ai).

## Layout

```
notebooks/     # Author recipes here (.ipynb with YAML frontmatter in cell 0)
markdowns/     # Generated MDX (or hand-written MDX without a notebook)
visuals/       # Plot images referenced from notebooks / markdowns
scripts/
  convert_to_markdown.py
  process_markdown.py
  extract_notebook_visuals.py
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
colab_url: "https://colab.research.google.com/github/PriorLabs/tabpfn-cookbook/blob/main/notebooks/my-recipe.ipynb"
---
```

Required: `title`, `description`  
Optional: `icon`, `cookbookTags`, `feature_in_doc`, `authors`  
Auto-set for notebooks by `convert_to_markdown.py`: `colab_url`

## CI

Pull requests and pushes to `main` run `.github/workflows/docs-sync.yml`:

### Job 1 — `validate`
Runs on every cookbook PR update and every push to `main`. Checks notebooks, markdown, and author blocks.

### Job 2 — `publish-docs-preview` (same-repo PRs only)
After validation passes, **on every PR commit** (`synchronize`):

1. Clones your staging docs branch (`DOCS_PREVIEW_BRANCH`).
2. Creates/updates `cookbook/pr-<N>` on `docs`.
3. **Copies this PR’s `markdowns/*.mdx` into `docs/cookbook/`**, runs `npm run sync`, and commits the result.
4. Triggers a Mintlify preview for `cookbook/pr-<N>`.
5. On **PR opened** only, posts a comment with the Mintlify `previewUrl`. Later pushes update the same preview branch without re-commenting.

**Fork PRs are skipped** for preview (validate still runs). A maintainer-only manual dispatch will come later.

### Job 3 — `publish-docs` (merge to `main` only)
After a push to `main` that **changes `markdowns/`**:

1. Copies **`main`’s** `markdowns/` onto `cookbook/update-<merged-pr-number>` on `docs`.
2. Opens or updates a PR into `DOCS_PREVIEW_BRANCH` (`tuana/cookbooks-poc` for now; set the variable to `main` at go-live).
3. If the result already matches the docs base (e.g. a revert), closes any stale open sync PR instead of leaving an outdated diff.

Pushes that only touch scripts/CI/etc. do **not** open a docs PR.

### Job 4 — `cleanup-docs-preview` (same-repo PR closed)
Deletes the temporary `cookbook/pr-*` branch on `docs`.

**Job 2 vs job 3:** Job 2 = temporary Mintlify preview of *this PR’s* cookbooks. Job 3 = open a docs PR to publish cookbooks from *main*.

### Repository secrets and variables

Configure in **Settings → Secrets and variables → Actions** on this repository (`PriorLabs/tabpfn-cookbook`):

| Name | Type | Purpose |
|------|------|---------|
| `DOCS_REPO_TOKEN` | **Secret** | Push preview/sync branches and open PRs on `PriorLabs/docs` |
| `MINTLIFY_API_KEY` | **Secret** | Mintlify admin API key (`mint_…`) |
| `MINTLIFY_PROJECT_ID` | **Secret** | Mintlify project ID |
| `DOCS_PREVIEW_BRANCH` | **Variable** | Docs branch for PR previews + target of post-merge sync PRs (`tuana/cookbooks-poc` now; `main` at go-live) |

Validation rules:

- **Notebook changed** → fails if `markdowns/` is not up to date (run `convert_to_markdown.py`, which includes author blocks)
- **Authors in frontmatter** → fails if the rendered author block is missing or out of date
- **Markdown only changed** → validates frontmatter and injected author/Colab blocks (run `process_markdown.py` when `authors` or `colab_url` is set)
