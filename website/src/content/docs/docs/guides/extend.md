---
title: Extending and verifying
description: "Inspect a dataset with marketforge info, continue it forward in time with marketforge extend, exactly as one longer run, and prove it unaltered with marketforge verify."
---

Every dataset carries its [manifest](../../reference/output/#the-manifest), `marketforge.json`: the version, seed, range, instruments, options and resolved overrides that made it, and a checkpoint of the model's state at its end. Three commands use it.

| Command | Question it answers |
| --- | --- |
| [`marketforge info`](#inspect-a-dataset) | What is this dataset, and can this MarketForge extend it? |
| [`marketforge extend`](#extend-a-dataset) | Can I have more of it, exactly as if I had asked for a longer range? |
| [`marketforge verify`](#verify-a-dataset) | Is it still exactly what its manifest says it is? |

## Inspect a dataset

```bash check=static
marketforge info ./data
```

```text title="Output"
Dataset ./data
  Written by  MarketForge 5.0.0 (model revision 2)
  Seed        42
  Range       2024-01-01 00:00 UTC -> 2024-04-01 00:00 UTC
  crypto      3 instrument(s): BTCUSD, ETHUSD, SOLUSD
  Files       24 csv files, 25.4 MB; timeframes m1, m5, m15, m30, H1, H4, D1, W1
  Can extend  yes
```

It reads only the manifest, so it is instant whatever the size of the dataset. `--json` prints the same for scripts. When the answer to *Can extend* is no, it names the version that can.

## Extend a dataset

```bash check=static
marketforge extend ./data --to 2025-03-01     # or --days 30
```

```python check=static
mf.extend("./data", "2025-03-01")
```

`extend` takes everything but the new end from the manifest, so the seed, instruments, timeframes, format, columns and overrides cannot drift. Afterwards the dataset holds **exactly the candles one generation up to the new end would have produced**. CSV files are byte-identical to it; Parquet and Feather files hold identical values, but keep their earlier row groups, so their bytes differ from a file written in one go.

That makes it practical to keep a long-running synthetic feed: generate a year once, then extend it a month at a time, and every consumer sees the same history. It is also how to build a long dataset in steps you can schedule.

### How it works

The checkpoint is the model's state (prices, GARCH variance, regime, volume memory) at the end of the last full day simulated, and the last candle written for every timeframe. `extend` resumes the simulation from that state with the same per-day random streams, so the continuation is the one a single run would have taken. Candles that were partial at the old end, a `W1` candle in mid-week for example, are completed and written once their bucket is covered.

- CSV files are appended to in place. Parquet and Feather files cannot be appended to, so each one that gets new candles is rewritten.
- An extension is **all-or-nothing**. If it fails or is interrupted, the dataset is left, or put back by the next `extend`, exactly as it was.
- `--dry-run` prints what would be added; `--jobs`, `--no-progress` and `--quiet` work as for `generate`.

### Limits

- Datasets go **forward only**. To get an earlier start, generate again.
- Extension works **within a model revision**. A seed's candles can differ between releases that change the model, so a dataset is extended only by a release with the same `model_revision` as the one that wrote it. `marketforge info` tells you which.
- Datasets written before 4.0 have no manifest and cannot be extended.

See [ADR 0009](../../adr/0009-extend-datasets-from-an-exact-checkpoint/) for the design.

## Verify a dataset

```bash check=static
marketforge verify ./data
```

```text title="Output"
24/24 files identical to a fresh generation
```

`verify` regenerates the dataset from its manifest in a temporary directory beside it and compares every file with it: CSV byte for byte, Parquet and Feather value for value. From Python, `mf.verify(path)` returns the same verdict as a `VerifyReport`. It exits with code 1, listing the files that differ, are missing or are extra, unless all of them match. Use it:

- before you publish results, to prove the data under them is what its manifest says;
- in CI, to catch a dataset that was edited, truncated or mixed with another;
- after copying a dataset between machines.

A mismatch means the dataset was modified, or that it was written on another kind of machine: candle values can differ in their last bit across CPUs (see [Reproducibility](../../reference/reproducibility/#across-machines)). Verifying takes as long as generating the dataset did, and needs as much free disk space. A dataset written by another model revision is refused, with the version to verify it with.
