---
title: Core concepts
description: "The handful of ideas MarketForge is built on: instruments and markets, the minute simulation, timeframes, regimes, seeds, datasets and their manifest, and model revisions."
---

MarketForge has a small vocabulary. Once these eight ideas are clear, every option on the [command line](../reference/cli/) and in the [Python API](../reference/python-api/) follows from them.

```text title="From a request to a dataset"
 seed ──┐
        ▼
 market ── simulated jointly, minute by minute, on its trading calendar
        │    (shared shocks, shared regime, correlated instruments)
        ▼
 m1 candles of every instrument ──► aggregated to m5 … W1 on the market's clock
        │
        ▼
 dataset: {market}/{SYMBOL}_{timeframe} files + marketforge.json (the manifest)
```

## Instruments, markets and the catalog

An **instrument** is a symbol, such as `BTCUSD`, `EURUSD` or `AAPL`, with a set of model parameters: a start price, an annual volatility and drift, a volume level, a spread and its correlations with the others. The **catalog** is the 208 built-in instruments; list them with `marketforge list-instruments` or `mf.instruments()`.

A **market** is a family of instruments that share a trading calendar, a regime and a set of model behaviours: `crypto` (53 instruments, 24/7), `forex` (81, Sunday to Friday) and `stocks` (74, the NYSE session). You ask for instruments, markets, or both, and MarketForge works out which markets to simulate.

The symbols are labels for parameter sets. MarketForge's `AAPL` has the volatility and correlations of a US large cap; its path is not Apple's history. See [What it is not](../limits/).

You can change any catalog instrument or add your own with an [override file](../guides/custom-instruments/).

## The simulation runs one market, one minute at a time

Every market is simulated **minute by minute, one UTC day at a time**, carrying its state (prices, volatility, regime, volume) from one day to the next. All instruments of a market are simulated together, so they share shocks and a regime: in a crypto sell-off, every coin falls at once.

Minutes when a market is closed are not simulated and produce no candle. The price still moves while it is shut, so the first candle after a closure opens with a **gap**. See [Markets & calendars](../reference/markets/) and [The model](../reference/model/).

## Timeframes are aggregated from minutes

Only `m1` candles are simulated. Every other **timeframe**, from `m2` to `W1`, is aggregated from them, on the market's own clock: forex days start at 17:00 New York, stock days at the 09:30 open, crypto days at 00:00 UTC. So an `H1` candle is exactly the six `m10` candles of its hour, and a candle is never published unless the range covers every open minute of it.

Asking for more timeframes costs disk space and little time: the simulation is the same.

## Regimes are the hidden state

At every minute a market is in one of five **regimes**: `trend_up`, `trend_down`, `range`, `high_volatility` or `crash`. The regime sets the drift and scales the volatility and correlations of every instrument in the market. It lasts hours to days and changes gradually.

Real data never tells you which regime it was in. MarketForge does: with `--with-regime` or `with_regime=True`, each candle carries the regime at its close. It is a ground-truth label for supervised learning and an answer key for regime detectors. See [Regimes](../reference/model/#regimes).

## Candles are mid prices; the spread is a column

`open`, `high`, `low` and `close` are **mid prices**, halfway between bid and ask. With `--with-spread`, each candle also carries its mean quoted **spread**, so `bid = price - spread / 2` and `ask = price + spread / 2`; `--with-bid-ask` writes those quotes around the close for you. Asking for the spread changes no other column. See [Bid-ask spread](../reference/spread/).

## A seed fixes everything

A **seed** is a non-negative integer. For a given version, `(seed, market, minute)` determines every random shock, so a seed always gives the same candles, bit for bit, whichever instruments, timeframes, format or parallelism you choose, and whether you generate a range at once or extend it in steps. Without a seed, MarketForge draws one and prints it, and records it in the manifest.

Different seeds give independent histories of the same market. That is how you build train, validation and test sets that share no path, or a thousand alternative years for a [stress test](../use-cases/stress-testing/). See [Reproducibility](../reference/reproducibility/).

## A dataset carries its own recipe

A **dataset** is a directory written by `marketforge generate` or `mf.generate_to_disk()`: one file per instrument and timeframe, under its market, plus **`marketforge.json`, the manifest**. The manifest records everything needed to make the dataset again: the version, the model revision, the seed, the range, the instruments, the options and the resolved overrides, plus a checkpoint of the model's state at the end.

That is what makes three commands possible:

- [`marketforge info`](../reference/cli/#info) tells you what a dataset is and how it was made;
- [`marketforge extend`](../guides/extend/) continues it, exactly as one longer run would have;
- [`marketforge verify`](../guides/extend/#verify-a-dataset) regenerates it and proves it was not altered.

`mf.generate()` returns the same candles in memory instead, with no manifest. See [Output format](../reference/output/).

## Versions and model revisions

MarketForge puts realism before seed stability: a release may change what a seed produces when that makes the data more realistic. Each such release increments the **model revision** (`mf.MODEL_REVISION`) and lists the change under *Output changes* in the [changelog](../../changelog/). The manifest records both the version and the model revision, and a dataset can only be extended or verified by a release with the same model revision.

To keep a dataset identical, pin the exact version: `pip install marketforge==4.0.0`.

## Next

- [Quick start](../quick-start/) to make your first dataset.
- [Working with the data](../guides/working-with-data/) to load it into pandas, polars, DuckDB or a tensor.
- The [glossary](../reference/glossary/) for every other term.
