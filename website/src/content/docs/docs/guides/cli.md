---
title: Command line
description: "Every marketforge command and option: generate, extend, validate and list-instruments."
---

```text title="Usage"
marketforge [--debug] COMMAND [OPTIONS]
```

| Command | What it does |
| --- | --- |
| [`generate`](#generate) | Writes a dataset: candle files for every instrument and timeframe, and the manifest. |
| [`extend`](#extend) | Continues a dataset forward in time, with the settings it was made with. |
| [`validate`](#validate) | Checks an `m1` candle file against real-market stylized facts. Exit code 1 on failure. |
| [`list-instruments`](#list-instruments) | Lists the catalog: start price, volatility, and whether a forex instrument is a derived cross. |

`--debug`, given before the command, shows full tracebacks. Otherwise an error is a single line. `--version` prints the version.

## generate

```bash
# One year of EURUSD, every timeframe, reproducible
marketforge generate -o ./eurusd --from 2024-01-01 --to 2025-01-01 --instruments EURUSD --seed 42

# A whole market as Parquet, with regime labels and the bid-ask spread
marketforge generate -o ./crypto --from 2024-01-01 --days 180 --market crypto \
    --format parquet --with-regime --with-spread --seed 7

# What would a run produce (files, rows, disk size, time)? Nothing is written.
marketforge generate --from 2015-01-01 --to 2025-01-01 --market all --dry-run
```

| Option | Meaning |
| --- | --- |
| `-o, --output-dir` | Where to write `{market}/{SYMBOL}_{timeframe}.{csv\|parquet\|feather}` and `marketforge.json`. |
| `--from` | Start of the range (inclusive). Accepts `2024-01-01`, `2024-01-01T09:30`, `2024-01-01T09:30-05:00` or Unix seconds. UTC unless an offset is given. |
| `--to` or `--days` | End of the range (exclusive), in the same formats as `--from`, or its length in days. Give exactly one. |
| `-i, --instruments` | Comma-separated instruments, in any letter case. Their markets are inferred. |
| `-m, --market` | `crypto`, `forex`, `stocks` or `all`. Defaults to all when `--instruments` is not given. With `--instruments`, keeps only the instruments in these markets. |
| `-s, --seed` | Non-negative integer. When omitted, a random seed is used, printed, and recorded in the manifest so the run can be reproduced. |
| `-t, --timeframes` | Any of `m1,m2,m3,m5,m10,m15,m20,m30,H1,H2,H3,H4,H6,H8,H12,D1,W1`, in any letter case. Default: `m1,m5,m15,m30,H1,H4,D1,W1`. |
| `--format` | `csv` (default), `parquet` or `feather`. Parquet files are about half the size and load much faster; Feather (Arrow IPC) loads fastest of all. |
| `--timestamps` | `unix` (default); `iso` (`2024-01-02T14:30:00Z`) for CSV files; or `datetime`, a native UTC time column, for Parquet and Feather files. |
| `--anomalies` | Optional, deliberately unrealistic events: `spikes`, `flash_crash`. |
| `--with-spread` | Adds a `spread` column: the mean quoted bid-ask spread of the candle, in price units. See [Bid-ask spread](../../reference/spread/). |
| `--with-bid-ask` | Adds `bid` and `ask` columns: the quotes around the close, `close ∓ spread / 2`, for backtesters that fill at the quote. |
| `--with-regime` | Adds a `regime` column: `trend_up`, `trend_down`, `range`, `high_volatility` or `crash`. |
| `--config` | A TOML [override file](../custom-instruments/). |
| `-j, --jobs` | Markets simulated in parallel. Default: one per market, up to the CPU count. |
| `--dry-run` | Prints the plan and estimates, then exits. |
| `--overwrite` | Replaces the dataset already in `--output-dir` instead of refusing it. |
| `--no-progress` | Hides the progress bar. |
| `-q, --quiet` | Prints nothing but warnings and errors: for scripts and CI. |

A file that receives no candle (the market was closed for the whole range, or the range is shorter than the candle) is written empty, with a warning. `generate` refuses a directory that already holds a dataset (a manifest, or candle files an interrupted run left behind), so two datasets never mix; `--overwrite` deletes the old dataset's files first and leaves any other file alone.

## extend

```bash
marketforge extend ./eurusd --to 2025-03-01   # or --days 30
```

Continues a dataset with everything but the new end taken from its manifest. Afterwards it holds exactly the candles one generation up to the new end would have produced. See [Extending a dataset](../extend/).

| Option | Meaning |
| --- | --- |
| `DATASET` | The directory holding `marketforge.json`. |
| `--to` or `--days` | The new end (exclusive), or the number of days to add. |
| `-j, --jobs` | Markets simulated in parallel. |
| `--dry-run` | Prints what would be added, then exits. |
| `--no-progress` | Hides the progress bar. |

## validate

```bash
marketforge validate --input ./eurusd/forex/EURUSD_m1.csv
marketforge validate --input ./eurusd            # every m1 file of a dataset
```

| Option | Meaning |
| --- | --- |
| `--input` | A CSV, Parquet or Feather file of `m1` candles with `open`, `high`, `low` and `close` columns, or a dataset directory: every `m1` file in it. Other timeframes are refused. |
| `--market` | `crypto`, `forex` or `stocks`: whose bands to apply. Optional for a file MarketForge wrote: it is read from the path (`{market}/{SYMBOL}_m1`). |
| `--json` | Prints each file's statistics, bands and verdict as JSON. |

Prints a report (one line per file for a dataset) and exits with code 1 if any statistic is outside its band. Works on any file with those columns, including your own real data. See [Validation](../validation/).

## info

```bash
marketforge info ./eurusd
marketforge info ./eurusd --json
```

Summarises a dataset from its manifest: the MarketForge version and model revision that wrote it, the seed, range, instruments, files and their size, and whether this MarketForge can [extend](../extend/) it (and if not, which version can). `--json` prints the same as JSON, for scripts.

## verify

```bash
marketforge verify ./eurusd
```

Regenerates a dataset from its manifest in a temporary directory and compares every file byte for byte, listing any that differ, are missing or are extra. It exits with code 1 unless all match: the dataset was modified, or it was written on another kind of machine (see [Reproducibility](../../reference/reproducibility/)). A dataset written by another model revision is refused, with the version to verify it with.

## list-instruments

```bash check=static
marketforge list-instruments --market forex
marketforge list-instruments --config my_instruments.toml
marketforge list-instruments --json
```

| Option | Meaning |
| --- | --- |
| `-m, --market` | Only this market. |
| `--config` | An override file to apply first, to see your own instruments. |

Forex crosses are marked as derived: their prices come from anchor pairs.
