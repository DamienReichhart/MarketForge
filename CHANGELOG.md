# Changelog

## 5.0.0

A model that links markets and prices on real ticks, an API that speaks
one language, and data that drops straight into ML and backtesting tools.
Upgrading from 4.x? See
[Migrating to 5.0](https://damienreichhart.github.io/MarketForge/docs/migrating-to-5/).

### Output changes
- **Prices sit on each instrument's tick.** Open, high, low and close were
  mid prices with 8 decimals (0.0005% of AAPL closes fell on a cent). Every
  price is now a whole number of ticks: a cent for stocks (a hundredth of a
  cent below $1), and about five significant digits elsewhere, 0.00001 on
  EURUSD, 0.001 on USDJPY, 0.01 on XAUUSD, 0.1 on BTCUSD. `tick_size` sets
  it per instrument in an override file. Bid and ask take half the spread
  each way, outwards onto the grid. A forex cross equals the product of its
  anchors to within the rounding of the three prices (two ticks), not to
  the last bit.
- **Stock volume is whole shares**, as forex tick volume already was.
- **Markets move together.** Each market was simulated alone: BTC and AAPL
  had a daily correlation of 0.02, a stock crash never touched crypto, and
  the S&P CFD did not follow S&P stocks. A world-wide shock now drives part
  of every market's main move, a closed market receives in its gap what
  the world did meanwhile, and a world-wide **macro state** (calm, or
  stressed about a month in nine) makes high volatility and crashes likelier
  in every market at once and drifts them down together
  ([ADR 0016](docs/adr/0016-markets-share-a-macro-state-and-a-global-shock.md)).
  BTC-AAPL is now 0.13 daily, 0.28 weekly and 0.39 monthly; crypto is
  stressed 39% of the time stocks are, against 25% otherwise. Each market's
  own correlations are unchanged. `GeneratedData.macro()` labels every day.
- **Index CFDs follow the stock market's bull and bear spells.** SPXUSD
  shared the stocks' shocks but not their regime trends, so it correlated
  about 0.1 with AAPL week to week. The forex market now runs the stock
  market's own regime chain (regime draws have a random stream of their
  own in every market) and moves each index CFD with the stock market's
  trend during NYSE hours: SPXUSD correlates 0.66 weekly and 0.77 monthly
  with a basket of large caps.
- **Stocks report earnings.** Gaps were scaled diffusion: AAPL's largest
  overnight move in two years was 3.6%, and NVDA's big gaps fell at random.
  Every stock now reports four times a year, after the close of a day of its
  own in the fourth to sixth week of each quarter, whatever the seed. The
  next open jumps by about 2.5 days of the stock's volatility, heavy-tailed
  (NVDA up to ~20%), and volatility, volume and the spread stay raised for a
  few days. Daily kurtosis is 9-14 instead of 4-5. `earnings_move` sets the
  jump per stock (0 for none), and `GeneratedData.earnings()` lists the
  events. Dividends and splits are not modelled.
- **Pegged currencies hold their pegs.** USDHKD wandered from 7.45 to 8.22
  in ten years against the real 7.75-7.85 band, and EURDKK by 10% against
  ERM II's 2.25%. Both now stay in their bands with a pull towards the
  centre, and USDCNH is managed: a weak pull within 8% of its start price.
- **Forex is thin at Christmas and New Year.** It traded those days as
  any other; volatility and tick volume now fall to about a third of normal
  on the 25th and the 1st, and spreads widen.
- **Quotes jitter, and minute correlations are lower than daily ones.**
  Minute returns had no autocorrelation and AAPL-MSFT correlated 0.80 at m1
  as at D1, unlike real markets (the Epps effect). The quoted mid now
  jitters around the efficient price by a quarter of the minute's
  volatility (0.15 for crypto): lag-1 autocorrelation of AAPL's m1 returns
  is -0.04, and AAPL-MSFT is 0.73 at m1 against 0.81 daily. Each open is
  still the previous close, and forex crosses still derive from anchors.
- **Stocks have opening and closing auctions.** The last minute held 0.6%
  of a day's volume; the closing cross now prints about 5-9%, and the open
  about 3%.
- **Volatility has slow cycles.** Volatility clustered over minutes (GARCH)
  and days (regimes) but not over months, so a decade had no calm or
  turbulent years. Each series' log volatility now also wanders by day,
  with a half-life of 60 days and a mean square of 1, so the catalog's
  volatility is kept.
- **Stocks' long-run drift is at most 8% a year.** NVDA and LLY had 15%:
  history is no guide to the next decade. A 50%-volatile stock still ends
  ten years anywhere from a tenth to fifty times its start: that is its
  volatility, not its drift.
