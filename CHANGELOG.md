# Changelog

## 3.0.0

A rewrite of the simulation pipeline. **The same seed produces different data
than 2.x**: every change below alters output, so the major version moves.

### Correctness
- Stocks and forex no longer trade 24/7. Candles exist only for minutes the
  market's trading calendar marks open (NYSE session with holidays and early
  closes; forex Sunday 17:00 to Friday 17:00 New York; crypto 24/7).
  Overnight and weekend gaps arise from those closures.
- Volume no longer explodes. In 2.x a single minute could hold ~50% of a
  week's volume.
- Correlation and the market regime are shared by the whole market. 2.x split
  markets into independent batches of 25 assets.
- Forex crosses are derived from anchor pairs, so `EURJPY == EURUSD * USDJPY`
  (2.x allowed free triangular arbitrage).
- Daily and weekly candles align to calendar boundaries (00:00 UTC, 17:00 New
  York, the NYSE open; Mondays). 2.x anchored them to `--from`. Partial
  candles are dropped.
- The configured annual drift and volatility are what is produced. In 2.x,
  regime multipliers dragged stocks and crypto drift negative.
- Calibration fixes that remove variance blow-ups (stocks GJR-GARCH, crypto
  Student-t degrees of freedom) and oversized forex weekend gaps.
- Each instrument's `volume_volatility` is used; it was ignored before.

### Reproducibility
- A seed now reproduces identical candles whatever instruments, timeframes,
  format or parallelism are chosen, and extending the end date never changes
  earlier candles.
- A random seed is printed (CLI) or returned (`result.seed`) so any run can be
  repeated.

### Features
- Python API: `marketforge.generate()` (DataFrames in memory) and
  `marketforge.generate_to_disk()`.
- CLI subcommands `generate`, `list-assets`, `validate`. Also new: ISO dates
  for `--from`/`--to`, `--dry-run` estimates, `--format parquet`,
  `--with-regime`, `--config` TOML overrides, `--jobs`, and a working
  `--debug`.
- TOML override files to change catalog instruments or add new ones.
- Optional regime label column.

### Performance
- Per-minute recursions are compiled with Numba, and simulation streams day by
  day, so memory no longer grows with the range. A year of EURUSD across all 8
  timeframes takes about 5 s; in 2.x, m1 alone took 10.5 s.
- CSV is written through pyarrow (about 10× faster). Parquet files are about
  half the size of CSV.

### Validation
- The validator uses open-to-close returns, which excludes gaps. Range
  efficiency is now a ratio of means: it gave `inf` for quiet instruments
  before. Leverage bands allow for sampling noise and FX cross conventions.

### Removed / breaking
- The `gaps` anomaly. Closures produce gaps now.
- `--batch-size`, which is ignored. `--threads` becomes `--jobs`.
- `ReturnGenerator`, `OHLCVBuilder`, `GeneratorConfig`, `AssetConfig`,
  `generate_market_batched` and the `processing`, `generators`, `markets` and
  `utils` packages.
- The `marketforge --from ...` form without a subcommand still works for one
  release and prints a deprecation note.
