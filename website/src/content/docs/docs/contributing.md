---
title: "Contributing"
description: "How to set up a development environment, the checks CI runs, and how releases happen."
---

MarketForge is free software under the AGPL-3.0-or-later, developed on [GitHub](https://github.com/DamienReichhart/MarketForge). Issues, measurements on real data and pull requests are welcome.

## Development setup

```bash
git clone https://github.com/DamienReichhart/MarketForge && cd MarketForge
pip install -e . --group dev          # or: uv pip install -e . --group dev
```

Work on the `dev` branch. `main` only changes when a release is made.

## Checks

The same checks CI runs:

```bash
ruff check . && ruff format --check . && lint-imports
mypy marketforge
pytest --cov
```

- `lint-imports` enforces the package layering: `cli` → `api` → `aggregation | output | validation` → `simulation` → `config` → `calendars` → `domain`. A package may import from the ones below it, never above.
- CI also fails if any seed's output differs from the latest release without a major version bump: see [Reproducibility](../reference/reproducibility/).
- Commits follow [Conventional Commits](https://www.conventionalcommits.org/). A commit marked breaking (`feat!:` or a `BREAKING CHANGE:` footer) blocks a release that is not a major bump.

## The website

This site lives in `website/` (Astro and Starlight). The changelog, the glossary and the design decisions are copied from the repository's own `CHANGELOG.md`, `GLOSSARY.md` and `docs/adr/` at build time, so edit those files, not their copies.

```bash
cd website
npm ci
npm run dev        # http://localhost:4321/MarketForge/
```

The landing page's chart is real output, written by `website/scripts/hero_sample.py`.

## Releases

To release: bump `[project].version` in `pyproject.toml`, add a `## <version>` section to `CHANGELOG.md`, and merge `dev` into `main`. The CD pipeline publishes to PyPI, creates the GitHub release, and deploys this website. See [`docs/ci-cd.md`](https://github.com/DamienReichhart/MarketForge/blob/main/docs/ci-cd.md).

## Design decisions

Significant decisions are recorded as [architecture decision records](../adr/0001-simulate-whole-market-day-by-day/), and the vocabulary in the [glossary](../reference/glossary/).