- **Regimes last a typical length.** Spell lengths were geometric (their
  spread equalled their mean), so an HMM was exactly the right model of the
  data and detectors scored better than they can on real markets. A spell
  now lasts its mean times a Gamma(2) draw, and regimes still never react to
  prices ([ADR 0017](docs/adr/0017-regimes-are-semi-markov-spells-and-never-react-to-price.md)).

### Validation
- **Five more statistics.** Minute-return autocorrelation, hourly kurtosis
  (aggregational Gaussianity) and the volume-volatility link, anchored on
  the same Binance minute data as the other crypto bands (provisional for
  forex and stocks); the gaps' share of the variance where a market closes;
  and, for data with regime labels, the spread of spell lengths.
- **A dataset's unusable files are skipped**, not fatal, and samples under
  1,950 m1 candles are refused instead of failing on noise.

### Breaking changes
- **One vocabulary for Python and the command line.** `fmt=` is `format=`;
  `include_regime=`, `include_spread=` and `include_bid_ask=` are
  `with_regime=`, `with_spread=` and `with_bid_ask=`; `--market` is
  `--markets` on `generate` and `list-instruments`; `--config` is
  `--overrides`; `validate --input PATH` is `validate PATH`. The old
  spellings fail with a message naming the new one for the whole 5.x series.
- **Every entry point generates the eight standard timeframes by default**,
  m1, m5, m15, m30, H1, H4, D1 and W1: `generate()` gave m1 only.
  `timeframes="all"` gives all 17.
- **`GeneratedData` is a read-only object, not a `dict`**: iterate it or use
  `.symbols`, `.frame()` and `.instrument()`. Symbols are sorted.
- **Ranges that can produce nothing are errors**: every requested market
  closed throughout (AAPL on a Saturday), or no complete candle of any
  requested timeframe. Nothing is written.
- **Times too large to be Unix seconds are refused** (Unix milliseconds
  became the year 55969), with the unit they look like.
- **`validate` needs at least 1,950 m1 candles**, a week of stock sessions:
  a 30-minute file failed on kurtosis alone.
- **Feather files are uncompressed**, so a memory-mapped read is zero-copy
  as documented; they are about the size of CSV. Use Parquet for small files.
- **The manifest spells its flags `with_regime`, `with_spread` and
  `with_bid_ask`**, and records the layout and every file's checksum.

### GeneratedData, a complete object
- **Getters and metadata**: `seed`, `start`, `end`, `version`,
  `model_revision`, `symbols`, `markets`, `timeframes`, `columns`,
  `market_of()`, `instrument()`, `frame()`, and `data["BTCUSD", "H1"]`.
  Symbols and timeframes ignore letter case, and an unknown one suggests
  the closest match.
- **Labels**: `regime(market, timeframe)`, `spells(market)` (one row per
  regime spell), `macro()` (calm or stressed, per day) and `earnings()`.
- **Narrowing**: `select()`, `between()` and `copy()`; `summary()`.
- **`save()`** writes the data as a dataset with a manifest, the files
  `generate_to_disk()` writes, so it extends and verifies: `read()` then
  `save(format="parquet")` converts a dataset.
- **A repr that fits on a screen**, instead of every DataFrame.

### Machine learning
- **`windows()`** cuts each instrument's candles into float32 windows for a
  sequence model, with features from the columns or computed (`return`,
  `log_volume`, `range`) and a target at or after each window's end.
- **`to_numpy(dtype=)`**, and a time axis built from integers: it was as
  slow as the simulation (5.6 s for a year of ten instruments).
- **`to_arrow()` and `to_polars()`** (`pip install 'marketforge[polars]'`).
- **`mf.concat()`** stacks `generate_many()` results into one frame indexed
  by seed, symbol and time.
- **`generate_many()` stays in one process** when the whole run is
  estimated under ten seconds: a process pool made small runs 40x slower.

### Datasets
- **The long layout** (`--layout long`, Parquet and Feather): one file per
  market and timeframe with `symbol` and `market` columns, so one glob reads
  a whole timeframe.
- **Every file says what it holds**: version, model revision, seed, market,
  timeframe and symbol in Parquet and Feather metadata.
- **Checksums**: the manifest records each file's rows, size and SHA-256,
  and `verify --checksums` checks them in seconds without regenerating.
- **`verify` compares Parquet and Feather by value**: an extended file keeps
  its row groups, so every extended Parquet dataset used to fail it. It
  regenerates beside the dataset, not in the system temp directory.
