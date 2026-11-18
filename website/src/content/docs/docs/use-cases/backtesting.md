---
title: Backtesting
description: "Test a backtesting engine or trading system against data that behaves like a real feed: calendars, gaps, spreads and aligned multi-asset panels."
---

Most backtester bugs are not in the strategy but in the plumbing: a session that starts at the wrong hour, a forward-filled weekend, a fill at a price that never existed, two instruments misaligned by a minute. Clean CSVs from a single 24/7 market hide all of them. MarketForge produces data with the awkward properties of real feeds, on demand and reproducibly, so you can find those bugs before they cost money.

## What to test your engine against

### Calendars and closures

- **Stocks** trade the NYSE session, 09:30 to 16:00 New York time, DST-aware, and skip NYSE holidays and early closes.
- **Forex** trades from Sunday 17:00 to Friday 17:00 New York time.
- **Crypto** never closes.

No candle is printed while a market is closed. An engine that assumes a candle every minute, or every day, breaks here. Daily candles start where the market's day does: 00:00 UTC for crypto, 17:00 New York for forex, the 09:30 open for stocks. See [Markets & calendars](../../reference/markets/).

### Gaps

The first candle after a closure opens away from the previous close, because the price moved while the market was closed. Stocks build up roughly 30% of a session's variance overnight; a typical EURUSD weekend gap is about 10 pips. Check that stop orders gap through their level instead of filling at it.

### Mid prices and the spread

Candle prices are **mid prices**. With `--with-spread`, each candle carries the mean quoted bid-ask spread, so:

```text title="Bid and ask from the mid price"
bid = price - spread / 2
ask = price + spread / 2
```

The spread widens in turbulent markets, in quiet hours and at the reopen: forex spreads are about five times wider when the week opens, stock spreads four times wider at the open. A strategy that only works when it trades the mid is not a strategy. See [Bid-ask spread](../../reference/spread/).

### Multi-asset alignment

`GeneratedData.panel()` puts every instrument on the union of their candle times, with NaN where a market was closed, never forward-filled. Mixing AAPL and BTCUSD shows immediately whether your engine handles instruments that do not trade at the same times.

Forex crosses are derived from anchor pairs, so `EURJPY == EURUSD * USDJPY` at every minute: a triangular-arbitrage strategy should find nothing. If it does, the engine has a look-ahead or alignment bug.

### Higher timeframes

Higher timeframes are aggregated from the same minutes and aligned to each market's clock (forex H4 candles start at 17:00, 21:00, 01:00, ... New York). A partial first or last candle is never published. Compare your engine's own resampling against MarketForge's files to catch off-by-one bucketing.

## Known answers

Synthetic data lets you build tests with a known answer:

- **Zero-edge baseline.** Generate a market with `drift = 0` in an [override file](../../guides/custom-instruments/) and run a random-entry strategy across many seeds. Its mean P&L before costs should be zero, and after costs should be minus the spread you paid. Anything else is a bug in fills or accounting.
- **Look-ahead detector.** A strategy that peeks one candle ahead makes money on every seed. Run your real strategy across 50 seeds: consistent profits on data with no edge are a red flag.
- **Regression tests.** Fix a seed and a version, store the expected trades, and assert them in CI. The data will be bit-for-bit identical on the next run with the same version and platform.

```bash
# A fixed fixture for the engine's test suite: one month, three markets, small
marketforge generate -o tests/fixtures/market --from 2024-03-01 --days 31 \
    -i AAPL,EURUSD,BTCUSD -t m5,H1,D1 --with-spread --seed 7
```

## From one equity curve to a distribution

A backtest on real data gives you one equity curve. Run the same strategy over many seeds to see the distribution of outcomes it produces, and see [Stress testing](../stress-testing/) for crashes and tail events.
