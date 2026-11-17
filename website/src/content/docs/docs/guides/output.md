---
title: Output format
description: "Files, columns, rounding, timestamps and the manifest that MarketForge writes."
---

## Layout

```
data/
├── marketforge.json
├── crypto/BTCUSD_m1.csv, BTCUSD_H1.csv, ...
├── forex/EURUSD_m1.csv, ...
└── stocks/AAPL_m1.csv, ...
```

One file per instrument and timeframe, under its market: `{market}/{SYMBOL}_{timeframe}.{csv|parquet|feather}`.

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
| `regime` | With `--with-regime`, last: `trend_up`, `trend_down`, `range`, `high_volatility` or `crash`. Parquet files and frames in memory hold it as the same categorical, whose codes (`.cat.codes`) are 0 to 4 in that order. |

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

Every dataset has a `marketforge.json`. It records the MarketForge version and model revision, the seed, the range, the instruments, timeframes, format, timestamps, anomalies and columns asked for, and the **resolved overrides** (the values, not a path, so the dataset stands on its own), plus the checkpoint [`extend`](../extend/) resumes from.

```json
{
  "marketforge": "4.0.0",
  "model_revision": 1,
  "seed": 1,
  "start": "2024-01-01T00:00:00Z",
  "end": "2024-01-03T00:00:00Z",
  "format": "csv",
  "timestamps": "unix",
  "timeframes": ["m1", "H1"],
  "anomalies": [],
  "include_regime": true,
  "include_spread": true,
  "instruments": { "crypto": ["BTCUSD"], "forex": ["EURUSD"] },
  "overrides": {},
  "checkpoint": { "...": "model state at the end of the range" }
}
```

A dataset can always be reproduced from its manifest, even when the seed was random and the terminal output is gone. Anyone you give the dataset to can read your custom instrument parameters there.

## CSV, Parquet or Feather

Parquet files are about half the size of CSV and load much faster; use them for anything large. Feather files (Arrow IPC, zstd-compressed) are a little larger than Parquet and the fastest to load: they are memory-mapped, so a training loop reads them with no copy. Candles are written in chunks of up to 32,768 rows per file (one Parquet row group each).

A Parquet or Feather file can only be finished, not appended to, so every such output stays open until the run ends. When a run needs more open files than the process's soft limit allows (256 by default on macOS), MarketForge raises the soft limit up to the hard limit, and stops before generating anything if that is not enough.
