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

Only one **anchor pair** per currency code is simulated; every **cross** is derived from them, so `EURJPY == EURUSD * USDJPY` at every minute and every triangle is arbitrage-free. Crosses take their volatility and start price from their anchor pairs. See [ADR 0002](../../adr/0002-derive-forex-crosses-from-anchor-pairs/).

## Catalog parameters

Annual volatility and drift in the catalog are what you get: regime multipliers are normalised so they change *when* volatility and drift happen, not how much. `start_price` is the price at the start of the range, whatever date that is: a range starting in 2015 starts at the same prices as one starting in 2024. Change any of them with an [override file](../../guides/custom-instruments/).

## Known simplifications

- The index and oil CFDs in the forex catalog (GRXEUR, SPXUSD, WTIUSD, ...) trade on the forex calendar, nearly 24/5. Their real sessions and daily maintenance breaks are not modelled.
- Forex is open on Christmas and New Year's Day.
- One-off NYSE closures (9/11, Hurricane Sandy, national days of mourning) are not modelled.
- Forex tick-volume levels, and forex and stock spread levels, are estimates, not measurements.
