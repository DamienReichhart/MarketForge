---
title: "The model"
description: "How MarketForge simulates prices, volatility, regimes, gaps, highs and lows, and volume, minute by minute."
---

MarketForge simulates each market minute by minute, one UTC day at a time, carrying the model's state (prices, GARCH variance, regime, volume memory) from day to day. Every instrument of a market is simulated jointly, so correlation, tail dependence and the regime are shared. See [ADR 0001](../../adr/0001-simulate-whole-market-day-by-day/).

Per open minute *t* and simulated series *f*:

## Shocks

Correlated, unit-variance **Student-t shocks** *z*, built as a normal variance mixture. The mixing variable is shared by the whole market, which creates **tail dependence**: in a sell-off, every instrument gets the large shock at once, as in real markets, rather than independently. See [ADR 0005](../../adr/0005-shared-student-t-mixing-for-tail-dependence/).

Crypto shocks have 6 degrees of freedom, the heaviest tails of the three markets.

In high-volatility and crash regimes a common shock is added to every instrument, so **correlations intensify under stress** as they do in real sell-offs. From range to crash, BTC-SAND goes from 0.55 to 0.82, AAPL-XOM from 0.38 to 0.65 and EURUSD-USDCHF from -0.66 to -0.86. See [ADR 0014](../../adr/0014-correlations-intensify-under-stress/).

## Volatility

σ<sub>f</sub> · √h<sub>t</sub> · g<sub>t</sub> · s<sub>t</sub>, where:

- σ<sub>f</sub> is the per-minute level implied by the instrument's annual volatility on its market's calendar.
- h<sub>t</sub> is a **GJR-GARCH(1,1)** multiplier with unit mean. It gives volatility clustering and the **leverage effect**: down-moves raise volatility more than up-moves.
- g<sub>t</sub> is the **regime** multiplier, smoothed so regime changes ramp in.
- s<sub>t</sub> is **intraday seasonality**: the U shape of stocks, the session pattern of forex, the US-open peak and quieter weekends of crypto.

## Regimes

A market-wide hidden state: **trend up**, **trend down**, **range**, **high volatility** or **crash**. It sets the trend and scales the volatility of every instrument of the market at once. Regimes last hours to days: crypto trends average about 1.7 days and crashes about 13 hours.

A regime trends along the market's main factor: all coins together, all stocks together, and in forex the dollar (`trend_up` is the dollar falling, so EURUSD rises and USDCHF falls). A spell of `trend_up` or `trend_down` ends in its direction about 70-90% of the time, and a crash falls by about 1.5 of its own standard deviations. Within a minute the trend is small next to the noise, as in real markets: it shows over hours. Trends average to zero and volatility multipliers are normalised, so the annual volatility and drift in the catalog are what you get over the long run. See [ADR 0013](../../adr/0013-regimes-trend-along-the-market-factor/). With `--with-regime`, the regime of each candle is written next to it.

## Returns

Open to close: μ<sub>f</sub> · d<sub>t</sub> + volatility · *z*, where d<sub>t</sub> is the regime drift multiplier.

## Gaps

After a closure of *C* minutes, the open jumps by a shock whose variance grows with *C*. Roughly 30% of a session's variance builds up overnight for stocks; a typical EURUSD weekend gap is about 10 pips.

## High and low

The exact maximum and minimum of a **Brownian bridge** from open to close, sampled from their closed-form distribution, so `high >= max(open, close)` and `low <= min(open, close)` by construction. The excursion uses a fraction of the bar's volatility (0.62 for crypto), because real minutes wander less inside the bar than a pure random walk.

## Volume

A **log-AR(1)** process. Volume rises with the size of the standardized move, with the volatility level (the mixture-of-distributions hypothesis) and with intraday seasonality, and has its own persistent noise.

## Spread

An optional column around the mid price, modelled separately so asking for it changes no other column. See [Bid-ask spread](../spread/).

## Anomalies

Optional, deliberately unrealistic events layered on top of the base simulation: `spikes` (single-candle fat-tail moves) and `flash_crash` (multi-candle V-shaped crashes). They are not part of the realism contract.

## Performance

The kernels are compiled with [Numba](https://numba.pydata.org/), and only the instruments you ask for are computed past the random draws. A year of EURUSD across all 8 timeframes takes about 2 s; a month of all 208 instruments, all timeframes, about 6 s. Memory does not grow with the date range. See [ADR 0003](../../adr/0003-stay-in-python-with-numba/).
