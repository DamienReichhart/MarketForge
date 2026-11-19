---
title: Custom instruments
description: "Change catalog instruments or add your own with a TOML override file: price, volatility, drift, volume, spread and correlations."
---

Change catalog instruments or add your own with a TOML **override file**. There is no need to edit or fork the package.

```toml
# my_instruments.toml
[instruments.BTCUSD]          # change an existing instrument
start_price = 42000
volatility = 0.60             # annualised

[instruments.MYCOIN]          # add a new one
market = "crypto"
start_price = 1.50
volatility = 0.90
drift = 0.0                   # annualised log drift
volume_base = 20000           # mean volume per minute (coins / ticks / shares)
volume_volatility = 0.5       # lognormal sigma of volume noise
spread_bps = 8                # typical bid-ask spread, in basis points of the price
correlations = { BTCUSD = 0.6, ETHUSD = 0.55 }
```

```bash
marketforge generate -o ./data --from 2024-01-01 --to 2024-03-01 \
    --instruments MYCOIN,BTCUSD --overrides my_instruments.toml
```

In Python, pass the path or the same content as a dict:

```python
mf.generate("MYCOIN,BTCUSD", start="2024-01-01", end="2024-03-01",
            overrides="my_instruments.toml")
mf.generate("BTCUSD", start="2024-01-01", end="2024-03-01",
            overrides={"BTCUSD": {"start_price": 42000}})
```

## Fields

| Field | Meaning |
| --- | --- |
| `market` | `crypto`, `forex` or `stocks`. Required for a new instrument; it decides the calendar, the regime path and the model parameters. |
| `start_price` | The price at the start of the range, whatever date that is. |
| `volatility` | Annualised volatility. What you set is what you get: regime multipliers are normalised. |
| `drift` | Annualised log drift. |
| `volume_base` | Mean volume per open minute, in the market's unit. |
| `volume_volatility` | Lognormal sigma of the volume noise. |
| `spread_bps` | Typical bid-ask spread in basis points. Set it to match your broker; built-in instruments derive it per market. |
| `tick_size` | The price step, a power of ten (`0.01`, `0.0001`). Default: a cent for stocks, about five significant digits of the start price elsewhere. Every price is rounded to it. |
| `correlations` | Correlations with other instruments of the same market. |

## Correlations

Correlations you do not specify for a new instrument are implied from the ones you do: a coin 0.6-correlated with BTC is also correlated with ETH. The resulting correlation matrix is always valid. When your correlations contradict the rest of the market, the values you set are kept exactly and the other pairs move to the nearest valid matrix. If your own values contradict each other, all of them move as little as possible, and the warning says by how much.

Forex crosses take their start price, volatility, drift and correlations from their anchor pairs, so they stay arbitrage-free. Overriding those keys on a built-in cross (EURJPY, for example) has no effect and is warned about: override the anchors (EURUSD, USDJPY) instead. Volume and spread keys do apply to crosses.

## Reproducibility

The resolved overrides are written into the dataset's [manifest](../../reference/output/#the-manifest), as values, so a dataset made with an override file can be reproduced and extended without it. Anyone you share the dataset with can read those parameters.

Use `marketforge list-instruments --overrides my_instruments.toml` to check the catalog after your overrides.

## Fit instruments to your own data

`marketforge calibrate` fits instruments to m1 candle files you have (and are allowed to use), and writes an override file:

```bash check=static
marketforge calibrate real/EURUSD_m1.csv real/GBPUSD_m1.csv --market forex -o mine.toml
marketforge generate -o ./like-mine --from 2025-01-01 --days 30 -i EURUSD,GBPUSD --overrides mine.toml
```

Each file is one instrument, named `SYMBOL_m1.csv` (or `.parquet`, `.feather`), with a `timestamp` (or `time`) column and `close`, plus `volume` if you have it. A catalog symbol gets new parameters, and any other symbol becomes a new instrument. For each file it fits:

- the start price (the last close);
- the tick size: the step the closes are on, so generated prices keep your data's decimals;
- the annualised volatility, gaps included;
- the volume level;
- the correlations of hourly returns with the files before it.

Drift is not fitted: below several years of data it is noise. In Python, `mf.calibrate(files, market)` returns the same overrides as a dict.
