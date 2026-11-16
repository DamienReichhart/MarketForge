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

`numpy` (2.2 or newer), `numba`, `scipy`, `pandas`, `pyarrow` (for Parquet), `click`, `tqdm` and `threadpoolctl`. CI tests every one of them at the lowest version declared, so the floors in `pyproject.toml` are real.

## From source

To change the code, or to run the test suite:

```bash
git clone https://github.com/DamienReichhart/MarketForge && cd MarketForge
pip install -e . --group dev        # pip 25.1 or newer (PEP 735 dependency groups)
pytest
```

See [Contributing](../contributing/) for the checks CI runs.

## Verifying a release

Every release is built and published by GitHub Actions through PyPI trusted publishing, with signed build-provenance and SBOM attestations:

```bash
gh attestation verify marketforge-<version>-py3-none-any.whl --repo DamienReichhart/MarketForge
```