- **`read(start=, end=)`** filters while reading.
- **`mf.info()` and `mf.verify()`** do from Python what the commands do.

### Python API and command line
- **`extend(days=)`**, as on the command line; `generate_to_disk()` runs one
  market per core by default, as the command line does; `estimate()` takes
  every argument `generate_to_disk()` does.
- **`list-instruments --search TEXT`**, a volume column, and `--markets` as a
  list. Formats, layouts and markets take any letter case.
- **Warnings are one line on the command line**, without Python's file and
  line, and point at your code from Python. The progress bar draws only on
  a terminal, so CI logs stay clean.
- **Exported types**: `DiskReport`, `DatasetInfo`, `VerifyReport`,
  `InstrumentData`, `Windows`, `ValidationReport`, `MetricResult` and
  `OverrideError`, which the documentation already named.

### Fixes
- **An interrupted `extend` no longer deletes your files.** Recovering it
  removed or renamed every `*.tmp` file anywhere under the dataset; it now
  touches only the candle files it wrote.
- **`calibrate` writes override files that `generate` accepts**: a
  correlation of 1.0, a forex symbol that is not six characters, or a file
  not named `SYMBOL_m1` used to fail only at generation.
- **The same instrument in two letter cases** (`eurusd,EURUSD`) is
  generated once, instead of passing `--dry-run` and failing the run.
- **`resample()` refuses candles it cannot aggregate exactly**: not m1, out
  of order, or in the wrong market's closed minutes; it drops the candles
  around missing minutes, with a warning, and keeps bid and ask.
- **`--overwrite` removes the market folders** the old dataset leaves empty.

