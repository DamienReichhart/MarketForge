# Extend datasets from an exact checkpoint

A dataset could not be continued: the simulator restarts its prices, volatility, regime and volume memory at `--from`, so generating the next month separately produced a discontinuity, and the only way to add a month to ten years was to regenerate ten years. `extend` now continues a dataset so that it equals, byte for byte in CSV, what one longer generation would have produced.

Every dataset carries a manifest, `marketforge.json`, with the version, seed, range, instruments, timeframes, formats, the resolved overrides and a checkpoint per market. The checkpoint is the simulator's exact state at the start of a UTC day eight days before the dataset's last day, plus the last candle published per timeframe. An extension restores that state, re-simulates from that day and publishes only the candles after the ones already written.

Alternatives we rejected:

- **Reconstructing state from the candle files.** The last close is rounded to 8 decimals and says nothing about GARCH variance, the regime or volume memory, so the continuation could only be approximately right, which breaks the reproducibility contract.
- **Checkpointing at the very end of the dataset.** The candles still open at the end (up to a week of minutes for `W1`, for every instrument) would have to be stored too: tens of megabytes, and a second code path for partial days. Resuming eight days back rebuilds every open candle from its first minute through the ordinary path, for a second or two of simulation at most, and a checkpoint of a few hundred numbers. Eight days is enough because the longest candle is a week.
- **Anchoring `start_price` to a fixed calendar date**, so that any range is a window on one infinite path. Every generation would then have to simulate from that date.
- **A `--continue` flag on `generate`.** It would accept a different seed or instrument list and produce a silently inconsistent dataset. `extend` takes everything but the new end from the manifest. The manifest stores override values, not a path or a hash, so a dataset can be extended without the file that made it, and overrides passed as a dict work too.

## Consequences

- **Forward only, within a major version.** Earlier history cannot be prepended, and a dataset written by another major version is refused, since a seed's candles may differ.
- **Datasets written before 4.0 cannot be extended**: they have no manifest.
- **Parquet files are rewritten** on extension (existing rows copied, new ones added) because Parquet cannot be appended to. We kept one file per instrument and timeframe rather than part files, which every existing reader would have had to learn.
- **Extension is all-or-nothing.** A journal records the size of every CSV file before it is appended to; rewritten Parquet files are staged beside the originals and swapped in after the new manifest is ready. A failed or killed extension is undone, or completed, the next time the dataset is extended.
- The custom instrument parameters in a manifest are readable by anyone who receives the dataset.
- Building this exposed that a flash crash was positioned among the candles a range kept of its day, so it moved with `--to`. It is now positioned in the day's whole session, which changes flash-crash output on partly covered days.
