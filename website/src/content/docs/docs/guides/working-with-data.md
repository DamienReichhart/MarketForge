---
title: Working with the data
description: "Load MarketForge candles into pandas, polars, DuckDB, NumPy or PyTorch; build panels across markets that keep different hours; resample on the market's clock; and handle closures without forward-filling."
---

A MarketForge dataset is plain files, so any tool that reads CSV, Parquet or Arrow reads it. This page shows the common ones, and the three things that trip people up: time zones, closed markets and resampling.

The examples use one small dataset, two coins and a stock as Parquet with native timestamps:

```python
import marketforge as mf

mf.generate_to_disk("./data", "BTCUSD,ETHUSD,AAPL", start="2024-01-01", days=30, seed=7,
                    timeframes=["m1", "H1", "D1"], fmt="parquet", timestamps="datetime",
                    include_regime=True, include_spread=True)
```

The command line equivalent is `marketforge generate -o ./data --from 2024-01-01 --days 30 -i BTCUSD,ETHUSD,AAPL -t m1,H1,D1 --format parquet --timestamps datetime --with-regime --with-spread --seed 7`.

## pandas

The shortest way back is [`mf.read()`](../../reference/python-api/#read): it returns what `generate()` would have, with a UTC `DatetimeIndex`, float columns and a categorical regime, whatever the file format.

```python
data = mf.read("./data", timeframes="H1")
btc = data["BTCUSD"]["H1"]
print(btc.index.tz, btc["regime"].cat.categories.tolist())
```

Reading the files yourself works just as well. With Unix timestamps (the default), convert them once:

```python
import pandas as pd

df = pd.read_parquet("data/crypto/BTCUSD_H1.parquet")      # timestamp is already UTC time here
# From a CSV with Unix seconds:
# df = pd.read_csv("data/crypto/BTCUSD_H1.csv")
# df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s", utc=True)
df = df.set_index("timestamp")
```

Every timestamp is UTC and marks the **start** of the candle. To see stock candles in exchange time, convert at the end, never before aggregating: `df.tz_convert("America/New_York")`.

## polars

```python
import polars as pl

btc = pl.read_parquet("data/crypto/BTCUSD_H1.parquet")
print(btc.schema["timestamp"], btc.schema["regime"])       # Datetime(UTC), Categorical

# Every H1 file of the crypto market, with the symbol taken from the file name
crypto = (
    pl.scan_parquet("data/crypto/*_H1.parquet", include_file_paths="path")
    .with_columns(pl.col("path").str.extract(r"(\w+?)_H1").alias("symbol"))
    .drop("path")
    .collect()
)
```

## DuckDB

DuckDB queries the files in place, without loading them first: useful for datasets larger than memory.

```python
import duckdb

print(duckdb.sql("""
    SELECT regexp_extract(filename, '(\\w+?)_H1', 1) AS symbol,
           regime,
           count(*) AS candles,
           avg(spread / close) * 1e4 AS spread_bps
    FROM read_parquet('data/*/*_H1.parquet', filename = true)
    GROUP BY ALL ORDER BY ALL
"""))
```

## Several instruments side by side

[`panel()`](../../reference/python-api/#generateddata) puts one column of every instrument on a shared time index, the union of all their candle times:

```python
import numpy as np
import pandas as pd

closes = data.panel("close", "H1")
print(closes.isna().sum().to_dict())   # {'BTCUSD': 140, 'ETHUSD': 140, 'AAPL': 720}
```

A value is NaN where that instrument printed no candle, and MarketForge **never forward-fills** it: a forward-filled price is a price nobody could trade at, and it silently turns closures into zero returns. Two things leave holes here:

- **Closures.** AAPL trades six and a half hours a day, five days a week, so it is NaN for most crypto hours.
- **Clocks.** Candles start on their market's clock. Crypto's `H1` candles start on the hour; a stock's start at the 09:30 open, so at half past (14:30 UTC in winter). The two markets never share a timestamp, and `closes.dropna()` on this panel is **empty**.

Instruments of one market always share a clock, so a panel of them lines up wherever they are all open:

```python
crypto = closes[["BTCUSD", "ETHUSD"]].dropna()
returns = np.log(crypto).diff()
```

Across markets, align on what was *known* at each moment. A timestamp is the start of its candle, and its close is only known one timeframe later, so shift to close times before you forward-fill, or every row sees a price from the future:

```python
known = closes.set_axis(closes.index + pd.Timedelta(hours=1)).ffill()   # last close known at each time
```

A return computed on a panel with holes is also NaN at the first candle after each closure, which drops the overnight and weekend gaps. To keep them, compute each instrument's returns on its own frame, `np.log(data["AAPL"]["H1"]["close"]).diff()`, and join afterwards.

For the long format of most data and ML tooling, use `to_long()`:

```python
long = data.to_long("H1")                          # indexed by (symbol, time)
aapl = long.loc["AAPL"]
```

## NumPy and tensors

`to_numpy()` gives a `(time, instrument, column)` array, with its time index and symbol list. Closed markets are NaN and the regime is its code, 0 to 4:

```python
x, times, symbols = data.to_numpy("H1", columns=["close", "volume", "regime"])
print(x.shape, symbols)                # (time, 3, 3) ['BTCUSD', 'ETHUSD', 'AAPL']
```

From there to PyTorch is one call. Keep the closure mask: it is information, not noise.

```python check=static
import torch

values = torch.from_numpy(np.nan_to_num(x, nan=0.0)).float()
is_open = torch.from_numpy(~np.isnan(x[..., 0]))   # (time, instrument): was the market open?
```

For training at scale, [Feather files](../../reference/output/#csv-parquet-or-feather) are memory-mapped and load with no copy, and [Training ML models](../../use-cases/machine-learning/) has windowing and splitting recipes.

## Resampling

To get a timeframe you did not generate, use [`mf.resample()`](../../reference/python-api/#resample) on `m1` candles, not `DataFrame.resample`:

```python
m1 = mf.read("./data", "AAPL", timeframes="m1")["AAPL"]["m1"]
h4 = mf.resample(m1, "H4", "stocks")   # buckets start at the 09:30 open, partial ones dropped
```

A plain `m1.resample("4h")` buckets from midnight UTC, so a stock's four-hour candle would straddle the open, and it keeps the partial candle at each end of the range. `mf.resample()` aligns buckets on the market's clock (forex days at 17:00 New York, stock days at the open, weeks on Monday) and drops any candle whose minutes the frame does not fully cover, exactly as MarketForge's own files do. It works on your own real `m1` data too.

## Prices, quotes and costs

Candle prices are **mid prices**. To trade at the quote, use the spread:

```python
btc = data["BTCUSD"]["H1"]
bid = btc["close"] - btc["spread"] / 2
ask = btc["close"] + btc["spread"] / 2
```

`--with-bid-ask` (`include_bid_ask=True`) writes those two columns for you. A backtest that buys at `ask` and sells at `bid` pays the spread on every round trip, as it would with a broker. See [Bid-ask spread](../../reference/spread/).

## Model returns, not prices

Every dataset starts at the catalog's start prices, whatever the dates: a range from 2015 starts where one from 2024 does. The price level carries no information, so build features from log returns, ranges and volumes, and scale per instrument.
