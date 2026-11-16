---
title: "Bid-ask spread"
description: "The optional spread column: how it is modelled, what it reacts to, and which levels are measured or estimated."
---

With `--with-spread` (or `include_spread=True`), each candle carries the **mean quoted bid-ask spread** of its minutes, in price units. Candle prices are mid prices, so:

```
bid = price - spread / 2
ask = price + spread / 2
```

Asking for the spread changes no other column. See [ADR 0008](../../adr/0008-spread-is-an-opt-in-column-around-mid-prices/).

## How it moves

Per minute, the spread is the instrument's typical level multiplied by:

- the **volatility level** (GARCH and regime) raised to a power, so spreads widen in turbulent markets;
- the **inverse of intraday seasonality** raised to a power, so they widen in quiet hours;
- a **reopening term**: forex spreads are about five times wider when the week opens and stock spreads four times wider at the open, decaying within minutes;
- lognormal noise.

## Levels per market

The typical level is the instrument's `spread_bps`. Built-in instruments have none of their own; each market derives it:

| Market | Typical level | Reaction to volatility | Basis |
| --- | --- | --- | --- |
| crypto | Set by the price: 0.02 basis points on BTCUSD, about 1 on coins under a dollar. A fixed price increment, like an exchange tick: it does not shrink when the price falls. | Weak (power 0.1): the most turbulent minutes are 3 to 11% wider. | **Fitted to measured quotes**: Binance USDT-futures best bid/ask, February 2024. |
| forex | Set by volatility: about half a pip on EURUSD, 13 basis points on USDTRY. | Power 0.5. | Estimate. |
| stocks | Set by volatility, never below one cent: a liquid large cap quotes exactly one cent wide most of the day. | Power 0.5. | Estimate. |

**Forex and stock levels are estimates, not measurements.** To match your broker, set `spread_bps` in an [override file](../../guides/custom-instruments/):

```toml
[instruments.EURUSD]
spread_bps = 0.8
```
