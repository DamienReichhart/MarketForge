---
title: Output format
description: "The files, columns, types, rounding, timestamps, candle alignment and manifest of a MarketForge dataset, and its guarantees."
---

## Layout

```text title="The dataset"
data/
├── marketforge.json
├── crypto/BTCUSD_m1.csv, BTCUSD_H1.csv, ...
├── forex/EURUSD_m1.csv, ...
└── stocks/AAPL_m1.csv, ...
```

One file per instrument and timeframe, under its market: `{market}/{SYMBOL}_{timeframe}.{csv|parquet|feather}`. This is the **split layout**, the default.

### The long layout

With `--layout long` (`layout="long"`), Parquet and Feather only, each market and timeframe is one file, `{market}/{timeframe}.{parquet|feather}`, with `symbol` and `market` columns after `timestamp`, sorted by time, then symbol:

```text title="--layout long"
data/
├── marketforge.json
├── crypto/m1.parquet, H1.parquet, ...
├── forex/m1.parquet, ...
└── stocks/m1.parquet, ...
```

One glob reads every instrument of a timeframe, with no file-name parsing:

```python check=static
import polars as pl

m1 = pl.scan_parquet("data/*/m1.parquet").filter(pl.col("symbol") == "BTCUSD").collect()
```

Instruments of different markets stay in different files: markets are simulated in parallel and trade at different times, so one file per market keeps every file sorted by time as it is written and extended. `read()`, `extend` and `verify` handle both layouts.

## Columns

```csv
timestamp,open,high,low,close,volume
1704205800,185,185.02079274,184.85083294,184.8539491,56235.3556
1704205860,184.8539491,185.03837413,184.84785539,185.03767407,127066.8316
```

| Column | Meaning |
| --- | --- |
| `timestamp` | Start of the candle, in Unix seconds (UTC), or `2024-01-02T14:30:00Z` with `--timestamps iso` (CSV), or a native UTC time column with `--timestamps datetime` (Parquet, Feather), which Spark, DuckDB and polars read as time. |
| `open`, `high`, `low`, `close` | **Mid prices**, rounded to 8 decimals (trailing zeros are not written). |
| `volume` | Rounded to 4 decimals. Base asset for crypto (BTC for BTCUSD), shares for stocks, **tick volume** (integer price updates per minute) for forex. |
| `spread` | With `--with-spread`: the mean quoted bid-ask spread of the candle, in price units. `bid = price - spread / 2`, `ask = price + spread / 2`. |
| `bid`, `ask` | With `--with-bid-ask`: the quotes around the close, `close - spread / 2` and `close + spread / 2`. |
| `regime` | With `--with-regime`, last: `trend_up`, `trend_down`, `range`, `high_volatility` or `crash`, the regime the market was in at the candle's close. CSV files hold the name; Parquet and Feather files and frames in memory hold the same categorical, whose codes (`.cat.codes`) are 0 to 4 in that order. |

Parquet and Feather files also say what they hold in their metadata: `marketforge` (the version), `model_revision`, `seed`, `market`, `timeframe` and, in the split layout, `symbol` (`pyarrow.parquet.read_schema(path).metadata`).

Frames in memory, from `generate()` or `read()`, have the same columns with `float64` values and a UTC `DatetimeIndex` named `time` instead of `timestamp`. See [`GeneratedData`](../python-api/#generateddata).

## Guarantees

- `high >= max(open, close)` and `low <= min(open, close)`; all prices and volumes are positive.
- Within a session, each candle opens at the previous close. The first candle after a closure opens with a **gap**.
- No candle exists while a market is closed: stocks outside the NYSE session, forex at the weekend.
- A candle is only written when the range covers every open minute of its bucket. Partial first or last candles are dropped, never published half-built.

## Candle alignment

| Market | Daily candle starts | Weekly candle starts | Intraday alignment |
| --- | --- | --- | --- |
| crypto | 00:00 UTC | Monday 00:00 UTC | UTC clock |
| forex | 17:00 New York (the "NY close") | Sunday 17:00 New York | New York close clock (H4: 17:00, 21:00, 01:00, ...) |
| stocks | 09:30 New York (the open) | Monday's open | The open (H1: 09:30, 10:30, ...) |

## The manifest

Every dataset has a `marketforge.json`. It records the MarketForge version and model revision, the seed, the range, the instruments, timeframes, format, layout, timestamps, anomalies and columns asked for, and the **resolved overrides** (the values, not a path, so the dataset stands on its own), plus the checkpoint [`extend`](../../guides/extend/) resumes from and the rows, size and SHA-256 of every candle file as written, which `marketforge verify --checksums` checks without regenerating anything. `marketforge info` prints it in readable form.

```json
{
  "marketforge": "4.0.0",
  "model_revision": 1,
  "seed": 1,
  "start": "2024-01-01T00:00:00Z",
  "end": "2024-01-03T00:00:00Z",
  "format": "csv",
  "layout": "split",
  "timestamps": "unix",
  "timeframes": ["m1", "H1"],
  "anomalies": [],
  "with_regime": true,
  "with_spread": true,
  "with_bid_ask": false,
  "instruments": { "crypto": ["BTCUSD"], "forex": ["EURUSD"] },
  "overrides": {},
  "checkpoint": { "...": "model state at the end of the range" },
  "files": {
    "crypto/BTCUSD_m1.csv": { "rows": 2880, "bytes": 191734, "sha256": "..." }
  }
}
```

A dataset can always be reproduced from its manifest, even when the seed was random and the terminal output is gone. Anyone you give the dataset to can read your custom instrument parameters there.

## CSV, Parquet or Feather

Parquet files are about half the size of CSV and load much faster; use them for anything large. Feather files (Arrow IPC) are uncompressed, so they are the largest, about the size of CSV, and the fastest to load: `pyarrow.memory_map` reads them with no copy and no decompression, so a training loop pays only for the pages it touches. Choose Parquet to keep disk small, Feather to load fast. Candles are written in chunks of up to 32,768 rows per file (one Parquet row group each).

A Parquet or Feather file can only be finished, not appended to, so every such output stays open until the run ends. When a run needs more open files than the process's soft limit allows (256 by default on macOS), MarketForge raises the soft limit up to the hard limit, and stops before generating anything if that is not enough.
