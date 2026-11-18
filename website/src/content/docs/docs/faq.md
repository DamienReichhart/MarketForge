---
title: FAQ and troubleshooting
description: "Answers to the questions people ask about MarketForge, and the fix for every common error: existing datasets, empty files, slow first runs, multiprocessing, open file limits, verify mismatches and failed validations."
---

## Errors and surprises

### "already holds a MarketForge dataset"

`generate` refuses a directory that holds a dataset, so two datasets never mix. Either add `--overwrite` (`overwrite=True`) to replace it, which deletes only the files MarketForge wrote, or continue it with [`marketforge extend`](../guides/extend/), or pick another `--output-dir`.

### A file is empty, with "No candles for ..."

The range holds no complete candle of that timeframe for that instrument. Either the market was closed for the whole range (a stock over a weekend, forex on a Saturday), or the range is shorter than the candle (a `W1` file from a ten-day range that covers no full Monday-to-Monday week). Candles are only written when the range covers every open minute of them, so partial candles at either end are dropped. Lengthen the range or drop the timeframe.

### "Unknown instrument(s)"

Run `marketforge list-instruments` to see the catalog; symbols are case-insensitive. A symbol that is not in it needs an [override file](../guides/custom-instruments/) that declares it, with its `market`.

### The first run is slow

The first generation in a fresh environment compiles the Numba kernels, which takes a second or two, then caches them on disk next to the package. If that directory is read-only, as in some container images, Numba caches in your user cache directory instead; set `NUMBA_CACHE_DIR` to choose where, for example to a directory your image keeps.

### `generate_many()` fails or starts the script again

`generate_many()` runs seeds in separate processes, which import your script again. On macOS and Windows, a script that calls it at the top level fails or recurses. Put the call under a main guard:

```python check=static
import marketforge as mf

def main():
    for data in mf.generate_many("BTCUSD", seeds=range(16), start="2024-01-01", days=30):
        ...

if __name__ == "__main__":
    main()
```

Notebooks and the REPL need nothing.

### "Parquet output keeps every file open"

Parquet and Feather files stay open until the run ends, and the run needs more file descriptors than the process may open. Raise the limit (`ulimit -n 4096`), request fewer instruments or timeframes, or write CSV. See [Performance and scale](../guides/performance/#open-file-limits).

### `extend` or `verify` refuses a dataset written by another version

A dataset can only be extended or verified by a release with the same model revision as the one that wrote it, because other revisions produce other candles for the same seed. `marketforge info` names the version that can; install it in a separate environment, such as `pip install marketforge==4.0.0`, or generate the dataset again.

### `verify` reports differences on another machine

Candle values are bit-for-bit identical on a given platform and NumPy build. Across CPUs, NumPy can pick different `exp` and `log` implementations that differ in the last bit on a few inputs, so a dataset copied to another kind of machine may not verify there. The values agree to rounding. See [Reproducibility](../reference/reproducibility/#across-machines).

### `validate` fails on my file

- **It needs `m1` candles.** The bands describe minute returns; other timeframes are refused.
- **Short samples are noisy.** The bands allow for sampling noise, but a day or two of minutes is not enough to measure long memory or tails. Validate at least two weeks.
- **Forex and stock bands are provisional.** They are estimates until real reference data is measured, and their reports say so. A real forex file outside them may be showing a band that is wrong, not data that is: [open an issue](https://github.com/DamienReichhart/MarketForge/issues) with the measurement.
- **Anomalies are excluded from realism.** A dataset generated with `--anomalies` is deliberately unrealistic and may fail some checks.

### My stock `H1` candles start at :30, my forex `D1` candles at 21:00 or 22:00 UTC

That is the market's clock. Stock candles are aligned on the 09:30 New York open, forex days start at 17:00 New York (21:00 or 22:00 UTC, depending on daylight saving time), and crypto uses the UTC clock. Timestamps are always UTC and mark the start of the candle. See [candle alignment](../reference/output/#candle-alignment), and [Working with the data](../guides/working-with-data/#several-instruments-side-by-side) for lining up markets.

### The playground's candles are not byte-identical to the installed package's

The [playground](../../playground/) runs the same package in the browser, with the kernels as plain Python instead of Numba. NumPy's `exp` and `log` round the last digit differently in WebAssembly, so about a third of the values differ in the 12th significant digit or beyond. The candles are the same to any practical precision, but they do not verify byte for byte against an installed MarketForge. Generate datasets you rely on with the installed package.

## The data

### Can a strategy that works on MarketForge make money?

Not on that evidence. MarketForge reproduces the statistics of real markets and contains no edge that carries over to them. A strategy that makes money on synthetic data has proved it runs, not that it works; a consistent profit across seeds more likely points to a look-ahead bug, or to a strategy that has learnt the generator's regimes. See [What it is not](../limits/).

### Is `AAPL` Apple's price history?

No. Symbols are labels for parameter sets: a start price, volatility, drift, volume level, spread and correlations typical of that instrument. Every range starts at the catalog's start prices, whatever its dates.

### Why does a range starting in 2015 start at the same price as one starting in 2024?

For the same reason: `start_price` is the price at the start of whatever range you ask for. Change it in an [override file](../guides/custom-instruments/) if the level matters to you; for modelling, use returns, which carry no information about the level.

### Does the same seed give the same data in every version?

Within a version, always: the same seed gives the same candles, whatever instruments, timeframes, format or `--jobs`. Across versions, not necessarily: realism comes before seed stability, and a release that changes a seed's candles increments the model revision and lists the change under *Output changes* in the [changelog](../../changelog/). Pin the version to keep a dataset identical.

### Are the instruments of a market independent?

No. All instruments of a market are simulated together: they share a correlation matrix, tail risk and the regime, and their correlations intensify in crashes. Instruments of different markets are independent of each other.

### Is there tick data, an order book or news?

No. MarketForge produces candles from `m1` up, around a mid price, with an optional quoted spread. There is no order book, no market impact and no news. See the [known simplifications](../limits/#known-simplifications-of-the-model).

### How many seeds do I need?

As many as the question needs. Each seed is an independent history; for a distribution of outcomes, hundreds are cheap, and [`generate_many()`](../reference/python-api/#generate_many) runs them on every core.

## The project

### Can I use it at work, in closed-source code? Who owns the data?

Yes, under the Apache-2.0 licence, and the data is yours to use, sell or publish. See [Licence](../licence/).

### How do I cite MarketForge?

The repository has a [`CITATION.cff`](https://github.com/DamienReichhart/MarketForge/blob/main/CITATION.cff); GitHub's *Cite this repository* button formats it. Record the version and seed next to your results, or keep the dataset's `marketforge.json`, which holds both.

### Something is missing or wrong

[Open an issue](https://github.com/DamienReichhart/MarketForge/issues), and report a security problem [privately](../security/).
