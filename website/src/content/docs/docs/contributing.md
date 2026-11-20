---
title: "Contributing"
description: "How to set up a development environment, the checks CI runs, and how releases happen."
---

MarketForge is free software under the Apache-2.0 licence, developed on [GitHub](https://github.com/DamienReichhart/marketforge). Issues, measurements on real data and pull requests are welcome.

## Development setup

```bash
git clone https://github.com/DamienReichhart/marketforge && cd marketforge
python -m pip install -U "pip>=25.1"    # --group needs pip 25.1
pip install -e . --group dev            # or: uv pip install -e . --group dev
pre-commit install                      # ruff on every commit
```

Work on the `dev` branch. `main` only changes when a release is made.

## Checks

The same checks CI runs, with [nox](https://nox.thea.codes/):

```bash
nox                     # lint, typecheck and tests
nox -s docs examples    # this site's code blocks and examples/, against a built wheel
```

or by hand: `ruff check . && ruff format --check . && lint-imports`, `mypy marketforge` and `pytest`.

- `lint-imports` enforces the package layering: `cli` → `api` → `aggregation | output | validation` → `simulation` → `config` → `calendars` → `domain`. A package may import from the ones below it, never above.
- CI also fails if any seed's output differs from the latest release without a `MODEL_REVISION` increment and an *Output changes* changelog section: see [Reproducibility](../reference/reproducibility/).
- CI also fails if the code is more than 15% slower than the latest release on any of a fixed set of workloads. A slowdown that buys something is declared with an `Accept-Slowdown: 25%` trailer in a commit message.
- The code blocks of these pages and of the README are run in CI against the built package. Mark a block that is too long to run, or that needs the reader's own data, with `check=static` after its language (` ```python check=static `): it is then checked against the API without running.
- Commits follow [Conventional Commits](https://www.conventionalcommits.org/). A commit that breaks the public API is marked `feat!:` (or `fix!:`, `refactor!:`, `build!:`, ...) or has a `BREAKING CHANGE:` footer, and blocks a release that is not a major bump. `docs`, `ci`, `test`, `style` and `chore` commits never count as breaking.

## The website

This site lives in `website/` (Astro and Starlight). The changelog, the glossary and the design decisions are copied from the repository's own `CHANGELOG.md`, `GLOSSARY.md` and `docs/adr/` at build time, so edit those files, not their copies.

```bash
cd website
npm ci
npm run dev        # http://localhost:4321/marketforge/
npm run check      # astro check: what CI type-checks
```

The landing page's chart is real output, written by `website/scripts/hero_sample.py`.

## Releases

To release: bump `[project].version` in `pyproject.toml`, add a `## <version>` section to `CHANGELOG.md`, and merge `dev` into `main`. The CD pipeline publishes to PyPI, creates the GitHub release, and deploys this website. See [`docs/ci-cd.md`](https://github.com/DamienReichhart/marketforge/blob/main/docs/ci-cd.md).

## Design decisions

Significant decisions are recorded as [architecture decision records](../adr/0001-simulate-whole-market-day-by-day/), and the vocabulary in the [glossary](../reference/glossary/).
