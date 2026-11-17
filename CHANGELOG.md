# Changelog

## 4.0.0

Datasets can be extended, candles can carry a bid-ask spread, the Python API
covers what the command line does, and MarketForge is now Apache-2.0.
**Realism now comes before seed stability**: seeds produce different candles
from 3.1.1 (see Output changes), and any later release may change them again
when that makes the data more realistic. The major version is for the renamed
options and parameters.

### Output changes
- **Flash crashes on a partly covered day move.** With the `flash_crash`
  anomaly, a crash was placed among the candles the range kept of its day, so
  changing `--to` within that day moved it and rewrote earlier candles,
  against the promise that `--to` does not change earlier candles. It is now placed in the day's whole
  session. Only days the range covers partly (a range that does not start or
  end at midnight UTC) are affected, and only with `flash_crash`.

### Licence
- **MarketForge is now Apache-2.0**, not AGPL-3.0-or-later, so it can be
  imported into closed-source pipelines and services without copyleft
  obligations. Versions released before 4.0 stay under the AGPL they shipped
  with. The data MarketForge generates was never covered by either licence.

### Breaking changes
- **"Asset" is now "instrument" everywhere**, as the glossary has said since
  3.0. `--assets`/`-a` is `--instruments`/`-i`, `list-assets` is
  `list-instruments`, and `generate()` and `generate_to_disk()` take
  `instruments=` instead of `assets=`. The old names are removed.
- **A seed must be an integer.** `seed=1.5`, `seed=True` and `seed="7"` raise
  `TypeError`; 1.5 used to be truncated to 1 without a word.
- **`validate` refuses candles that are not m1.** The bands describe minute
  returns, and an H1 file used to pass as realistic.
- **Reproducible per version, not per major version.** A seed's candles are
  fixed for one exact version (and platform), and any release may change them
  to make the data more realistic, listing the change under *Output changes*
  and incrementing `marketforge.MODEL_REVISION`. The manifest records the
  revision, and `extend` continues only datasets written with the same one.
  Pin the version to keep a dataset identical. See
  [ADR 0011](docs/adr/0011-realism-over-seed-stability.md).

### Extendable datasets
- **`marketforge extend ./data --to 2025-03-01`** (or `--days 30`) and
  `mf.extend(dataset, end)` continue a dataset. The result is exactly what one
  generation up to the new end would have produced; CSV files are
  byte-identical to it. An extension that fails or is killed leaves the
  dataset as it was.
- **Every dataset has a manifest**, `marketforge.json`: version, seed, range,
  instruments, timeframes, formats, anomalies and the resolved overrides. A
  dataset can always be reproduced, even when the seed was random and the
  terminal output is gone. `DiskReport.manifest` is its path.
- Datasets written before 4.0 have no manifest and cannot be extended. See
  [ADR 0009](docs/adr/0009-extend-datasets-from-an-exact-checkpoint.md).

### Bid-ask spread
- **`--with-spread` / `include_spread=True`** adds a `spread` column: the mean
  quoted spread of the candle, in price units, around prices that are mid
  prices. It widens in turbulent markets, in quiet hours and when a market
  reopens, and is never below one cent for stocks.
- **Crypto spreads are fitted to measured quotes** (Binance USDT-futures best
  bid/ask, February 2024): 0.02 basis points on BTCUSD, about 1 on coins
  under a dollar, barely widening with volatility. Forex and stock levels are
  **estimates**, derived from each instrument's volatility. Set `spread_bps`
  in an override file to match your broker.
- Asking for the spread changes no other column. See
  [ADR 0008](docs/adr/0008-spread-is-an-opt-in-column-around-mid-prices.md).

### Validation
- **Sampling noise is allowed for with standard errors that fit minute
  returns.** The validator assumed 1/sqrt(n), which is 2.5 times too small on
  heavy-tailed, clustered data, so sound two-week samples failed by chance.
  With two-week windows and three seeds, all 624 instrument checks now pass
  (621 before). See
  [ADR 0010](docs/adr/0010-noise-allowances-use-the-samples-own-standard-errors.md).
- **The crypto bands are anchored on seven coins instead of three.** A
  fortnight of XRP reaches an excess kurtosis of 1331, so the ceiling for
  the catalog's alt-coins was too low.
- `scripts/measure_real_data.py` reads Binance best bid/ask archives and
  reports spread statistics.

### Python API
- `mf.validate(data, market)` checks a DataFrame or a file against the
  validation bands, including the spread when there is one.
- `mf.instruments()` returns the catalog as a DataFrame.
- `data.panel("close", "H1")` returns one column per instrument, NaN where a
  market was closed.
