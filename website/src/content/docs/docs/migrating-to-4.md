---
title: "Migrating to 4.0"
description: "What changes when you upgrade from MarketForge 3.x to 4.0, and what to edit."
---

4.0 renames a few options, changes some outputs, and **changes the candles every seed produces**: the model is more realistic (see the [changelog](../../changelog/)). Upgrading takes a few edits.

## Rename

| 3.x | 4.0 |
| --- | --- |
| `--assets`, `-a` | `--instruments`, `-i` |
| `marketforge list-assets` | `marketforge list-instruments` |
| `generate(assets=...)`, `generate_to_disk(assets=...)` | `instruments=...` |
| `marketforge --from ...` (no subcommand, deprecated in 3.0) | `marketforge generate --from ...` |
| `--threads`, `--thread-count` (deprecated in 3.0) | `--jobs` |
| `--batch-size` (ignored since 3.0) | remove it |

## Expect different candles

The same seed gives different candles in 4.0. Regimes now trend, correlations are those the catalog states and intensify in crashes, big candles have wicks, and forex sessions follow their own clocks. If an experiment needs the old data, keep it pinned to `marketforge==3.1.1`.

From 4.0 on, any release may change a seed's candles when that makes the data more realistic, and lists it under *Output changes*. Pin the exact version to keep a dataset identical (see [Reproducibility](../reference/reproducibility/)).

## Code that reads files

- **The regime column holds names** (`trend_up`, `range`, ...), not codes 0 to 4. Replace `df.regime == 2` with `df.regime == "range"`. Or load with [`mf.read()`](../reference/python-api/#read), which returns a categorical whose `.cat.codes` are the old codes.
- **Generating into a directory that holds a dataset is refused.** Pass `--overwrite` (`overwrite=True`) to replace it.

## Other changes

- **Seeds must be integers:** `seed=1.5` raises `TypeError`.
- **`validate` refuses candles that are not m1.**
- **Ranges cannot start before 1970.**
- **scipy is no longer installed with MarketForge.** Install it yourself if your own code imports it.
- **Datasets written by 3.x have no manifest**, so they cannot be extended. Generate them again with 4.0.
