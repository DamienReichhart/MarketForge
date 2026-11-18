---
title: Python API
description: "Every public function and type of marketforge: generate, generate_many, generate_to_disk, read, extend, resample, estimate, calibrate, validate, instruments, parse_time, and what they return and raise."
---

Everything the command line does is available from Python, and more: in-memory frames, panels, tensors, parallel seeds and size estimates.

```python check=static
import marketforge as mf

data = mf.generate(["EURUSD", "AAPL"], start="2024-01-01", end="2024-02-01",
                   seed=42, timeframes=["m1", "H1", "D1"], include_spread=True)
eurusd_h1 = data["EURUSD"]["H1"]       # a DataFrame indexed by UTC time
closes = data.panel("close", "H1")     # one column per instrument
```

The supported API is what `import marketforge` exposes, listed on this page. Module paths below it (`marketforge.api.memory`, ...) can change in any release.

## At a glance

| Name | What it does |
| --- | --- |
| [`generate()`](#generate) | Candles in memory, as a [`GeneratedData`](#generateddata). |
| [`generate_many()`](#generate_many) | `generate()` once per seed, in parallel processes. |
| [`generate_to_disk()`](#generate_to_disk) | A dataset on disk: candle files and the manifest, in bounded memory. |
| [`read()`](#read) | Loads a dataset back into memory, with the right types. |
| [`extend()`](#extend) | Continues a dataset forward in time. |
| [`resample()`](#resample) | Aggregates `m1` candles into any timeframe on the market's clock. |
| [`estimate()`](#estimate) | Files, rows, size, memory and time of a generation, without running it. |
| [`validate()`](#validate) | Checks `m1` candles against the stylized facts of real markets. |
| [`calibrate()`](#calibrate) | Fits instruments to your own `m1` files and returns overrides. |
| [`instruments()`](#instruments) | The catalog as a DataFrame. |
| [`parse_time()`](#parse_time) | The Unix seconds of any time MarketForge accepts. |
| `__version__`, `MODEL_REVISION` | The installed version, and the revision of the model that decides what a seed produces (see [Reproducibility](../reproducibility/)). |

## Arguments shared by every function

| Argument | Accepts |
| --- | --- |
| `instruments` | A list (`["EURUSD", "AAPL"]`) or one comma-separated string (`"EURUSD,AAPL"`), in any letter case. If omitted, every instrument of `markets`. |
| `markets` | `"crypto"`, `"forex"`, `"stocks"`, a list or comma-separated string of them. If omitted with no `instruments`, all three. |
| `start`, `end` | The range `[start, end)`: Unix seconds, an ISO 8601 string (`"2024-01-01"`, `"2024-01-01T09:30-05:00"`), or a `date` or `datetime` (naive means UTC). From 1970 on. |
| `days` | The length of the range in whole days, instead of `end`. Give exactly one of them. |
| `seed` | A non-negative `int`. If omitted, a random one is drawn and kept on the result (`.seed`). A float, a bool or a string raises `TypeError`. |
| `timeframes` | A list or comma-separated string of `m1, m2, m3, m5, m10, m15, m20, m30, H1, H2, H3, H4, H6, H8, H12, D1, W1`. |
| `anomalies` | `"spikes"`, `"flash_crash"`, or both: deliberately unrealistic [stress events](../../use-cases/stress-testing/#anomalies-deliberately-extreme-events). |
| `include_regime` | Adds a categorical `regime` column: `trend_up`, `trend_down`, `range`, `high_volatility`, `crash` (codes 0 to 4). |
| `include_spread` | Adds `spread`, the mean quoted bid-ask spread of the candle in price units. See [Bid-ask spread](../spread/). |
| `include_bid_ask` | Adds `bid` and `ask`, the quotes around the close: `close ∓ spread / 2`. |
| `overrides` | The path of a TOML [override file](../../guides/custom-instruments/), or the same content as a dict: `{"BTCUSD": {"start_price": 42000}}`. |

An argument that is invalid, such as an unknown instrument or timeframe, a range that ends before it starts, or an override key that does not exist, raises `ValueError` with a message that says what is accepted.

## generate()

```python check=signature
mf.generate(
    instruments=None, *, start, end=None, days=None, markets=None, seed=None,
    timeframes=("m1",), anomalies=(), include_regime=False, include_spread=False,
    include_bid_ask=False, overrides=None,
) -> GeneratedData
```

Simulates the range and returns every candle in memory. Timeframes default to `m1` only. Use it for anything that fits in memory; for years of minute data, use [`generate_to_disk()`](#generate_to_disk) or check first with [`estimate()`](#estimate), whose `memory_bytes` is what `generate()` needs.

```python
data = mf.generate("BTCUSD,ETHUSD", start="2024-01-01", days=30, seed=42,
                   timeframes=["m5", "H1"], include_regime=True)
btc = data["BTCUSD"]["H1"]
print(btc.columns.tolist())   # ['open', 'high', 'low', 'close', 'volume', 'regime']
```

## generate_many()

```python check=signature
mf.generate_many(instruments=None, *, seeds, jobs=None, **kwargs) -> Iterator[GeneratedData]
```

Runs `generate()` once per seed, in parallel processes, and yields the results **in the order of `seeds`** as they are ready, so only a few are in memory at once. Each result is exactly what `generate(..., seed=s)` returns. `kwargs` are every other argument of `generate()`; passing `seed=` raises `TypeError`.

- `jobs`: the number of processes. Default: the CPU count. Each process compiles the kernels once, which takes a couple of seconds on a cold cache.
- In a script, call it under `if __name__ == "__main__":`: worker processes import the script again, as with any Python multiprocessing. Notebooks and the REPL need nothing.

```python check=static
if __name__ == "__main__":
    for data in mf.generate_many("BTCUSD", seeds=range(64), start="2024-01-01", days=90,
                                 timeframes=["m5"], include_regime=True):
        train_on(data["BTCUSD"]["m5"])      # one independent history per seed
```

## generate_to_disk()

```python check=signature
mf.generate_to_disk(
    output_dir, instruments=None, *, start, end=None, days=None, markets=None, seed=None,
    timeframes=("m1", "m5", "m15", "m30", "H1", "H4", "D1", "W1"), anomalies=(),
    include_regime=False, include_spread=False, include_bid_ask=False, overrides=None,
    fmt="csv", timestamps="unix", jobs=1, on_day=None, overwrite=False,
) -> DiskReport
```

Writes a dataset, `{output_dir}/{market}/{SYMBOL}_{timeframe}.{fmt}` plus the manifest `marketforge.json`, streaming the simulation day by day: **memory does not grow with the length of the range.** It takes the arguments of `generate()`, with all eight default timeframes, and:

| Argument | Meaning |
| --- | --- |
| `output_dir` | Where to write the dataset. Created if needed. |
| `fmt` | `"csv"`, `"parquet"` or `"feather"`. See [Output format](../output/#csv-parquet-or-feather). |
| `timestamps` | `"unix"` seconds; `"iso"` 8601 strings, for CSV; `"datetime"`, a native UTC time column, for Parquet and Feather. |
| `jobs` | Markets simulated in parallel threads. Each market uses one core, so only a request spanning several markets is faster with more. |
| `on_day` | A callable invoked with the market after each simulated day, for progress reporting. |
| `overwrite` | Replace the dataset already in `output_dir`. Without it, a directory holding one (a manifest, or candle files an interrupted run left) raises `FileExistsError`. Only files MarketForge wrote are deleted. |

Returns a [`DiskReport`](#diskreport).

## read()

```python check=signature
mf.read(dataset, instruments=None, *, timeframes=None) -> GeneratedData
```

Loads a dataset written by `generate_to_disk()` or the command line, in any format, back into memory: the same `GeneratedData` that `generate()` returns for those settings, with a UTC index, float columns and a categorical regime. Values are those of the files, so prices are rounded to 8 decimals and volumes to 4. Raises `ValueError` if the directory has no manifest, or holds none of the instruments or timeframes asked for.

```python check=static
h1 = mf.read("./data", "BTCUSD,ETHUSD", timeframes="H1")
```

## extend()

```python check=signature
mf.extend(dataset, end, *, jobs=1, on_day=None) -> DiskReport
```

Continues a dataset up to `end`, with the seed, instruments, timeframes, format and overrides of its manifest. Afterwards it holds exactly the candles one generation up to `end` would have produced. Raises `ValueError` if the directory is not a dataset, `end` is not after the dataset's end, or the dataset was written by another model revision. See [Extending and verifying](../../guides/extend/).

## resample()

```python check=signature
mf.resample(frame, timeframe, market) -> pd.DataFrame
```

Aggregates `m1` candles into `timeframe` exactly as MarketForge does: on the market's clock (forex days start at 17:00 New York, stock days at the 09:30 open, weeks on Monday), dropping any candle whose bucket `frame` does not fully cover. A plain `DataFrame.resample("4h")` gets both wrong. Open is the first open, high the maximum, low the minimum, close the last close, volume the sum, spread the mean and regime the last.

`frame` needs a UTC `DatetimeIndex` and `open`, `high`, `low`, `close` and `volume`: a frame from `generate()` or `read()`, or your own data.

```python
m1 = mf.generate("EURUSD", start="2024-01-01", days=14, seed=3)["EURUSD"]["m1"]
h4 = mf.resample(m1, "H4", "forex")   # 17:00, 21:00, 01:00, ... New York
```

## estimate()

```python check=signature
mf.estimate(
    instruments=None, *, start, end=None, days=None, markets=None,
    timeframes=("m1", "m5", "m15", "m30", "H1", "H4", "D1", "W1"),
    include_regime=False, include_spread=False, overrides=None, fmt="csv", seed=None,
) -> Estimate
```

What a generation would produce, without running it. It is instant, and what `--dry-run` prints. Returns an [`Estimate`](#estimate-1).

```python
plan = mf.estimate(markets="crypto", start="2020-01-01", end="2024-01-01",
                   timeframes=["m5", "H1"], fmt="parquet")
print(plan.files, plan.rows, plan.disk_bytes / 1e9, plan.wall_seconds(jobs=3))
```

## validate()

```python check=signature
mf.validate(data, market=None) -> ValidationReport
```

Checks `m1` candles against a market's validation bands. `data` is a DataFrame with `open`, `high`, `low` and `close` columns, or the path of a CSV, Parquet or Feather file; a `spread` column, when present, is checked too. `market` may be omitted for a file MarketForge wrote, whose path names it. Raises `ValueError` if the candles are not `m1`, a price column is missing or the market is unknown. Returns a [`ValidationReport`](#validationreport). See [Validation](../../guides/validation/).

## calibrate()

```python check=signature
mf.calibrate(files, market) -> dict[str, dict[str, Any]]
```

Fits instruments to `m1` candle files: start price, annual volatility, volume level and correlations, as described in [Custom instruments](../../guides/custom-instruments/#fit-instruments-to-your-own-data). Returns overrides to pass as `overrides=`, the same that `marketforge calibrate` writes as TOML.

## instruments()

```python check=signature
mf.instruments(markets=None, *, overrides=None) -> pd.DataFrame
```

The catalog as a DataFrame indexed by symbol, with the columns `market`, `start_price`, `volatility` and `drift` (annualised), `volume_base` (mean volume per open minute) and `derived` (`True` for forex crosses, whose prices come from anchor pairs). With `overrides`, they are applied first.

```python
forex = mf.instruments("forex")
print(len(forex), forex["derived"].sum())   # 81 instruments, 40 of them derived crosses
```

## parse_time()

```python check=signature
mf.parse_time(value) -> int
```

The Unix seconds (UTC) of any time MarketForge accepts: an `int`, a `float` or a digit string of seconds, an ISO 8601 string, or a `date` or `datetime` (naive means UTC).

## GeneratedData

What `generate()`, `generate_many()` and `read()` return: a `dict` of `{symbol: {timeframe: DataFrame}}`, plus the seed.

Each DataFrame has a UTC `DatetimeIndex` named `time` (the start of each candle) and `float64` columns `open`, `high`, `low`, `close` and `volume`, then `spread`, `bid` and `ask` when asked for, and `regime` last, a categorical. Rows exist only for candles the market printed: there is no row while a market is closed.

| Member | What it gives |
| --- | --- |
| `data["BTCUSD"]["H1"]` | One instrument and timeframe as a DataFrame. Iterate with `data.items()` like any dict. |
| `data.seed` | The seed that produced it: the one passed, or the one drawn at random. |
| `data.panel(column="close", timeframe=None)` | One column of every instrument side by side. Its index is the union of every instrument's candle times, so a value is NaN where that instrument's market was closed. It is never forward-filled. |
| `data.to_long(timeframe=None)` | Every instrument in one frame indexed by `(symbol, time)`: the long format of most data and ML tooling. `.loc["BTCUSD"]` gives back one instrument. |
| `data.to_numpy(timeframe=None, columns=("open", "high", "low", "close", "volume"))` | A `(time, instrument, column)` float array, its time index and its symbol list: `x, times, symbols = data.to_numpy("H1")`. NaN where a market was closed; the regime as its codes. |

`timeframe` may be omitted when only one was generated; otherwise a `ValueError` lists the choices.

## DiskReport

What `generate_to_disk()` and `extend()` return.

| Attribute | Meaning |
| --- | --- |
| `seed` | The seed of the dataset. |
| `paths` | Every file written, as `{market: {symbol: {timeframe: Path}}}`: `report.paths["stocks"]["AAPL"]["D1"]`. |
| `n_files` | The number of files. |
| `manifest` | The path of `marketforge.json`. |

## Estimate

What `estimate()` returns. Every figure is approximate.

| Attribute | Meaning |
| --- | --- |
| `files` | Output files: one per instrument and timeframe. |
| `rows` | Candles across all of them. |
| `disk_bytes` | Size on disk in the requested format. |
| `memory_bytes` | Peak memory of `generate()`, which holds everything in memory. `generate_to_disk()` needs far less. |
| `seconds` | Time on one core. |
| `wall_seconds(jobs=1)` | Elapsed time with `jobs` markets in parallel. |
| `open_minutes` | Open minutes of each market in the range: `{"crypto": 129600, ...}`. |

## ValidationReport

What `validate()` returns.

| Member | Meaning |
| --- | --- |
| `passed` | `True` when every statistic is inside its band. |
| `summary()` | The printable report, one line per statistic, as `marketforge validate` prints it. |
| `metrics` | `{name: MetricResult}`, one per statistic. |
| `get(name)` | One `MetricResult`, or `None`. |

A `MetricResult` has `name`, `value`, `low` and `high` (the band; `None` for an open end), `passed`, and `provisional`, which is `True` when the band is not yet anchored on real data (forex and stocks).

```python
report = mf.validate(mf.generate("BTCUSD", start="2024-01-01", days=14, seed=1)["BTCUSD"]["m1"], "crypto")
kurtosis = report.get("excess_kurtosis")
print(report.passed, kurtosis.value, (kurtosis.low, kurtosis.high))
```

## Errors

| Exception | When |
| --- | --- |
| `ValueError` | An invalid argument: an unknown instrument, market or timeframe, a bad range, an invalid override file (its subclass `OverrideError`), candles that are not `m1` for `validate()`, a directory that is not a dataset. |
| `TypeError` | A seed that is not an integer; `seed=` passed to `generate_many()`. |
| `FileExistsError` | `generate_to_disk()` into a directory that holds a dataset, without `overwrite=True`. |
| `OSError` | Too many output files open at once for the process's limit, raised before anything is generated. See [Performance and scale](../../guides/performance/#open-file-limits). |
