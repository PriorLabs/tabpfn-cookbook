# TabPFN Cookbook

Source notebooks for [TabPFN](https://priorlabs.ai) cookbooks. Published on [docs.priorlabs.ai](https://docs.priorlabs.ai) (Cookbook tab).
## Contribute

### Setup

1. Fork [PriorLabs/tabpfn-cookbook](https://github.com/PriorLabs/tabpfn-cookbook) and branch from `main`.
2. Install [uv](https://docs.astral.sh/uv/) and sync the environment once:

```bash
uv sync
```

Prefix the commands below with `uv run` (e.g. `uv run python scripts/validate.py --all`) to run them in that environment.

### Pick a path

| Path | When | Source of truth |
|------|------|-----------------|
| **Notebook** (recommended) | Code walkthroughs | `notebooks/<slug>.ipynb` → generates `markdowns/<slug>.mdx` |
| **Markdown only** | Prose / no runnable notebook | `markdowns/<slug>.mdx` only |

Use a short `slug` (filename without extension), e.g. `my-recipe`.

### Notebook recipe

1. Create `notebooks/<slug>.ipynb` with [frontmatter](#frontmatter) in the **first markdown cell** (`title` + `description` required).
2. Write and **run** the notebook so useful outputs (prints, tables, plots) are saved in the `.ipynb`.
3. Convert (builds MDX, injects authors/Colab, extracts plots into `visuals/<slug>/` only if needed):

```bash
uv run python scripts/convert_to_markdown.py --slug <slug>
```

4. Validate and commit:

```bash
uv run python scripts/validate.py --all
git add notebooks/<slug>.ipynb markdowns/<slug>.mdx visuals/<slug>/
git commit -m "Add <slug> cookbook"
```


**Plots and images:** embedded chart outputs are extracted automatically on convert. For static images, either paste them into a markdown cell (Jupyter stores them as attachments, `![alt](attachment:name.png)`) or add a file under `visuals/<slug>/` and reference it as `![alt](../visuals/<slug>/name.png)`. On convert, attachments are extracted to `visuals/<slug>/name.png` and both forms are rewritten **in the notebook** to the raw GitHub URL of that file:

```markdown
![My chart](https://raw.githubusercontent.com/PriorLabs/tabpfn-cookbook/main/visuals/<slug>/my-chart.png)
```

This is required because Colab ignores cell attachments and cannot resolve relative paths, so those forms show as broken images there. Validation fails if a notebook still contains them. The URL points at `main`, so images in a new cookbook render in Colab once the PR is merged; reviewers can view the files in the PR diff under `visuals/`.

### Markdown-only recipe

1. Create `markdowns/<slug>.mdx` with [frontmatter](#frontmatter).
2. If you set `authors` and/or `colab_url`:

```bash
uv run python scripts/process_markdown.py --slug <slug>
```

3. Validate and commit `markdowns/<slug>.mdx` (do **not** run `convert_to_markdown.py`).

### Open a PR

Push your branch and open a PR against `main`. CI runs the same checks as `validate.py`.

Same-repo PRs get a Mintlify docs preview comment when opened; fork PRs still get validation.

### Commands you’ll use

| Command | When |
|---------|------|
| `uv run python scripts/convert_to_markdown.py --slug <slug>` | After editing a notebook (or `--all`) |
| `uv run python scripts/process_markdown.py --slug <slug>` | After editing `authors` / `colab_url` on a markdown-only recipe |
| `uv run python scripts/validate.py --all` | Before opening or updating a PR |

### Optional frontmatter extras

**Authors**

```yaml
authors:
  - name: Prior Labs
    linkedin: https://www.linkedin.com/company/prior-labs
    twitter: https://twitter.com/prior_labs
```

Social fields: `github`, `linkedin`, `x` (`twitter` is also accepted). Notebooks get the author block from convert; markdown-only needs `process_markdown.py`.

**Colab** — set automatically for notebooks. For markdown-only, set `colab_url` then run `process_markdown.py`.

**YouTube** — in a notebook markdown cell:

```markdown
[youtube: Optional title](https://youtu.be/VIDEO_ID)
```

or a bare YouTube URL on its own line. Markdown-only recipes: paste an `<iframe>` yourself.

Questions? Open an issue or email [hello@priorlabs.ai](mailto:hello@priorlabs.ai).

## Layout

```
notebooks/   # Author notebooks (.ipynb, frontmatter in cell 0)
markdowns/   # Generated or hand-written MDX
visuals/     # Plot images (created by convert when needed)
scripts/     # convert_to_markdown, process_markdown, validate, …
```

## Frontmatter

```markdown
---
title: "Recipe title"
description: "Short summary for the docs site."
icon: "bolt"
cookbookTags:
  - api
feature_in_doc: classification
featured: true
authors:
  - name: Prior Labs
    linkedin: https://www.linkedin.com/company/prior-labs
    twitter: https://twitter.com/prior_labs
---
```

Required: `title`, `description`  
Optional: `icon`, `cookbookTags`, `feature_in_doc`, `featured`, `authors`  
Auto-set for notebooks: `colab_url`

`featured: true` pins the recipe to the top row of the Cookbook index on docs.priorlabs.ai with a highlighted tile and a "Featured" badge. Featured recipes share that top row, so **at most 3** may be featured at once; `validate.py` (and CI) fails if more are set. Omit it (or set `false`) for normal tiles.

## CI (maintainers)

Workflow: `.github/workflows/docs-sync.yml`

| Job | When | What |
|-----|------|------|
| `validate` | Every PR update + push to `main` | Notebooks / markdown / author blocks |
| `publish-docs-preview` | Same-repo PRs only | Mintlify preview on `cookbook/pr-<N>` (comment on open) |
| `publish-docs` | Push to `main` that changes `markdowns/` | Opens docs PR `cookbook/update-<N>` → `DOCS_PREVIEW_BRANCH` |
| `cleanup-docs-preview` | Same-repo PR closed | Deletes `cookbook/pr-*` |

Fork PRs: validate only (no preview).

**Secrets / variables** on `PriorLabs/tabpfn-cookbook`:

| Name | Type | Purpose |
|------|------|---------|
| `DOCS_REPO_TOKEN` | Secret | Contents + Pull requests write on `PriorLabs/docs` |
| `MINTLIFY_API_KEY` | Secret | Mintlify admin API key |
| `MINTLIFY_PROJECT_ID` | Secret | Mintlify project ID |
| `DOCS_PREVIEW_BRANCH` | Variable | Preview base + sync PR target (`tuana/cookbooks-poc` now; `main` at go-live) |
