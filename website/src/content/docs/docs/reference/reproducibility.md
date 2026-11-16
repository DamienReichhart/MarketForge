---
title: "Reproducibility"
description: "The reproducibility contract: what a seed fixes, what it does not, and when candles may change."
---

For a given MarketForge **major version**, `(seed, market, minute)` fully determines every random shock. Output is identical regardless of:

- which instruments are selected, and how many;
- the timeframes;
- the output format (CSV, Parquet or in memory);
- `--jobs`;
- whether the spread or the regime is requested;
- how far `--to` extends;
- whether the range was generated at once or [extended](../../guides/extend/) in steps.

The same seed gives the same EURUSD whether you generate it alone or with 207 other instruments. Changes that alter output for an existing seed only ship in a **new major version**.

## How it is enforced

On every commit, CI fingerprints (SHA-256) 786 outputs of fixed-seed scenarios (every instrument, CSV bytes and in-memory frames, all timeframes, anomalies, regime labels, both DST transitions, a leap day) with the code under test and with the latest PyPI release, in the same environment, and fails on any difference unless the major version was bumped. See [ADR 0006](../../adr/0006-validation-bands-are-the-realism-contract/) and [ADR 0007](../../adr/0007-optimise-without-changing-a-single-bit/).

## Across machines

Candle values are bit-for-bit identical on a given platform and NumPy build. Across machines they can differ in the last bit before rounding: NumPy picks its `exp`/`log` implementation by CPU (for example AVX-512), and those differ by one ulp on a small fraction of inputs.

NumPy 2.2 or newer is required: older releases break the contract (extending the range changed earlier candles by about 1e-14).

## For experiments

To make an experiment reproducible from MarketForge data, record:

1. the MarketForge version (at least the major version);
2. the seed;
3. the range, instruments and options, or simply keep the dataset's `marketforge.json`, which holds all of them, including the resolved overrides.
