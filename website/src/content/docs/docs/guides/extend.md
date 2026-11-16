---
title: Extending a dataset
description: "Continue a dataset forward in time with marketforge extend, byte-identical to generating the whole range at once."
---

```bash
marketforge extend ./data --to 2025-03-01     # or --days 30
```

```python
mf.extend("./data", "2025-03-01")
```

`extend` takes everything but the new end from the dataset's [manifest](../output/#the-manifest), so the seed, instruments, timeframes, format and overrides cannot drift. Afterwards the dataset holds **exactly the candles one generation up to the new end would have produced**; CSV files are byte-identical to it.

This makes it practical to keep a long-running synthetic feed: generate a year once, then extend it a month at a time, and every consumer sees the same history.

## How it works

The manifest stores a checkpoint: the model state (prices, GARCH variance, regime, volume memory) at the end of the last full day simulated, and the last candle written for every timeframe. `extend` resumes the simulation from that state with the same per-day random streams, so the continuation is the one a single run would have taken.

- CSV files are appended to in place. A Parquet file cannot be appended to, so each one that gets new candles is rewritten.
- An extension is **all-or-nothing**. If it fails or is interrupted, the dataset is left, or put back by the next `extend`, exactly as it was.
- `--dry-run`, `--jobs` and `--no-progress` work as for `generate`.

## Limits

- Datasets go **forward only**. To get an earlier start, generate again.
- Extension works **within a major version**: a seed's candles can differ between major versions, so a dataset written by 4.x is extended by 4.x.
- Datasets written before 4.0 have no manifest and cannot be extended.

See [ADR 0009](../../adr/0009-extend-datasets-from-an-exact-checkpoint/) for the design.
