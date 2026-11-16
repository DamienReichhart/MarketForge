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
    --instruments MYCOIN,BTCUSD --config my_instruments.toml
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
| `correlations` | Correlations with other instruments of the same market. |

## Correlations

Correlations you do not specify for a new instrument are implied from the ones you do: a coin 0.6-correlated with BTC is also correlated with ETH. The resulting correlation matrix is always valid.

Forex crosses take their volatility and start price from their anchor pairs, so they stay arbitrage-free.

## Reproducibility

The resolved overrides are written into the dataset's [manifest](../output/#the-manifest), as values, so a dataset made with an override file can be reproduced and extended without it. Anyone you share the dataset with can read those parameters.

Use `marketforge list-instruments --config my_instruments.toml` to check the catalog after your overrides.
