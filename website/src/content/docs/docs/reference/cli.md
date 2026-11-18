---
title: Command line
description: "Every marketforge command and option: generate, extend, info, verify, validate, calibrate and list-instruments, with their exit codes."
---

```text title="Usage"
marketforge [--debug] COMMAND [OPTIONS]
```

| Command | What it does |
| --- | --- |
| [`generate`](#generate) | Writes a dataset: one candle file per instrument and timeframe, and the manifest. |
| [`extend`](#extend) | Continues a dataset forward in time with the settings it was made with. |
| [`info`](#info) | Summarises a dataset from its manifest, and says whether it can be extended. |
| [`verify`](#verify) | Regenerates a dataset from its manifest and compares every file byte for byte. |
| [`validate`](#validate) | Checks `m1` candles against the stylized facts of real markets. |
| [`calibrate`](#calibrate) | Fits instruments to your own `m1` files and writes an override file. |
| [`list-instruments`](#list-instruments) | Lists the catalog, with your overrides applied if you give them. |

| Global option | Meaning |
| --- | --- |
| `--debug` | Given before the command: show the full traceback of an error instead of one line. |
| `--version` | Print the version and exit. |
| `-h, --help` | Help for `marketforge` or for any command (`marketforge generate -h`). |

Every command exits with **0** on success; **1** when it fails, which includes an unknown instrument, a failed validation and a dataset that does not verify; and **2** when the command line itself is malformed: an unknown option, or a required one missing.

## Common values

These formats are shared by every command that takes them.

| Value | Accepted forms |
| --- | --- |
| Time | `2024-01-01`, `2024-01-01T09:30`, `2024-01-01T09:30-05:00` or Unix seconds (`1704067200`). UTC unless an offset is given. Ranges start at 1970-01-01 at the earliest. |
| Range | `--from` is inclusive and `--to` exclusive: `--from 2024-01-01 --to 2024-02-01` is all of January. `--days N` instead of `--to` gives N whole days. |
| Instruments | Comma-separated catalog symbols in any letter case: `eurusd,AAPL,BtcUsd`. Their markets are inferred. See [Markets & calendars](../markets/). |
| Markets | `crypto`, `forex`, `stocks`, a comma-separated list of them, or `all`. |
| Timeframes | Any of `m1, m2, m3, m5, m10, m15, m20, m30, H1, H2, H3, H4, H6, H8, H12, D1, W1`, comma-separated, in any letter case. |

## generate

```bash
# One year of EURUSD, every default timeframe, reproducible
marketforge generate -o ./eurusd --from 2024-01-01 --to 2025-01-01 --instruments EURUSD --seed 42

# A whole market as Parquet, with regime labels and the bid-ask spread
marketforge generate -o ./crypto --from 2024-01-01 --days 180 --market crypto \
    --format parquet --with-regime --with-spread --seed 7

# What would a run produce (files, rows, disk size, time)? Nothing is written.
marketforge generate --from 2015-01-01 --to 2025-01-01 --market all --dry-run
```

### What to generate

| Option | Meaning |
| --- | --- |
| `--from TIME` | Start of the range, inclusive. Required. |
| `--to TIME` or `--days N` | End of the range (exclusive), or its length in days. Give exactly one. |
| `-i, --instruments LIST` | The instruments to write. |
| `-m, --market LIST` | Every instrument of these markets. The default when `--instruments` is not given is `all`. With `--instruments`, keeps only those in these markets. |
| `-s, --seed N` | A non-negative integer. Without it a random seed is drawn, printed and recorded in the manifest, so the run can still be reproduced. |
| `-t, --timeframes LIST` | Default: `m1,m5,m15,m30,H1,H4,D1,W1`. |
| `--anomalies LIST` | Deliberately unrealistic stress events: `spikes`, `flash_crash`. See [Stress testing](../../use-cases/stress-testing/#anomalies-deliberately-extreme-events). |
| `--config FILE` | A TOML [override file](../../guides/custom-instruments/) that changes or adds instruments. |

### Columns and files

| Option | Meaning |
| --- | --- |
| `-o, --output-dir DIR` | Where to write `{market}/{SYMBOL}_{timeframe}.{csv,parquet,feather}` and `marketforge.json`. Required unless `--dry-run`. |
| `--format` | `csv` (default), `parquet` (smallest) or `feather` (fastest to load). See [Output format](../output/#csv-parquet-or-feather). |
| `--timestamps` | `unix` seconds (default); `iso`, such as `2024-01-02T14:30:00Z`, for CSV; `datetime`, a native UTC time column, for Parquet and Feather. |
| `--with-spread` | Adds `spread`: the mean quoted bid-ask spread of the candle, in price units. See [Bid-ask spread](../spread/). |
| `--with-bid-ask` | Adds `bid` and `ask`: the quotes around the close, `close ∓ spread / 2`. |
| `--with-regime` | Adds `regime`: `trend_up`, `trend_down`, `range`, `high_volatility` or `crash`. |

### How to run

| Option | Meaning |
| --- | --- |
| `-j, --jobs N` | Markets simulated in parallel. Default: one per market, up to the CPU count. Each market runs on one core, so `--jobs` only helps when several markets are generated. |
| `--dry-run` | Print the plan (range, seed, instruments, files, rows, size, time) and exit without writing. |
| `--overwrite` | Replace the dataset already in `--output-dir`. Only files MarketForge wrote are deleted. |
| `--no-progress` | Hide the progress bar. |
| `-q, --quiet` | Print nothing but warnings and errors: for scripts and CI. |

`generate` refuses a directory that already holds a dataset (a manifest, or candle files an interrupted run left behind), so two datasets never mix. A file that receives no candle, because the market was closed for the whole range or the range is shorter than the candle, is written empty with a warning.

## extend

```bash check=static
marketforge extend ./eurusd --to 2025-03-01
marketforge extend ./eurusd --days 30
```

Continues a dataset up to a new end. The seed, instruments, timeframes, format, columns and overrides come from its manifest and cannot be changed. Afterwards it holds exactly the candles one generation up to the new end would have produced. See [Extending and verifying](../../guides/extend/).

| Option | Meaning |
| --- | --- |
| `DATASET` | The directory holding `marketforge.json`. |
| `--to TIME` or `--days N` | The new end (exclusive), or the number of days to add. |
| `-j, --jobs N` | Markets simulated in parallel. |
| `--dry-run` | Print what would be added and exit. |
| `--no-progress` | Hide the progress bar. |
| `-q, --quiet` | Print nothing but warnings and errors. |

A dataset written by another model revision is refused, with the version that can extend it.

## info

```bash check=static
marketforge info ./eurusd
marketforge info ./eurusd --json
```

```text title="Output"
Dataset ./eurusd
  Written by  MarketForge 4.0.0 (model revision 1)
  Seed        42
  Range       2024-01-01 00:00 UTC -> 2025-01-01 00:00 UTC
  forex       1 instrument(s): EURUSD
  Files       8 csv files, 27.4 MB; timeframes m1, m5, m15, m30, H1, H4, D1, W1
  Can extend  yes
```

Summarises a dataset from its manifest, without reading the candle files: the version and model revision that wrote it, the seed, range, instruments, files and their size, and whether this MarketForge can [extend](#extend) it (and if not, which version can).

| Option | Meaning |
| --- | --- |
| `DATASET` | The directory holding `marketforge.json`. |
| `--json` | Print the same summary as JSON, for scripts. |

## verify

```bash check=static
marketforge verify ./eurusd
```

Regenerates the dataset from its manifest in a temporary directory and compares every file byte for byte, listing any that differ, are missing or are extra. It exits with **1** unless all of them match, which means the dataset was modified, or written on another kind of machine (see [Reproducibility](../reproducibility/#across-machines)). A dataset written by another model revision is refused, with the version to verify it with.

| Option | Meaning |
| --- | --- |
| `DATASET` | The directory holding `marketforge.json`. |
| `-j, --jobs N` | Markets regenerated in parallel. |

Verifying takes as long as generating the dataset did, and needs as much free disk space.

## validate

```bash check=static
marketforge validate --input ./eurusd/forex/EURUSD_m1.csv
marketforge validate --input ./eurusd                    # every m1 file of a dataset
marketforge validate --input ./my_eurusd_m1.csv --market forex
```

Measures heavy tails, volatility clustering, long memory, the leverage effect, intrabar range and the spread, and compares each with the band measured on real markets. It prints a report (one line per file for a dataset) and exits with **1** if any statistic is outside its band. It works on any file with those columns, including your own real data. See [Validation](../../guides/validation/).

| Option | Meaning |
| --- | --- |
| `--input PATH` | A CSV, Parquet or Feather file of `m1` candles with `open`, `high`, `low` and `close` columns, or a dataset directory, to check every `m1` file in it. Other timeframes and empty files are refused. Required. |
| `--market` | `crypto`, `forex` or `stocks`: whose bands to apply. Optional for a file MarketForge wrote, whose path (`{market}/{SYMBOL}_m1`) names the market. |
| `--json` | Print each file's statistics, bands and verdict as JSON. |

## calibrate

```bash check=static
marketforge calibrate real/EURUSD_m1.csv real/GBPUSD_m1.csv --market forex -o mine.toml
marketforge generate -o ./like-mine --from 2025-01-01 --days 30 -i EURUSD,GBPUSD --config mine.toml
```

Fits instruments to `m1` candle files you have, and are allowed to use, and writes an override file to generate data like them. Each file is one instrument: the symbol is the part of the file name before the first `_`. A catalog symbol gets new parameters, and any other becomes a new instrument. What is fitted is listed in [Custom instruments](../../guides/custom-instruments/#fit-instruments-to-your-own-data).

| Option | Meaning |
| --- | --- |
| `FILES...` | One or more `m1` files (CSV, Parquet or Feather) with a `timestamp` (or `time`) column and `close`, plus `volume` if you have it. |
| `-m, --market` | `crypto`, `forex` or `stocks`: the market the instruments join, for their calendar and correlations. Required. |
| `-o, --output FILE` | The override file to write. Default: `calibrated.toml`. |

## list-instruments

```bash check=static
marketforge list-instruments --market forex
marketforge list-instruments --config my_instruments.toml
marketforge list-instruments --json
```

Lists every instrument with its market, start price and annual volatility. Forex crosses are marked as derived: their prices come from [anchor pairs](../markets/#arbitrage-free-forex).

| Option | Meaning |
| --- | --- |
| `-m, --market` | Only this market: `crypto`, `forex` or `stocks`. |
| `--config FILE` | An override file to apply first, to check your own instruments. |
| `--json` | Print the instruments as JSON. |
