---
title: "Migrating to 5.0"
description: "What changes when you upgrade from MarketForge 4.x to 5.0, and what to edit: renamed arguments and options, the new default timeframes, GeneratedData, and the new model."
---

5.0 gives Python and the command line one vocabulary, makes `GeneratedData` a complete object, and **changes the candles every seed produces**: the markets are linked, prices sit on ticks, stocks report earnings (see the [changelog](../../changelog/)). The old names fail with a message that names the new one, so a run tells you every edit to make.

## Rename

| 4.x | 5.0 |
| --- | --- |
| `fmt=` (`generate_to_disk`, `estimate`) | `format=` |
| `include_regime=`, `include_spread=`, `include_bid_ask=` | `with_regime=`, `with_spread=`, `with_bid_ask=`, as on the command line |
| `generate --market`, `list-instruments --market` | `--markets` (`-m` is unchanged) |
| `--config FILE` | `--overrides FILE` |
| `marketforge validate --input PATH` | `marketforge validate PATH` |

`validate --market` and `calibrate --market` keep their name: each takes the one market whose bands or calendar apply.

## Expect more timeframes from `generate()`

`generate()` returned `m1` only; like the command line and `generate_to_disk()`, it now returns the eight standard timeframes, `m1` to `W1`. Pass `timeframes="m1"` to keep 4.x's memory use, and `timeframes="all"` for all 17.

## `GeneratedData` is not a dict

It is a read-only mapping: `data["BTCUSD"]["H1"]` works as before (and so do `data["btcusd", "h1"]` and `data.frame("BTCUSD", "H1")`), but there is no item assignment, `.setdefault()` or `.update()`, and `.copy()` returns a `GeneratedData`. Its symbols are **sorted**, so `list(data)`, `panel()` columns and the instrument axis of `to_numpy()` are in alphabetical order, not request order. See [GeneratedData](../reference/python-api/#generateddata) for what it adds.

## Handle errors that were warnings

- A range in which every requested market is closed (a stock on a Saturday), or that holds no complete candle of any requested timeframe, raises `ValueError` and writes nothing. It used to write header-only files and exit 0.
- A time too large to be Unix seconds, such as Unix milliseconds, raises `ValueError`: divide it by 1,000.
- `validate()` refuses fewer than 1,950 `m1` candles, a week of stock sessions.

## Expect different candles

Model revision 2 links the markets, quotes every price on its tick, rounds stock volume to whole shares, adds earnings, auctions, pegs, holiday liquidity, microstructure noise and slow volatility, and makes regime spells last a typical length. A 4.x seed gives other candles, and 4.x datasets cannot be extended by 5.0: generate them again, or keep the version that wrote them (`pip install "marketforge<5"`). `marketforge info` says which version can extend a dataset.

Code that compared prices with `==` against arithmetic (`EURJPY == EURUSD * USDJPY`) needs a tolerance of a couple of ticks, since each price is rounded to its own.

## Files

- Feather files are uncompressed, so they are zero-copy to read and about the size of CSV. Write Parquet for small files.
- The manifest spells its flags `with_regime`, `with_spread` and `with_bid_ask`, and records the layout and each file's checksum. 5.0 reads 4.x manifests.
