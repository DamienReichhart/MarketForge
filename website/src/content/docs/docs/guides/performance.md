---
title: Performance and scale
description: "How long a generation takes, how much disk and memory it needs, how to size a run before starting it, and what actually makes large runs faster."
---

MarketForge simulates every open minute of every instrument you ask for, so the cost of a run is roughly **open minutes × instruments**, plus the time to write the candles. A few rules of thumb, then the tools to size a run exactly.

## How long things take

Measured on a 4-core Linux machine, CSV unless stated:

| Run | Files | Size | Time |
| --- | --- | --- | --- |
| One year of EURUSD, 8 timeframes | 8 | 27 MB | 2 s |
| 90 days of all 53 crypto instruments, 8 timeframes | 424 | 620 MB | 7 s |
| 30 days of all 208 instruments, 8 timeframes | 1,664 | 450 MB (220 MB Parquet) | 7 to 9 s (4.5 s Feather) |
| Ten years of all 208 instruments, 8 timeframes | 1,664 | 59 GB (29 GB Parquet) | about 12 min (10 as Parquet), estimated |

The first run in a fresh environment adds a second or two while Numba compiles the kernels. They are cached on disk, so later runs start at once.

## Size a run before you start it

`--dry-run` prints the plan and its estimates and writes nothing:

```bash
marketforge generate --from 2015-01-01 --to 2025-01-01 --markets all --format parquet --dry-run
```

From Python, [`mf.estimate()`](../../reference/python-api/#estimate) returns the same figures, including the memory `generate()` would need:

```python
import marketforge as mf

plan = mf.estimate(markets="crypto", start="2020-01-01", end="2024-01-01",
                   timeframes=["m5", "H1"], with_regime=True, format="parquet")
print(f"{plan.files} files, {plan.rows:,} rows, {plan.disk_bytes / 1e9:.1f} GB on disk, "
      f"{plan.memory_bytes / 1e9:.1f} GB in memory, ~{plan.wall_seconds(jobs=3):.0f} s")
```

## Memory: disk streams, memory does not

- **`generate_to_disk()` and `marketforge generate` stream.** The simulation runs one day at a time and each day's candles are written before the next is simulated, so memory barely grows with the range: one market of 53 coins peaks at about 0.5 GB for a month and 0.6 GB for a year, and all 208 instruments as Parquet at about 1 GB.
- **`mf.generate()` holds everything.** Every candle of every timeframe is in memory at the end. Ten years of all 208 instruments would need about 83 GB. Check `estimate(...).memory_bytes` first, and write to disk anything that does not fit.

To work with a dataset larger than memory, write it as Parquet and query it in place with DuckDB or polars' lazy scans: see [Working with the data](../working-with-data/#duckdb).

## What makes a run faster

In order of effect:

1. **Ask for less.** Only the instruments you request are computed past the random draws, so `-i BTCUSD,ETHUSD` is far cheaper than `--market crypto`. Timeframes are aggregated from the same minutes, so dropping them saves disk more than time; `m1` is the largest file by far.
2. **Write Feather or Parquet.** Formatting CSV text is a large share of a big run. Feather is the fastest to write and to read; Parquet is the smallest. See [Output format](../../reference/output/#csv-parquet-or-feather).
3. **Run markets in parallel with `--jobs`.** Each market is simulated on one core, so `--jobs` only helps a request spanning several markets, and it cannot make one market faster. Writing is partly shared, so three markets on three cores take less than the sum, not a third of it.
4. **Run seeds in parallel processes.** For many independent datasets (train/validation/test splits, stress tests), [`mf.generate_many()`](../../reference/python-api/#generate_many) runs one seed per process on every core, or run several `marketforge generate` processes, one per seed, into different directories.

```python check=static
# 64 seeds of 90 days, one process per core, yielded in seed order
for data in mf.generate_many("BTCUSD,ETHUSD", seeds=range(64), start="2024-01-01", days=90,
                             timeframes=["m5"], with_regime=True):
    ...
```

In a script, call `generate_many()` under `if __name__ == "__main__":`, as any Python multiprocessing needs.

## Long ranges, in steps

A dataset can grow a piece at a time with [`marketforge extend`](../extend/), and the result is exactly the dataset one long run would have produced. That makes it safe to generate a year now and the next one later, or to resume a large run in chunks you can schedule.

## Open file limits

A Parquet or Feather file can only be finished, not appended to, so every one of them stays open until the run ends. A run of 1,664 files needs about that many file descriptors. MarketForge raises the process's soft limit towards the hard limit when needed (macOS defaults to 256), and stops with an `OSError` before simulating anything if that is not enough. Then raise the limit with `ulimit -n 4096`, ask for fewer instruments or timeframes, or write CSV, which is appended to day by day.

## In the browser

The [playground](../../../playground/) runs the same package with Pyodide, without Numba, so it is 10 to 100 times slower and caps the size of a request. Use it to try MarketForge, and the installed package for real datasets.
