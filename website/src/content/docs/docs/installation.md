---
title: Installation
description: "Install MarketForge from PyPI or from source. Python 3.12 or newer."
---

MarketForge is a pure-Python package with compiled [Numba](https://numba.pydata.org/) kernels. It needs **Python 3.12 or newer** and runs on Linux, macOS and Windows.

## From PyPI

```bash
pip install marketforge
marketforge --version
```

With [uv](https://docs.astral.sh/uv/):

```bash
uv pip install marketforge
```

The first generation in a fresh environment takes a few extra seconds while Numba compiles the kernels; they are cached afterwards.

### Dependencies

`numpy` (2.2 or newer), `numba`, `pandas`, `pyarrow` (CSV, Parquet and Feather writing), `click`, `tqdm` and `threadpoolctl`. scipy is not needed: it is only used offline, to refit the catalogs' correlations. CI tests every one of them at the lowest version declared, so the floors in `pyproject.toml` are real.

## In the browser

The [Playground](../../playground/) runs MarketForge in your browser with [Pyodide](https://pyodide.org/), with nothing to install. There Numba is not available, so the kernels run as plain Python: the page is 10 to 100 times slower than an installed MarketForge, caps the size of a request, and its candles are not bit-identical to an installed version's for the same seed. Use it to try MarketForge; generate the datasets you rely on with the installed package. The playground lists [its limits](../../playground/#web-version-vs-installed-version) in full.

## From source

To change the code, or to run the test suite:

```bash
git clone https://github.com/DamienReichhart/marketforge && cd marketforge
pip install -e . --group dev        # pip 25.1 or newer (PEP 735 dependency groups)
pytest
```

See [Contributing](../contributing/) for the checks CI runs.

## Verifying a release

Every release is built and published by GitHub Actions through PyPI trusted publishing, with signed build-provenance and SBOM attestations:

```bash
gh attestation verify marketforge-<version>-py3-none-any.whl --repo DamienReichhart/marketforge
```
