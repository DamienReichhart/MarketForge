---
title: Python API
description: "generate(), generate_to_disk(), extend(), instruments(), validate() and parse_time()."
---

Everything the command line does is available from Python. The supported API is what `import marketforge` exposes; module paths below it can change between releases.

```python
import marketforge as mf

data = mf.generate(
    ["EURUSD", "AAPL"],                # or "EURUSD,AAPL"
    start="2024-01-01", end="2024-02-01",
    seed=42, timeframes=["m1", "H1", "D1"],
    include_spread=True,
)
eurusd_h1 = data["EURUSD"]["H1"]       # DataFrame indexed by UTC time
closes = data.panel("close", "H1")     # one column per instrument
print(data.seed)                       # 42 (or the random seed that was chosen)

# Stream large ranges to disk instead of memory, and continue them later
report = mf.generate_to_disk("./data", markets="stocks",
                             start="2015-01-01", end="2025-01-01",
                             seed=1, fmt="parquet", jobs=3)
print(report.n_files, report.paths["stocks"]["AAPL"]["D1"], report.manifest)
mf.extend("./data", "2025-02-01")

mf.instruments("forex")                # the catalog as a DataFrame
report = mf.validate(data["EURUSD"]["m1"], "forex")
print(report.passed, report.summary())
```

## Functions

| Function | What it does |
| --- | --- |
| `generate(...)` | Candles in memory: `{symbol: {timeframe: DataFrame}}`. Each DataFrame has a UTC `DatetimeIndex` named `time` and the columns `open, high, low, close, volume`, plus `spread` with `include_spread=True` and a categorical `regime` with `include_regime=True`. |
| `GeneratedData.panel(column, timeframe)` | One column of every instrument side by side. The index is the union of all candle times; a value is NaN where that instrument's market was closed, never forward-filled. |
| `generate_to_disk(output_dir, ...)` | A dataset on disk: candle files and the manifest. Memory does not grow with the range. |
| `extend(dataset, end)` | Continues a dataset, as `marketforge extend` does. |
| `instruments(markets=None, overrides=None)` | The catalog as a DataFrame indexed by symbol: market, start price, volatility, drift, base volume, and whether the instrument is a derived forex cross. |
| `validate(data, market=None)` | Checks `m1` candles (a DataFrame or a CSV/Parquet path) against a market's validation bands. The market can be omitted for a file MarketForge wrote. |
| `parse_time(value)` | The Unix seconds of any time MarketForge accepts. |

## generate()

```python
mf.generate(
    instruments=None, *, start, end, markets=None, seed=None,
    timeframes=("m1",), anomalies=(), include_regime=False, include_spread=False,
    overrides=None,
) -> GeneratedData
```

- `instruments`: a list or one comma-separated string, in any letter case. If omitted, every instrument of `markets` (default: all markets).
- `start`, `end`: the range `[start, end)` as Unix seconds, ISO 8601 strings, or `date`/`datetime` objects (naive means UTC).
- `seed`: a non-negative integer. The same seed returns identical candles. A float, a bool or a string raises `TypeError`.
- `timeframes`: defaults to `m1` only in memory; `generate_to_disk` defaults to all eight.
- `overrides`: the path of a TOML [override file](../custom-instruments/), or the same content as a dict: `{"BTCUSD": {"start_price": 42000}}`.

`generate()` keeps everything in memory. For long ranges or many instruments, use `generate_to_disk()`.

## generate_to_disk()

Takes the same arguments as `generate()`, plus:

- `output_dir`: where to write the dataset.
- `fmt`: `"csv"` (default) or `"parquet"`.
- `timestamps`: `"unix"` (default) or `"iso"`, for CSV files.
- `jobs`: markets simulated in parallel.

Returns a `DiskReport` with `n_files`, `paths` (`{market: {symbol: {timeframe: path}}}`) and `manifest`, the path of `marketforge.json`.

## validate()

Returns a `ValidationReport`: `report.passed` is `True` when every statistic is inside its band, `report.summary()` is the printable report, and `report.metrics` holds each statistic. Raises `ValueError` if the candles are not `m1`, a price column is missing or the market is unknown. See [Validation](../validation/).
