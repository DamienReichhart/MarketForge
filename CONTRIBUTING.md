# Contributing to MarketForge

Issues, measurements on real data and pull requests are welcome.

## The most useful contribution: real-data measurements

The forex and stocks validation bands are provisional: they are not yet measured on real minute data. If you can run `marketforge validate your_real_m1.csv --market forex --json` on data you are allowed to use, [open a realism report](https://github.com/DamienReichhart/marketforge/issues/new?template=realism.yml) with the statistics. Never attach the raw data itself.

## Set up

```bash
git clone https://github.com/DamienReichhart/marketforge && cd marketforge
python -m pip install -U "pip>=25.1"    # --group needs pip 25.1; Debian's pip 24 fails
pip install -e . --group dev            # or: uv pip install -e . --group dev
pre-commit install                      # ruff on every commit
```

## Before you push

```bash
nox                     # lint, typecheck and tests, as CI runs them
nox -s tests-3.13 -- tests/api -x    # one Python, some tests
nox -s docs examples    # the documentation's code blocks and examples/, slower
```

Without nox, the same checks are `ruff check . && ruff format --check . && lint-imports`, `mypy marketforge` and `pytest`.

## Rules that CI enforces

- Commits follow [Conventional Commits](https://www.conventionalcommits.org/). Mark a break of the public API with `type!:` or a `BREAKING CHANGE:` footer.
- **A change that alters what a seed produces** must increment `MODEL_REVISION` in `marketforge/_version.py` and list the change under `### Output changes` in `CHANGELOG.md` ([ADR 0011](docs/adr/0011-realism-over-seed-stability.md)). Judge it against the validation bands (`python scripts/benchmark_realism.py`).
- Changing a catalog's stated correlations or volatilities needs `python scripts/fit_correlations.py`.
- Open pull requests against `dev`. The maintainer bumps the version and writes the release notes when `dev` is merged into `main`, which releases.

More on the pipeline is in [`docs/ci-cd.md`](docs/ci-cd.md), design decisions are in [`docs/adr/`](docs/adr/), and the vocabulary is in [`GLOSSARY.md`](GLOSSARY.md). Report security issues privately: see [`SECURITY.md`](SECURITY.md).
