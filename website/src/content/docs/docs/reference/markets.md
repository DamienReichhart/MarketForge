---
title: "Markets & calendars"
description: "The three simulated markets, their 208 instruments, trading calendars, volume units and known simplifications."
---

A **market** is a family of instruments that share one trading calendar, one regime path and one set of model parameters. Every instrument of a market is simulated jointly.

| Market | Instruments | Hours | Volume unit | Notes |
| --- | --- | --- | --- | --- |
| crypto | 53 (BTCUSD, ETHUSD, SOLUSD, ...) | 24/7 | Base asset (BTC for BTCUSD) | Heaviest tails (Student-t, 6 degrees of freedom). Activity peaks at the US open; weekends are quieter. Calibrated on real Binance `m1` data. |
| forex | 81: majors, crosses, exotics, metals (XAUUSD), index and oil CFDs | Sunday 17:00 to Friday 17:00 New York | Ticks per minute (integers) | 41 anchor pairs are simulated and 40 crosses derived. Weekend gaps. |
| stocks | 74 US large caps (AAPL, MSFT, NVDA, JPM, ...) | NYSE session, holidays, early closes | Shares | Overnight and weekend gaps. U-shaped intraday volatility and volume. |

List them all with `marketforge list-instruments` or `mf.instruments()`.

## Trading calendars

- **Crypto** never closes.
- **Forex** trades from Sunday 17:00 to Friday 17:00 New York time, following New York's daylight saving time.
- **Stocks** trade the NYSE session, 09:30 to 16:00 New York time, on NYSE trading days. NYSE holidays are skipped and early closes (13:00) are honoured.

No candle is printed while a market is closed. A **gap** between the last close of a session and the first open of the next comes from the price moving during the closure, as it does in reality, not from an injected event.

## Arbitrage-free forex

Only one **anchor pair** per currency code is simulated; every **cross** is derived from them, so `EURJPY == EURUSD * USDJPY` at every minute and every triangle is arbitrage-free. Each price is then rounded to its own tick, as quotes are, so the identity holds to within two ticks of the cross, far inside the spread. Crosses take their volatility and start price from their anchor pairs. See [ADR 0002](../../adr/0002-derive-forex-crosses-from-anchor-pairs/).

## Correlations

Each catalog states the correlations that matter (BTC-ETH 0.88, AAPL-MSFT 0.78, EURUSD-GBPUSD 0.82) and fills the other pairs with a market default. Those values cannot all hold at once, so MarketForge uses the valid correlation matrix that comes closest to the stated pairs, giving the defaults little weight. Crypto and stocks keep their stated pairs to within 0.05. Forex is fitted through its anchors, so the crosses' correlations and volatilities follow from them. It keeps its anchor pairs to 0.04 on average, and its crosses at 0.7 to 1.2 times their stated volatilities, where the catalog contradicts itself. See [ADR 0012](../../adr/0012-fit-correlations-to-what-the-catalog-states/).

## Catalog parameters

Annual volatility and drift in the catalog are what you get (for forex crosses, approximately: see Correlations above): regime multipliers are normalised so they change *when* volatility and drift happen, not how much. `start_price` is the price at the start of the range, whatever date that is: a range starting in 2015 starts at the same prices as one starting in 2024. Change any of them with an [override file](../../guides/custom-instruments/).

## Known simplifications

- The index and oil CFDs in the forex catalog (GRXEUR, SPXUSD, WTIUSD, ...) trade on the forex calendar, nearly 24/5. Their real sessions and daily maintenance breaks are not modelled.
- Forex trades through Christmas and New Year's Day, as it does in reality, but thinly: volatility and tick volume fall to about a third of normal and spreads widen, and to about two thirds on the days around them.
- One-off NYSE closures (9/11, Hurricane Sandy, national days of mourning) are not modelled.
- Stocks report earnings (see [Model](../model/)), but pay no dividends and never split: prices are total-return-like and unadjusted, and a stock that rises far is never split back down.
- Forex tick-volume levels, and forex and stock spread levels, are estimates, not measurements.