### Documentation and tooling
- [Migrating to 5.0](https://damienreichhart.github.io/MarketForge/docs/migrating-to-5/),
  and tested recipes for backtrader, backtesting.py, vectorbt, Nautilus
  Trader and freqtrade on the
  [Backtesting](https://damienreichhart.github.io/MarketForge/docs/use-cases/backtesting/)
  page.
- The README's Python example guards `generate_many()` with
  `if __name__ == "__main__":`, as scripts that start processes must, and
  states the headline command's disk size.
- `nox` runs CI's checks locally, `pre-commit` runs ruff before each
  commit, and the `examples/` scripts run in CI.

## 4.0.0

The most realistic MarketForge yet, and the easiest to build on:
- **A more realistic model.** Regimes that trend, correlations that hold and
  intensify in crashes, wicks on big candles, and forex sessions on their own
  clocks.
- **Easier to build on.** An ML-first Python API (`generate_many`, `read`,
  `to_numpy`, Feather, `resample`), bid and ask quotes, calibration to your
  own data, and datasets you can extend, inspect and verify.
- **A new licence.** MarketForge is now Apache-2.0.

**Realism now comes before seed stability**: seeds produce different candles
from 3.1.1 (see Output changes), and any later release may change them again
when that makes the data more realistic. Upgrading from 3.x? See
[Migrating to 4.0](https://damienreichhart.github.io/MarketForge/docs/migrating-to-4/).

### Output changes
- **Your override correlations hold.** Correlations set in an override file
  that contradicted the market were repaired by clipping eigenvalues, which
  moved your own values (BTC-ETH set to -0.5 came back +0.04). Your values
  are now kept exactly while the rest of the market moves to the nearest
  valid matrix. If your values contradict each other, they move as little as
  possible, and the warning says how far.
- **Forex sessions keep their own clocks.** Forex seasonality was a step
  function at fixed UTC hours, so the London open stayed at 07:00 UTC all
  year. Tokyo, London and New York sessions now ramp in and out on their own
  clocks, with bursts at the London open, at 08:30 New York (US data) and at
  the 16:00 London fix, and thinner Friday afternoons and Sunday opens.
- **Crypto bursts at funding times.** Volatility now rises briefly at the
  00:00, 08:00 and 16:00 UTC funding settlements of perpetual futures.
- **Big candles have wicks.** Highs and lows came from the expected
  volatility only, so the biggest minutes were bare bodies (range 1.05 times
  the body), unlike real ones, which retrace. A minute's wicks now grow with
  its move: range is about 1.3 to 1.4 times the body on the largest minutes.
- **Correlations intensify under stress.** One correlation matrix drove every
  regime, so BTC and a gaming coin were as correlated in a crash as in a
  range. A common shock is now added in high-volatility and crash regimes:
  from range to crash, BTC-SAND goes from 0.55 to 0.82, AAPL-XOM from 0.38 to
  0.65 and EURUSD-USDCHF from -0.66 to -0.86
  ([ADR 0014](docs/adr/0014-correlations-intensify-under-stress.md)).
- **A stock crash is the most volatile regime.** Its volatility multiplier was
  1.5 against 1.8 for high volatility (crypto and forex use 3.0); it is now
  2.6.
- **Regimes trend.** A regime used to scale the catalog drift, a few percent
  a year (zero for every forex pair), so `trend_up` had no detectable trend
  and averaged a negative return over 90 days of BTC. Each regime now has a
  trend strength per spell, along the market's main factor: coins and stocks
  together, and the dollar in forex (`trend_up` is the dollar falling). A
  `trend_up` or `trend_down` spell ends in its direction about 70-90% of the
  time, and a crash falls by about 1.5 of its own standard deviations. The
  catalog's annual drift is still the long-run drift
  ([ADR 0013](docs/adr/0013-regimes-trend-along-the-market-factor.md)).
- **Correlations are the ones the catalog states.** The stated correlations
  were made valid by clipping eigenvalues, which moved them as much as the
  filler values: EURUSD-USDCHF came out -0.45 instead of -0.92, AUDUSD-NZDUSD
  0.41 instead of 0.88, BTC-ETH 0.73 instead of 0.88. Each market's matrix is
  now fitted to the stated pairs ([ADR 0012](docs/adr/0012-fit-correlations-to-what-the-catalog-states.md)).
  Crypto and stocks keep them to within 0.05, and forex is fitted through its
  anchors. Forex crosses, whose volatility came out about 1.5 times the
  catalog's (AUDNZD 0.10-0.12 for a stated 0.07), now land at 0.7 to 1.2
  times it.
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
- **Third-party licences ship with everything that contains third-party
  code.** Each GitHub release has a `third-party-licenses.txt` with the licence
  and NOTICE texts of every runtime dependency, and the website serves those
  of its own code, fonts and playground runtime (Pyodide, CPython, Emscripten,
  and the Python wheels it serves) at `/third-party-licenses.txt`, with the
  texts upstream packages leave out, such as pyarrow's NOTICE, and of the
  libraries compiled into the playground's WebAssembly (libffi, zlib, bzip2,
  xz, Zstandard, SQLite, libc++, musl) and into the site's search (Rust crates,
  Svelte). Both are written by
  the build that produces what they describe, and CI blocks a release if a
  dependency's licence is not allowed or its licence text is missing. The
  wheel and sdist still contain only MarketForge's own code.

### Breaking changes
- **"Asset" is now "instrument" everywhere**, as the glossary has said since
  3.0. `--assets`/`-a` is `--instruments`/`-i`, `list-assets` is
  `list-instruments`, and `generate()` and `generate_to_disk()` take
  `instruments=` instead of `assets=`. The old names are removed.
- **The forms deprecated in 3.0 are removed.** `marketforge --from ...`
  without a subcommand is no longer routed to `generate`, and the hidden
  `--threads`/`--thread-count` and `--batch-size` options are gone. Use
  `marketforge generate --from ...` and `--jobs`.
- **`generate` refuses a directory that already holds a dataset.** Generating
  again into one used to leave the old dataset's files beside the new ones,
  so a glob over the directory mixed two datasets and the manifest no longer
  described it. Pass `--overwrite` (`overwrite=True`) to replace it: the old
  manifest and candle files are deleted first, and other files are left alone.
- **Files write the regime as its name**, as frames in memory always did:
  `trend_up`, `trend_down`, `range`, `high_volatility` or `crash` instead of
  the codes 0 to 4. Parquet stores it as a categorical, so `pd.read_parquet`
  returns exactly the in-memory column; `.cat.codes` gives the codes. Code
  written as `df.regime == 2` against files becomes `df.regime == "range"`.
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

### Machine-learning ergonomics
- **More timeframes**: m2, m3, m10, m20, H2, H3, H6, H8 and H12, on each
  market's anchors like the others.
- **`mf.resample(frame, "H4", "forex")`** aggregates m1 candles (generated,
  read back or your own) exactly as MarketForge does: on the market's anchor
  clock and without partial candles.
- **Feather output** (`--format feather`): Arrow IPC files that load fastest
  and memory-map with no copy. They extend, read back and validate like the
  other formats.
- **Native time columns** (`--timestamps datetime`): Parquet and Feather files
  can store the timestamp as a UTC time type, which Spark, DuckDB and polars
  read as time, instead of Unix seconds.
- **`mf.generate_many(..., seeds=range(64), jobs=8)`** runs `generate()` once
  per seed in parallel processes and yields the results in seed order, so
  many-seed training sets and stress tests use every core without holding
  everything in memory.
- **`mf.read(dataset)`** loads a dataset, or some of its instruments and
  timeframes, back as the `GeneratedData` that `generate()` returns: UTC
  index, float columns, categorical regime. No more hand-written
  `read_csv` and timestamp conversion.
- **`GeneratedData.to_long()`** stacks every instrument into one frame
  indexed by `(symbol, time)`, and **`to_numpy()`** gives a `(time,
  instrument, column)` array with its axes, NaN where a market was closed.
- **`mf.estimate()`** says what a generation would produce (files, rows,
  disk size, the memory `generate()` would need, time) without running it,
  as `--dry-run` does, and `--dry-run` now estimates the time for the
  markets it simulates in parallel instead of one core.
- **`days=`** is accepted instead of `end=` in Python, as `--days` is on the
  command line.

### Installation
- **Python 3.15 is supported** and tested on Linux (x86-64 and arm64),
  macOS and Windows, with the newest numpy, pandas, Numba and pyarrow.
- **scipy is no longer a dependency** (about 100 MB less to install, and one
  fewer version to reconcile with an ML stack). Validation computes the
  excess kurtosis with NumPy, to the same value.
- **MarketForge runs in Pyodide** (Python in WebAssembly). Numba is not
  installed there, and the kernels run as plain Python to the same bits, only
  slower. Everywhere else Numba is still required, and a missing Numba is
  still an import error, not a silent fallback.

### New commands
- **`marketforge info DATASET`** summarises a dataset from its manifest
  (version, model revision, seed, range, instruments, files and size) and
  says whether it can be extended, and if not with which version.
- **`marketforge calibrate FILES --market M`** (`mf.calibrate`) fits
  instruments to your own m1 candle files (start price, volatility with gaps,
  volume, hourly correlations) and writes an override file to generate data
  like yours.
- **`marketforge verify DATASET`** regenerates a dataset from its manifest
  and compares every file byte for byte: proof that a dataset is untouched
  and reproducible here.
- **`marketforge validate --input DATASET`** validates every `m1` file of a
  dataset, one line per file, with an overall exit code.
- **`--json`** on `info`, `validate` and `list-instruments` prints
  machine-readable output for scripts and CI.
- **`-q`/`--quiet`** on `generate` and `extend` prints nothing but warnings
  and errors.

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
- **`--with-bid-ask` / `include_bid_ask=True`** adds `bid` and `ask` columns:
  the quotes around the close, for backtesters that fill at the quote.
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

### Fixes
- **`--dry-run` counted daily and weekly candles wrongly.** It divided a
  market's open minutes by 1,440 for both, so a stock day (390 open minutes)
  counted as a quarter of a candle and W1 as many candles as D1. Both now
  follow each market's sessions.
- **A wrong override value says where it is.** A string where a number was
  expected failed with numpy's "could not convert string to float: 'x'", and
  a `correlations` value that was not a table crashed. Values are checked
  when the overrides are read, and the message names the file, the
  instrument and the key.
- **Requests that were partly ignored now warn.** Overriding a forex cross's
  start price, volatility, drift or correlations had no effect (a cross is
  derived from its anchors), and `-i BTCUSD,AAPL -m crypto` dropped AAPL
  without a word.
- **A range that starts before 1970 is refused with a clear message**
  instead of numpy's "expected non-negative integer".

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
- **Try MarketForge in your browser.** The site's
  [Playground](https://damienreichhart.github.io/MarketForge/playground/)
  runs the released package in the page itself: pick instruments, a range and
  a seed, see the candles with their regimes, download them as CSV or Parquet,
  and copy the equivalent command. It is a preview with limits the installed
  package does not have (it is 10 to 100 times slower, capped in size, and not
  bit-identical to an installed MarketForge), which the page states up front.
  Nothing leaves the browser, and the runtime is served by the site itself.
- **Runnable examples** in [`examples/`](examples/), each running in
  seconds: a regime classifier trained on seed-disjoint splits, training
  windows (with a PyTorch `DataLoader` when torch is installed), a backtest
  that fills at the bid and ask on NYSE sessions, and Monte Carlo drawdowns
  with `generate_many()`. The stress-testing guide read the bad drawdown tail
  from the 95th and 99th percentiles; drawdowns are negative, so it is now
  read from the low ones.
- **Contributing is documented on GitHub too**: a `CONTRIBUTING.md`, issue
  forms (including a realism report for statistics measured on real data)
  and a `CITATION.cff` for citing MarketForge in research.

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
