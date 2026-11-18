<h1 align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/DamienReichhart/MarketForge/main/docs/brand/assets/lockup-dark.svg">
    <img alt="MarketForge" src="https://raw.githubusercontent.com/DamienReichhart/MarketForge/main/docs/brand/assets/lockup-light.svg" height="64">
  </picture>
</h1>

[![PyPI](https://img.shields.io/pypi/v/marketforge)](https://pypi.org/project/marketforge/)
[![Python](https://img.shields.io/pypi/pyversions/marketforge)](https://pypi.org/project/marketforge/)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue)](https://github.com/DamienReichhart/MarketForge/blob/main/LICENSE)
[![Docs](https://img.shields.io/badge/docs-damienreichhart.github.io%2FMarketForge-informational)](https://damienreichhart.github.io/MarketForge/)

**Synthetic market data for training AI trading models and testing
backtesters.** MarketForge simulates 208 crypto, forex and US stock
instruments minute by minute, on each market's real trading calendar, and
writes candles from `m1` to `W1` as CSV, Parquet or pandas DataFrames. Every
candle can carry the **hidden market regime** that produced it and a realistic
**bid-ask spread**, and every dataset is **reproducible** from its seed and
version.

```bash
pip install marketforge
marketforge generate -o ./data --from 2024-01-01 --days 90 --market crypto --with-regime --with-spread --seed 42
```

**[Documentation](https://damienreichhart.github.io/MarketForge/docs/)** ·
[Quick start](https://damienreichhart.github.io/MarketForge/docs/quick-start/) ·
[Try it in your browser](https://damienreichhart.github.io/MarketForge/playground/) ·
[Changelog](https://damienreichhart.github.io/MarketForge/changelog/) ·
[PyPI](https://pypi.org/project/marketforge/)

## What it is for

Real market history is finite, expensive, unlabelled, and leaks into every
model you fit on it. MarketForge covers what real data cannot:

- **Training AI trading models.** Unlimited, realistic sequences for
  pre-training, data augmentation and architecture search. The regime label is
  ground truth for supervised learning and for scoring regime detectors, and
  disjoint seeds give train, validation and test sets that share no path.
  [ML guide](https://damienreichhart.github.io/MarketForge/docs/use-cases/machine-learning/)
- **Testing backtesters and trading systems.** NYSE sessions, holidays, early
  closes and DST; the forex week; 24/7 crypto; overnight and weekend gaps;
  mid prices plus a spread; multi-asset panels that do not trade at the same
  times. The bugs show up in testing, not with real money.
  [Backtesting guide](https://damienreichhart.github.io/MarketForge/docs/use-cases/backtesting/)
- **Stress testing.** Run a strategy through hundreds of alternative
  histories, crash and high-volatility regimes included, and look at the
  distribution of drawdowns instead of one equity curve. Optional spikes and
  flash crashes push it further.
  [Stress-testing guide](https://damienreichhart.github.io/MarketForge/docs/use-cases/stress-testing/)

### What it is not

**A source of alpha.** A model trained only on MarketForge learns MarketForge.
The data has the statistics of real markets but no edge that carries over to
them, and instrument symbols are labels for parameter sets, not the history of
those instruments. A strategy that makes money on synthetic data has proved
that it runs, not that it works: use MarketForge to build, debug, pre-train
and stress-test, and real data to decide whether anything earns money. See
[What it is not](https://damienreichhart.github.io/MarketForge/docs/limits/).

## Why MarketForge

- **Ground-truth regimes.** With `--with-regime`, each candle carries the
  market's hidden state: trend up, trend down, range, high volatility or
  crash. Regimes trend along the market's main factor, so the labels show in
  the data, and real data never tells you which one you were in.
- **Real trading calendars.** Stocks trade the NYSE session (09:30-16:00 New
  York, DST-aware) and skip NYSE holidays and early closes. Forex trades from
  Sunday 17:00 to Friday 17:00 New York time. Crypto never closes. No candles
  are printed while a market is closed, and gaps come from the price moving
  during the closure, as they do in reality.
- **One market, one story.** Every instrument of a market is simulated
  jointly: the correlations the catalog states, Student-t shocks with tail
  dependence, correlations that intensify in crashes (diversification fails
  when it matters), and a shared regime.
- **Arbitrage-free forex.** One anchor pair per currency is simulated and
  every cross is derived from them, so `EURJPY == EURUSD * USDJPY` at every
  minute.
- **Validated, not eyeballed.** Heavy tails, volatility clustering, long
  memory, the leverage effect, intrabar range and the spread are checked for
  every instrument, across seeds, against bands measured on real crypto minute
  data (forex and stock bands are still provisional). The validator ships with
  the package, and `marketforge calibrate` fits instruments to your own data.
- **Built for ML pipelines.** `generate_many()` runs seeds in parallel
  processes for leak-free splits, `to_numpy()` gives `(time, instrument,
  feature)` tensors, `read()` loads datasets back with the right types, and
  Feather files load with no copy.
- **Reproducible.** A seed fixes every random shock by market and minute. The
  same seed and version give the same EURUSD, bit for bit on a given
  platform, whether you generate it alone or with 207 other instruments. CI
  enforces it on every commit.
- **Datasets you can extend.** Every dataset carries a manifest of how it was
  made. `marketforge extend` continues it, byte-identical to generating the
  whole range at once.
- **Fast, bounded memory.** Compiled (Numba) kernels stream the simulation day
  by day. A year of EURUSD across all 8 timeframes takes about 2 s; a month of
  all 208 instruments about 6 s. Memory does not grow with the range.

## Quick start

```bash
# One year of EURUSD, every timeframe, reproducible
marketforge generate -o ./eurusd --from 2024-01-01 --to 2025-01-01 --instruments EURUSD --seed 42

# A whole market as Parquet, with regime labels and the bid-ask spread
marketforge generate -o ./crypto --from 2024-01-01 --days 180 --market crypto \
    --format parquet --with-regime --with-spread --seed 7

# What would a run produce (files, rows, disk size, time)? Nothing is written.
marketforge generate --from 2015-01-01 --to 2025-01-01 --market all --dry-run

# Continue a dataset: 30 more days, same seed, instruments, timeframes and format
marketforge extend ./eurusd --days 30

# Check an m1 file against real-market stylized facts (exit code 1 on failure)
marketforge validate --input ./eurusd/forex/EURUSD_m1.csv
```

Every option is in the
[command-line reference](https://damienreichhart.github.io/MarketForge/docs/guides/cli/).

### Python

```python check=static
import marketforge as mf

# Disjoint seeds: train, validation and test never share a path.
# One generation per seed, in parallel processes, yielded in seed order.
for data in mf.generate_many(
    "BTCUSD,ETHUSD,SOLUSD", seeds=range(64),
    start="2024-01-01", end="2024-04-01", timeframes=["m5"],
    include_regime=True, include_spread=True,
):
    x, times, symbols = data.to_numpy("m5")          # (time, instrument, OHLCV), NaN when closed
    labels = data["BTCUSD"]["m5"]["regime"]          # ground-truth regime per candle
    ...

# Years of data, streamed to disk; continued later
mf.generate_to_disk("./data", markets="stocks", start="2015-01-01", end="2025-01-01",
                    seed=1, fmt="parquet", jobs=3)
mf.extend("./data", "2025-02-01")

# Check minute candles against the bands measured on real markets
m1 = mf.generate("BTCUSD", start="2024-01-01", end="2024-01-15", seed=1)["BTCUSD"]["m1"]
report = mf.validate(m1, "crypto")
print(report.summary())
```

See the [Python API](https://damienreichhart.github.io/MarketForge/docs/guides/python-api/), and
[`examples/`](https://github.com/DamienReichhart/MarketForge/tree/main/examples) for runnable
scripts: a regime classifier, training windows for a neural network, a backtest that fills at
the quote, and Monte Carlo drawdowns.

## Output

```
data/
├── marketforge.json                       # the manifest: version, seed, range, settings
├── crypto/BTCUSD_m1.csv, BTCUSD_H1.csv, ...
├── forex/EURUSD_m1.csv, ...
└── stocks/AAPL_m1.csv, ...
```

```csv
timestamp,open,high,low,close,volume,spread,regime
1704067200,67500,67841.28465635,67497.68731519,67837.68959567,548.7391,0.13516156,range
```

Timestamps are the start of the candle in Unix seconds (UTC), or ISO 8601
with `--timestamps iso`. Prices are mid prices: `bid = price - spread / 2`.
The regime is one of `trend_up`, `trend_down`, `range`, `high_volatility` and
`crash`, in files as in memory (a categorical whose codes are 0 to 4 in that
order). `high >= max(open, close)` and
`low <= min(open, close)` always hold, and partial candles are never written.
See [Output format](https://damienreichhart.github.io/MarketForge/docs/guides/output/).

## Markets

| Market | Instruments | Hours | Calibration |
| --- | --- | --- | --- |
| crypto | 53 (BTCUSD, ETHUSD, SOLUSD, ...) | 24/7 | Validation bands and spreads measured on Binance minute data of seven coins |
| forex | 81: majors, crosses, exotics, metals, index and oil CFDs | Sunday 17:00 to Friday 17:00 New York | Provisional bands; spreads estimated |
| stocks | 74 US large caps (AAPL, MSFT, NVDA, JPM, ...) | NYSE session, holidays, early closes | Provisional bands; spreads estimated |

Change any instrument, or add your own, with a TOML
[override file](https://damienreichhart.github.io/MarketForge/docs/guides/custom-instruments/).
The [model](https://damienreichhart.github.io/MarketForge/docs/reference/model/),
the [spread](https://damienreichhart.github.io/MarketForge/docs/reference/spread/)
and the [known simplifications](https://damienreichhart.github.io/MarketForge/docs/reference/markets/#known-simplifications)
are documented in full.

## Reproducibility

For a given MarketForge **version**, `(seed, market, minute)` fully determines
every random shock. Output is identical whichever instruments, timeframes,
format or `--jobs` you choose, whether the spread or regime is requested, how
far `--to` extends, and whether the range was generated at once or extended in
steps. **Realism comes before seed stability:** any release may change what a
seed produces when that makes the data more realistic, and says so under
*Output changes* in the changelog. Pin the version to keep a dataset
identical; the manifest records the version and model revision that made it.
See
[Reproducibility](https://damienreichhart.github.io/MarketForge/docs/reference/reproducibility/).

## Contributing

```bash
git clone https://github.com/DamienReichhart/MarketForge && cd MarketForge
pip install -e . --group dev
ruff check . && ruff format --check . && lint-imports
mypy marketforge
pytest
```

These are the checks CI runs; see [`docs/ci-cd.md`](https://github.com/DamienReichhart/MarketForge/blob/main/docs/ci-cd.md) for the
pipeline and the release process, [`docs/adr/`](https://github.com/DamienReichhart/MarketForge/tree/main/docs/adr) for design
decisions, and [`GLOSSARY.md`](https://github.com/DamienReichhart/MarketForge/blob/main/GLOSSARY.md) for the vocabulary. The website
lives in [`website/`](https://github.com/DamienReichhart/MarketForge/tree/main/website). Report security issues privately: see
[`SECURITY.md`](https://github.com/DamienReichhart/MarketForge/blob/main/SECURITY.md).

```
marketforge/
  domain/        Shared vocabulary: markets, regimes, anomalies, timeframes, candles. Imports nothing else.
  calendars/     When each market is open and where its bars start (NYSE rules, DST).
  config/        Model parameters, per-market defaults, TOML overrides.
    catalog/     Built-in instruments and correlations, one package per market.
  simulation/    The day-by-day market simulator and its parts (kernels, factors, regimes, anomalies).
  aggregation/   m1 candles to higher timeframes, streaming.
  output/        CSV and Parquet writers.
  validation/    Stylized-fact metrics and the bands generated data must meet.
  api/           generate() and generate_to_disk(): parsing, planning, execution.
  cli/           The marketforge command, one module per subcommand.
tests/           Mirrors the package, plus tooling/ for the release scripts.
website/         The documentation site (Astro, Starlight), deployed to GitHub Pages.
```

Each package may import from the ones listed above it, never from the ones
below; `aggregation`, `output` and `validation` do not import each other. CI
enforces this with `lint-imports`. The supported Python API is what
`import marketforge` exposes; module paths below it can change between
releases.

## License

Apache-2.0. See [LICENSE](https://github.com/DamienReichhart/MarketForge/blob/main/LICENSE).

All data MarketForge produces is synthetic. It is not the price history of any
real instrument, and nothing in this project is financial advice.
