---
title: "Reproducibility"
description: "What a seed fixes, what it does not, and when candles may change between releases."
---

For a given MarketForge **version**, `(seed, market, minute)` fully determines every random shock. Output is identical regardless of:

- which instruments are selected, and how many;
- the timeframes;
- the output format (CSV, Parquet or in memory);
- `--jobs`;
- whether the spread or the regime is requested;
- how far `--to` extends;
- whether the range was generated at once or [extended](../../guides/extend/) in steps.

The same seed gives the same EURUSD whether you generate it alone or with 207 other instruments.

## Releases can change a seed's candles

**Realism comes before seed stability.** Any release, minor or patch included, may change the candles a seed produces when that makes the data more realistic. The changelog lists every such change under **Output changes**, and the package's `MODEL_REVISION` goes up by one. A dataset's `marketforge.json` records the version and the model revision that made it, so you can always tell which model wrote a file.

Two things follow:

- **To keep an experiment identical, pin the version** (`pip install marketforge==4.0.0`).
- **`extend` only continues a dataset written by the same model revision**, because a checkpoint from another model cannot be continued exactly. Generate again, or install the version the dataset records.

Major versions are for breaks of the public API (renamed options, removed functions), not for output.

## How it is enforced

On every commit, CI fingerprints (SHA-256) 786 outputs of fixed-seed scenarios (every instrument, CSV bytes and in-memory frames, all timeframes, anomalies, regime labels, both DST transitions, a leap day) with the code under test and with the latest PyPI release, in the same environment. A difference is accepted only when `MODEL_REVISION` was incremented and the changelog has an *Output changes* section for the version; otherwise the commit fails. See [ADR 0011](../../adr/0011-realism-over-seed-stability/) and [ADR 0007](../../adr/0007-optimise-without-changing-a-single-bit/).

## Across machines

Candle values are bit-for-bit identical on a given platform and NumPy build. Across machines they can differ in the last bit before rounding: NumPy picks its `exp`/`log` implementation by CPU (for example AVX-512), and those differ by one ulp on a small fraction of inputs. "Reproducible" therefore means the same version on the same kind of machine; across machines expect agreement to rounding, not byte equality.

NumPy 2.2 or newer is required: older releases change earlier candles when the range is extended (by about 1e-14).

## For experiments

To make an experiment reproducible from MarketForge data, record:

1. the exact MarketForge version;
2. the seed;
3. the range, instruments and options, or simply keep the dataset's `marketforge.json`, which holds all of them, including the resolved overrides.
