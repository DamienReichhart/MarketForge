# Simulate the whole market jointly, day by day, with shocks keyed by minute

Memory used to be bounded by splitting a market into asset batches of 25 and simulating each batch independently. That silently destroyed correlation and the shared regime across batches, and made output depend on `--batch-size`, thread count and `--assets`. We now always simulate every instrument of a market together and bound memory by walking time one UTC day at a time, carrying model state (prices, GARCH variance, regime, volume memory) across days. Every random draw for a day comes from a generator seeded by `(seed, market, day)` and is indexed by minute-of-day, so the same seed reproduces the same paths whatever subset is written, and extending `--to` never changes earlier candles.

## Consequences

- ~~`--assets` only filters what is written; it no longer makes generation cheaper.~~ Amended in 3.1 by [ADR 0007](0007-optimise-without-changing-a-single-bit.md): every *random draw* is still made for the whole market, but the computation after the draws runs only for the requested instruments and the factors they are built from. Column-wise operations make that bit-identical, so the reproducibility guarantee is unchanged.
- Draws are made for all 1440 minutes of a day even when the market is open for 390 of them; we accept the wasted random numbers for exact prefix stability.
- Any change to the order or shape of per-day draws changes every seed's output and so needs an *Output changes* entry and a `MODEL_REVISION` increment ([ADR 0011](0011-realism-over-seed-stability.md)).