- `overrides=` accepts a dict as well as a TOML path.
- Instruments, markets, timeframes and anomalies can be one comma-separated
  string, in any letter case: `mf.generate("EURUSD")` used to fail on
  "unknown instruments E, U, R, S, D".

### Command line
- `--days N` as an alternative to `--to`.
- `--timestamps iso` writes `2024-01-02T14:30:00Z` in CSV files.
- `validate` reads the market from the path of a file MarketForge wrote, so
  `--market` is optional, and its report says "at most 0.26" instead of
  "target [None, 0.26]".
- Timeframes are accepted in any letter case (`-t h1,d1`).
- An unknown instrument suggests the closest symbol (`APPL (did you mean
  AAPL?)`), and a mistake like that no longer ends with a hint about
  `--debug` tracebacks.
- A file that receives no candle now comes with a warning instead of silence.
- `generate` asks for `--output-dir` before it plans anything.

### Website and documentation
- **MarketForge has a website**,
  [damienreichhart.github.io/MarketForge](https://damienreichhart.github.io/MarketForge/),
  with full documentation: guides for training ML models, backtesting and
  stress testing, the command line, the Python API, the model, the spread,
  validation and reproducibility, plus this changelog, the glossary and the
  design decisions. It is deployed from `main` by the CD pipeline.
- The README and the package description present MarketForge for what it
  is used for: training and testing AI trading models and backtesters, with
  a plain statement of what synthetic data cannot do.
- **MarketForge has a visual identity, "Regimes".** The logo is the five
  market regimes as colour bands crossed by one price path, and the same
  colours shade the regimes on the website's chart. The guidelines, the colour
  and type tokens, and every logo, favicon and social image are in
  [`docs/brand`](docs/brand/README.md) and on the site's Brand page. The site
  now sets type in DM Sans and DM Mono, and link previews carry an image.

## 3.1.1

One fix for macOS 15; on Linux, Windows and other macOS versions every seed
produces exactly the candles 3.1.0 produced, and CI now enforces that. This
release also ships the hardened release pipeline.

### Fixes
- **macOS 15: extending a date range could change earlier candles** in the
  last digit (about 1e-16 relative). Apple's Accelerate BLAS on macOS 15
  rounds a row of a matrix product differently depending on how many rows the
  matrix has, and a day cut short by the end (or start) of the range was
  multiplied with fewer rows than the same day in a longer run. Such a day is
  now computed in the shape of its whole trading session, so a minute's
  candle no longer depends on where the range ends. Whole days take exactly
  the same path as before. On macOS 15 only, the candles of a day cut short by
  the range change in the last digit, to the values a longer range already
  produced in 3.1.0.

### Release and supply chain
- Each release carries a **CycloneDX SBOM** (`marketforge-<version>.cdx.json`
  on the GitHub release) and signed build-provenance and SBOM attestations.
  Verify a download with
  `gh attestation verify <file> --repo DamienReichhart/MarketForge`.
- The PyPI release is verified after upload by installing and running it on
  Linux, macOS and Windows.
- `SECURITY.md`: report vulnerabilities privately through GitHub, not in
  public issues.

### Guarantees now enforced by CI
- **Seed reproducibility:** on Linux, macOS and Windows, 786 fixed-seed
  outputs are compared bit for bit with the latest release; any difference
  fails unless the major version is bumped.
- **Semantic versioning:** a release is blocked if a commit since the last
  release is marked breaking (`type!:` or `BREAKING CHANGE:`) and the
  version is not a major bump.

## 3.1.0

Faster generation with **bit-for-bit identical output**: every seed produces
exactly the candles 3.0.0 produced (checked on 4,717 outputs across markets,
anomalies including flash crashes, DST, holidays, subsets and overrides, on
both the newest dependencies and the declared floors). The rules that keep it that
way are recorded in `docs/adr/0007-optimise-without-changing-a-single-bit.md`.

### Breaking changes
- **Python 3.12 or newer.** Python 3.10 and 3.11 are no longer supported
  (`requires-python = ">=3.12"`). pip on those versions keeps resolving to
  3.0.0. NumPy itself already dropped 3.10 after 2.2 and 3.11 after 2.4, which
  left 3.10 users stuck on numpy 2.2. The `tomli` dependency is gone: TOML is
  read with the standard library's `tomllib`.
- **`MarketType`, `AnomalyType`, `RegimeType` and `OutputFormat` are
  `enum.StrEnum`s.** `str()` and f-strings now give the value:
  `str(MarketType.FOREX)` and `f"{MarketType.FOREX}"` are `"forex"`, not
  `"MarketType.FOREX"`. Comparison with strings, hashing, `.value`, `repr()`
  and generated data are unchanged. Code that parsed the `"Class.MEMBER"`
  text must use `.name` instead. Error messages that name a market now read
  `Unknown market: forex`.

### Performance
| Workload (best of 3, one core unless noted) | 3.0.0 | 3.1.0 |
| --- | --- | --- |
| EURUSD, 1 year, 8 timeframes, CSV | 5.2 s | 1.7 s |
| All 208 instruments, 1 month, 8 timeframes, CSV | 10.4 s | 6.0 s |
| Same, Parquet | 7.7 s | 4.1 s |
| Same, CSV, default `--jobs` (one per market) | 14.5 s | 5.8 s |
| Crypto market, 3 months, m1 + H1, in memory | 1.8 s | 0.85 s |

- Only the requested instruments, and the factors they are built from, are
  simulated past the market-wide random draws. Asking for EURUSD no longer
  computes 81 forex instruments to keep one.
- The per-minute price, intrabar and volume pipeline runs in fused Numba
  kernels instead of ~15 full-size NumPy temporaries. A whole-market day is
  about 2× faster.
- Writers round each field once for every instrument and buffer every file,
  CSV included, instead of making one small write per file per simulated day.
  In 3.0 these small writes made the writer, not the simulation, the
  bottleneck, and the GIL contention made `--jobs` slower than one job.
- Weekly and daily aggregation no longer re-copies the open bucket every day.
  m1 candles pass straight through, and the bar clock is computed once per day
  for all timeframes.
- In-memory DataFrames are built with one copy and share their time index.
  This also halves peak memory, because the intermediate concatenation is gone.
- The regime calibration (a multi-million-step chain, up to ~200 MB of
  temporaries) is computed once per process instead of once per simulator.
  Seasonality is cached the same way.
- `--dry-run` estimates use the new cost model and match measured times.

### Fixes
- Parquet output could fail with "Too many open files": every Parquet file
  stays open until the run ends (1,664 for the full catalog), above the
  default limit of 256 on macOS and, for long ranges, 1,024 on Linux. The soft
  limit is now raised towards the hard limit when needed, and the run stops
  before generating anything with a clear message if that is not enough.
- Re-running Parquet generation into the same directory could leave a
  previous run's file in place for a timeframe that received no candle this
  time. Every output is now rewritten from scratch.
- Write buffers are capped at ~2 million rows per market (~100 MB). Before,
  up to 32,768 rows were buffered per file, which could reach gigabytes on
  long full-catalog runs.
- When generation fails, every writer is still closed and the original error
  is raised, not a secondary error from closing files.

### API
- `MarketSimulator(spec, seed, instruments=...)` simulates a subset of a
  market; `DayResult` columns follow the requested order.
- `BarAggregator.push(bars, anchor=None)` accepts precomputed bar-clock
  minutes, shared by several timeframes.

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
- Regimes last hours to days instead of 2–8 minutes (`RegimeParams.minutes_per_step`).
  Regime labels are therefore meaningful, and volatility keeps memory out to a
  day, as in real data.
- Calibrated against real Binance m1 data: intrabar range (high/low use a
  fraction of the bar volatility), crypto intraday cycle, volume persistence.
- Volume has defined units: base-asset units for crypto (BTC was 50,000/min,
  now ~19/min like Binance), integer tick volume for forex, shares for stocks.

### Packaging
- Dependency floors raised to versions that actually work together:
  `numpy>=2.2`, `numba>=0.61.2`, `scipy>=1.13`, `pandas>=2.2.2`,
  `pyarrow>=16`. The previous floors could not be installed together, and
  numpy < 2.2 broke the "extending the range never changes earlier candles"
  guarantee. CI now tests the floors.
- Python 3.14 is supported and tested.
- The `dev` extra is replaced by PEP 735 dependency groups
  (`pip install -e . --group dev`), so test tools are no longer published in
  the package metadata.
- The package ships a `py.typed` marker.

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
- Bands are anchored to statistics measured on real m1 data
  (`scripts/measure_real_data.py`, `marketforge/validation/reference.py`).
  Crypto is anchored on Binance data; forex and stocks are marked provisional.
- New `long_memory` check: |r| autocorrelation at one hour.

### Removed / breaking
- The `gaps` anomaly. Closures produce gaps now.
- `--batch-size`, which is ignored. `--threads` becomes `--jobs`.
- `ReturnGenerator`, `OHLCVBuilder`, `GeneratorConfig`, `AssetConfig`,
  `generate_market_batched` and the `processing`, `generators`, `markets` and
  `utils` packages.
- The `marketforge --from ...` form without a subcommand still works for one
  release and prints a deprecation note.
