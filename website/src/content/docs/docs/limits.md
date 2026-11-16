---
title: What it is not
description: "The honest limits of synthetic market data, and of MarketForge's model in particular."
---

MarketForge is useful precisely because it is honest about what synthetic data can and cannot do. Read this page before you draw conclusions from anything trained or tested on it.

## It is not a source of alpha

A model trained only on MarketForge data learns MarketForge's generator. The generator reproduces the *statistics* of real markets (heavy tails, volatility clustering, the leverage effect, correlation, intraday seasonality), but it contains **no exploitable edge that carries over to real markets**. There is nothing in it to discover about BTC, EURUSD or AAPL.

Two consequences:

- **A strategy that makes money on synthetic data has proved that it runs, not that it works.** Profit on MarketForge data is at best a sign that the strategy exploits the generator's own structure, for example by detecting its regimes.
- **Do not judge a model by its synthetic test score alone.** Use synthetic data to build, pre-train, augment and stress-test; use real, out-of-sample data to decide whether anything earns money.

## It is not real market data

Instrument symbols (`BTCUSD`, `AAPL`, ...) are labels for sets of model parameters: a start price, a volatility, a drift, a volume level and correlations. The price paths are not, and do not try to be, the history of those instruments. `start_price` is the price at the start of whatever range you ask for: a range starting in 2015 starts at the same prices as one starting in 2024.

Never present MarketForge output as real data. See the [terms of use](../../legal/terms/).

## What it is good for

| Use | Why synthetic data helps |
| --- | --- |
| Pre-training and data augmentation | Unlimited, realistic sequences; a model can learn the "grammar" of markets before it sees scarce real data. |
| Supervised learning on hidden states | Every candle can carry the regime that produced it: ground truth real data cannot provide. |
| Testing backtesters and pipelines | Calendars, gaps, closures, spreads and multi-asset alignment that behave like a real feed, at any scale. |
| Stress testing | Thousands of alternative histories, crashes included, instead of the one that happened. |
| Teaching and research | A known data-generating process: you can check whether a method recovers what was put in. |

## Known simplifications of the model

- **Regimes are a five-state process shared by a market.** Real markets have richer, overlapping states; MarketForge's labels are clean by construction.
- **No order book, no market impact, no news.** Candles summarise a mid price; the spread is a separate, modelled column. Your orders do not move the price.
- **Forex and stock calibration is provisional.** Crypto bands and spreads are anchored on measured Binance data. Forex and stock bands, forex tick-volume levels and forex and stock spread levels are estimates, and their validation reports say so.
- **Calendars are simplified in places.** The index and oil CFDs in the forex catalog trade on the forex calendar (nearly 24/5) without their real sessions and maintenance breaks. Forex is open on Christmas and New Year's Day. One-off NYSE closures (9/11, Hurricane Sandy, national days of mourning) are not modelled.
- **No corporate actions.** No splits, dividends, delistings or symbol changes.
- **Anomalies are deliberately unrealistic.** `spikes` and `flash_crash` are stress events layered on top of the realistic base, not part of it.

Found a property of real markets that matters to you and is missing? [Open an issue](https://github.com/DamienReichhart/MarketForge/issues).
