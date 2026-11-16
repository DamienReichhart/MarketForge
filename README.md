# MarketForge

Realistic synthetic OHLCV market data for backtesting, strategy development and
ML research. MarketForge simulates 208 instruments across crypto, forex and US
stocks minute by minute, on each market's real trading calendar, and publishes
candles from `m1` to `W1` as CSV, Parquet or pandas DataFrames, with an optional
bid-ask spread.

```bash
pip install marketforge
marketforge generate -o ./data --from 2024-01-01 --to 2025-01-01 --instruments EURUSD,AAPL,BTCUSD --seed 42
```

## Why MarketForge

- **Real trading calendars.** Stocks trade the NYSE session (09:30-16:00 New
  York, DST-aware) and skip NYSE holidays and early closes. Forex trades from
  Sunday 17:00 to Friday 17:00 New York time. Crypto never closes. No candles
  are printed while a market is closed. Overnight and weekend gaps come from
  the price moving during the closure, as they do in reality.
- **Arbitrage-free forex.** Only one anchor pair per currency is simulated, and
  every cross is derived from them, so `EURJPY == EURUSD * USDJPY` at every
  minute.
- **One market, one story.** Every instrument of a market is simulated jointly:
  a full correlation matrix, Student-t shocks with tail dependence (sell-offs
  hit everything at once), and a shared market regime (trend, range, high
  volatility, crash).
- **Stylized facts, validated.** Heavy tails, volatility clustering, the
  leverage effect and realistic intrabar ranges are checked by a bundled
  validation harness. Every instrument is checked, across seeds.
- **Bit-for-bit reproducible.** A seed fixes every random shock by market and
  minute. The same seed gives the same EURUSD whether you generate it alone or
  with 200 other instruments. Extending `--to` never changes earlier candles.
- **Datasets you can extend.** Every dataset carries a manifest: the version,
  seed and settings that produced it. `marketforge extend` continues it later,
  and the result is byte-identical to generating the whole range at once.
- **Bid-ask spread.** An optional `spread` column around the mid price widens
  in turbulent markets, in quiet hours and when a market reopens.
- **Fast and bounded in memory.** Simulation streams day by day through
  compiled (Numba) kernels, and only the instruments you ask for are computed
  past the random draws. A year of EURUSD across all 8 timeframes takes about
  2 s. A month of all 208 instruments, all timeframes, takes about 6 s.
  Memory does not grow with the date range.

## Installation

Python 3.12 or newer.

```bash
pip install marketforge
```

From source, with the test, type-checking and lint tools (a
[PEP 735](https://peps.python.org/pep-0735/) dependency group, pip 25.1 or
newer):

```bash
git clone https://github.com/DamienReichhart/MarketForge && cd MarketForge
pip install -e . --group dev
pytest
mypy marketforge
ruff check . && ruff format --check .
```

These are the same checks CI runs. See [`docs/ci-cd.md`](docs/ci-cd.md) for
the pipeline and the release process.

## Command line

```bash
# One year of EURUSD, every timeframe, reproducible
marketforge generate -o ./data --from 2024-01-01 --to 2025-01-01 --instruments EURUSD --seed 42

# A whole market as Parquet, with regime labels and the bid-ask spread
marketforge generate -o ./data --from 2024-01-01 --days 180 --market crypto \
    --format parquet --with-regime --with-spread --seed 7

# See what a run would produce (files, rows, disk size, time) without writing anything
marketforge generate --from 2015-01-01 --to 2025-01-01 --market all --dry-run

# Continue a dataset: 30 more days, same seed, instruments, timeframes and format
marketforge extend ./data --days 30

# List instruments (forex crosses are marked as derived)
marketforge list-instruments --market forex

# Check an m1 file against real-market stylized facts (exit code 1 on failure)
marketforge validate --input ./data/forex/EURUSD_m1.csv
```

### `generate` options

| Option | Meaning |
| --- | --- |
| `-o, --output-dir` | Where to write `{market}/{SYMBOL}_{timeframe}.{csv\|parquet}` and `marketforge.json`. |
| `--from` | Start of the range (inclusive). Accepts `2024-01-01`, `2024-01-01T09:30`, `2024-01-01T09:30-05:00` or Unix seconds. UTC unless an offset is given. |
| `--to` or `--days` | End of the range (exclusive), in the same formats as `--from`, or its length in days. Give exactly one. |
| `-i, --instruments` | Comma-separated instruments, in any letter case. Their markets are inferred. |
| `-m, --market` | `crypto`, `forex`, `stocks` or `all`. Defaults to all when `--instruments` is not given. With `--instruments`, it keeps only the instruments in these markets. |
| `-s, --seed` | Non-negative integer. When omitted, a random seed is used, printed and recorded in the manifest so the run can be reproduced. |
| `-t, --timeframes` | Any of `m1,m5,m15,m30,H1,H4,D1,W1`, in any letter case. Default: all. |
| `--format` | `csv` (default) or `parquet`. Parquet files are about half the size and load much faster. |
| `--timestamps` | `unix` (default) or `iso` (`2024-01-02T14:30:00Z`), for CSV files. |
| `--anomalies` | Optional unrealistic events: `spikes`, `flash_crash`. |
| `--with-spread` | Adds a `spread` column: the mean quoted bid-ask spread of the candle, in price units (see [Spread](#spread)). |
| `--with-regime` | Adds a `regime` column: 0 trend_up, 1 trend_down, 2 range, 3 high_volatility, 4 crash. |
| `--config` | TOML override file (see [Custom instruments](#custom-instruments)). |
| `-j, --jobs` | Markets simulated in parallel. Default: one per market, up to the CPU count. |
| `--dry-run` | Print the plan and estimates, then exit. |
| `--no-progress` | Hide the progress bar. |
| `--debug` (before the command) | Show full tracebacks. Errors are a single line otherwise. |

A file that receives no candle (the market was closed for the whole range, or
the range is shorter than the candle) is written empty, with a warning.

### Extending a dataset

```bash
marketforge extend ./data --to 2025-03-01     # or --days 30
```

`extend` takes everything but the new end from the dataset's manifest, so the
seed, instruments, timeframes, format and overrides cannot drift. Afterwards
the dataset holds exactly the candles one generation up to the new end would
have produced; CSV files are byte-identical to it. `--dry-run`, `--jobs` and
`--no-progress` work as for `generate`.

- CSV files are appended to in place. A Parquet file cannot be appended to, so
  each one that gets new candles is rewritten.
- An extension is all-or-nothing. If it fails or is interrupted, the dataset
  is left, or put back by the next `extend`, exactly as it was.
- Datasets go forward only, and only within a major version: a seed's candles
  can differ between major versions. Datasets written before 4.0 have no
  manifest and cannot be extended.

## Python API

```python
import marketforge as mf

data = mf.generate(
    ["EURUSD", "AAPL"],                # or "EURUSD,AAPL"
    start="2024-01-01", end="2024-02-01",
    seed=42, timeframes=["m1", "H1", "D1"],
    include_spread=True,
)
eurusd_h1 = data["EURUSD"]["H1"]       # DataFrame indexed by UTC time
closes = data.panel("close", "H1")     # one column per instrument
print(data.seed)                       # 42 (or the random seed that was chosen)

# Stream large ranges to disk instead of memory, and continue them later
report = mf.generate_to_disk("./data", markets="stocks",
                             start="2015-01-01", end="2025-01-01",
                             seed=1, fmt="parquet", jobs=3)
print(report.n_files, report.paths["stocks"]["AAPL"]["D1"], report.manifest)
mf.extend("./data", "2025-02-01")

mf.instruments("forex")                # the catalog as a DataFrame
report = mf.validate(data["EURUSD"]["m1"], "forex")
print(report.passed, report.summary())
```

| Function | What it does |
| --- | --- |
| `generate(...)` | Candles in memory: `{symbol: {timeframe: DataFrame}}`. Each DataFrame has a UTC `DatetimeIndex` named `time` and the columns `open, high, low, close, volume`, plus `spread` with `include_spread=True` and a categorical `regime` with `include_regime=True`. |
| `GeneratedData.panel(column, timeframe)` | One column of every instrument side by side. The index is the union of all candle times; a value is NaN where that instrument's market was closed, never forward-filled. |
| `generate_to_disk(output_dir, ...)` | A dataset on disk: candle files and the manifest. Memory does not grow with the range. |
| `extend(dataset, end)` | Continues a dataset, as `marketforge extend` does. |
| `instruments(markets=None, overrides=None)` | The catalog as a DataFrame indexed by symbol: market, start price, volatility, drift, base volume, and whether the instrument is a derived forex cross. |
| `validate(data, market=None)` | Checks m1 candles (a DataFrame or a CSV/Parquet path) against a market's validation bands. The market can be omitted for a file MarketForge wrote. |
| `parse_time(value)` | The Unix seconds of any time MarketForge accepts. |

Instruments, markets, timeframes and anomalies can be given as a list or as
one comma-separated string, in any letter case. `overrides` takes the path of
a TOML file or the same content as a dict: `{"BTCUSD": {"start_price": 42000}}`.

## Output

```
data/
├── marketforge.json
├── crypto/BTCUSD_m1.csv, BTCUSD_H1.csv, ...
├── forex/EURUSD_m1.csv, ...
└── stocks/AAPL_m1.csv, ...
```

```csv
timestamp,open,high,low,close,volume
1704205800,185,185.02079274,184.85083294,184.8539491,56235.3556
1704205860,184.8539491,185.03837413,184.84785539,185.03767407,127066.8316
```

- `timestamp`: start of the candle, in Unix seconds (UTC), or as
  `2024-01-02T14:30:00Z` with `--timestamps iso`. Parquet uses the same
  columns, with `timestamp` always stored as int64 Unix seconds.
- `spread` (with `--with-spread`) comes after `volume`, and `regime` (with
  `--with-regime`) last.
- Prices are mid prices. With a spread, bid = price - spread / 2 and
  ask = price + spread / 2.
- Prices are rounded to 8 decimals and volume to 4 (trailing zeros are not written).
- `high >= max(open, close)`, `low <= min(open, close)`, all prices and volumes
  positive.
- Within a session, each candle opens at the previous close. The first candle
  after a closure opens with a gap.
- `generate` rewrites every output file and the manifest from scratch, so
  re-running into the same directory never leaves candles from an earlier run
  behind. Only `extend` adds to existing files.
- `marketforge.json`, the manifest, records the MarketForge version, seed,
  range, instruments, timeframes, formats, anomalies and the resolved
  overrides (the values, not a path, so the dataset stands on its own), plus
  the checkpoint `extend` resumes from. Anyone you give the dataset to can
  read your custom instrument parameters there.
- Candles are buffered and written in chunks of up to 32,768 rows per file
  (one Parquet row group each), with at most ~2 million rows buffered per
  market.
- A Parquet file can only be finished, not appended to, so every Parquet output
  stays open until the run ends. When a run needs more open files than the
  process's soft limit allows (256 by default on macOS), MarketForge raises the
  soft limit up to the hard limit, and stops before generating anything if
  that is not enough.

### Candle alignment

| Market | Daily candle starts | Weekly candle starts | Intraday alignment |
| --- | --- | --- | --- |
| crypto | 00:00 UTC | Monday 00:00 UTC | UTC clock |
| forex | 17:00 New York (the "NY close") | Sunday 17:00 New York | New York close clock (H4: 17:00, 21:00, 01:00, ...) |
| stocks | 09:30 New York (the open) | Monday's open | the open (H1: 09:30, 10:30, ...) |

A candle is only written when the requested range covers every open minute of
its bucket. Partial first or last candles are dropped, never published
half-built.

## Markets

| Market | Instruments | Hours | Volume unit | Notes |
| --- | --- | --- | --- | --- |
| crypto | 53 (BTCUSD, ETHUSD, SOLUSD, ...) | 24/7 | base asset (BTC for BTCUSD) | Heaviest tails (Student-t, 6 degrees of freedom). Activity peaks at the US open; weekends are quieter. Calibrated on real Binance m1 data. |
| forex | 81: majors, crosses, exotics, metals (XAUUSD), index and oil CFDs | Sun 17:00 to Fri 17:00 NY | ticks per minute (integers) | 41 anchor pairs are simulated and 40 crosses derived. Weekend gaps. |
| stocks | 74 US large caps (AAPL, MSFT, NVDA, JPM, ...) | NYSE session, holidays, early closes | shares | Overnight and weekend gaps. U-shaped intraday volatility and volume. |

**Known simplifications.** The index and oil CFDs in the forex catalog
(GRXEUR, SPXUSD, WTIUSD, ...) trade on the forex calendar, nearly 24/5. Their
real sessions and daily maintenance breaks are not modelled. Forex is open on
Christmas and New Year's Day. NYSE one-off closures (9/11, Hurricane Sandy,
national days of mourning) are not modelled. Forex tick-volume levels, and
forex and stock spread levels, are estimates, not measurements.

`start_price` is the price at the start of the range, whatever date that is: a
range starting in 2015 starts at the same prices as one starting in 2024.

Annual volatility and drift in the catalog are what you get. Regime multipliers
are normalised so they change *when* volatility and drift happen, not how much.
Forex crosses take their volatility and start price from their anchor pairs.

## Custom instruments

Change catalog instruments or add your own with a TOML file. There is no need
to edit the package.

```toml
# my_instruments.toml
[instruments.BTCUSD]          # change an existing instrument
start_price = 42000
volatility = 0.60             # annualised

[instruments.MYCOIN]          # add a new one
market = "crypto"
start_price = 1.50
volatility = 0.90
drift = 0.0                   # annualised log drift
volume_base = 20000           # mean volume per minute (coins / ticks / shares)
volume_volatility = 0.5       # lognormal sigma of volume noise
spread_bps = 8                # typical bid-ask spread, in basis points of the price
correlations = { BTCUSD = 0.6, ETHUSD = 0.55 }
```

```bash
marketforge generate -o ./data --from 2024-01-01 --to 2024-03-01 --instruments MYCOIN,BTCUSD --config my_instruments.toml
```

Correlations you do not specify for a new instrument are implied from the ones
you do: a coin 0.6-correlated with BTC is also correlated with ETH. The
resulting matrix is always valid.

## Model

Per open minute *t* and simulated series *f*:

- **Shocks** *z*: correlated, unit-variance Student-t shocks via a normal
  variance mixture. The mixing variable is shared by the whole market, which
  creates tail dependence.
- **Volatility**: σ<sub>f</sub> · √h<sub>t</sub> · g<sub>t</sub> · s<sub>t</sub>.
  - σ<sub>f</sub> is the per-minute level implied by the annual volatility on
    that market's calendar.
  - h<sub>t</sub> is a GJR-GARCH(1,1) multiplier with unit mean, which gives
    clustering and the leverage effect.
  - g<sub>t</sub> is the regime multiplier, smoothed so regime changes ramp in.
    Regimes last hours to days: crypto trends average about 1.7 days and
    crashes about 13 hours.
  - s<sub>t</sub> is intraday seasonality.
- **Return** (open to close): μ<sub>f</sub> · d<sub>t</sub> + volatility · *z*,
  where d<sub>t</sub> is the regime drift multiplier.
- **Gaps**: after a closure of *C* minutes, the open jumps by a shock whose
  variance grows with *C*. Roughly 30% of a session's variance builds up
  overnight for stocks; a typical EURUSD weekend gap is about 10 pips.
- **High/low**: the exact maximum and minimum of a Brownian bridge from open to
  close, sampled from their closed-form distribution. The excursion uses a
  fraction of the bar's volatility (0.62 for crypto), because real minutes
  wander less inside the bar than a pure random walk.
- **Volume**: a log-AR(1) process. It rises with the size of the standardized
  move, with the volatility level and with intraday seasonality, and has its
  own persistent noise.

### Spread

With `--with-spread`, each candle carries the mean quoted bid-ask spread of
its minutes, in price units. Per minute, the spread is the instrument's
typical level multiplied by:

- the volatility level (GARCH and regime) raised to a power, so spreads widen
  in turbulent markets;
- the inverse of intraday seasonality raised to a power, so they widen in
  quiet hours;
- a reopening term: forex spreads are about five times wider when the week
  opens and stock spreads four times wider at the open, decaying within
  minutes;
- lognormal noise.

The typical level is the instrument's `spread_bps`. Built-in instruments have
none of their own; each market derives it:

| Market | Typical level | Reaction to volatility | Basis |
| --- | --- | --- | --- |
| crypto | Set by the price: 0.02 basis points on BTCUSD, about 1 on coins under a dollar. A fixed price increment, like an exchange tick: it does not shrink when the price falls. | Weak (power 0.1): the most turbulent minutes are 3 to 11% wider. | **Fitted to measured quotes**: Binance USDT-futures best bid/ask, February 2024. |
| forex | Set by volatility: about half a pip on EURUSD, 13 basis points on USDTRY. | Power 0.5. | Estimate. |
| stocks | Set by volatility, never below one cent: a liquid large cap quotes exactly one cent wide most of the day. | Power 0.5. | Estimate. |

**Forex and stock levels are estimates, not measurements**; set `spread_bps`
in an override file to match your broker. Asking for the spread changes no
other column. See [ADR 0008](docs/adr/0008-spread-is-an-opt-in-column-around-mid-prices.md).

Design decisions and their reasons are recorded in [`docs/adr/`](docs/adr), and
the vocabulary in [`GLOSSARY.md`](GLOSSARY.md).

## Validation

```bash
marketforge validate --input ./data/crypto/BTCUSD_m1.csv --market crypto
python scripts/benchmark_realism.py --seeds 123,7 --days 14   # every instrument
```

The validator takes m1 candles only, and refuses other timeframes: the bands
describe minute returns. It measures open-to-close minute returns (overnight
and weekend gaps excluded) against per-market bands:

- **Heavy tails**: excess kurtosis in a realistic range.
- **Volatility clustering**: the autocorrelation of |returns| over the first
  20 minutes is significant.
- **Long memory**: |returns| are still autocorrelated an hour later.
- **Leverage effect**: returns are not positively correlated with next-period
  volatility. The band is looser for forex, where crosses have no natural
  "down".
- **Range efficiency**: mean(high − low) / mean(|close − open|). A pure random
  walk gives 2.0.
- **Spread** (when the file has a `spread` column): the median spread, in
  basis points, is in a realistic range, and the most turbulent minutes are
  about as much wider than the median as in real quotes.

Heavy tails, long memory and the leverage effect allow two standard errors of
sampling noise, estimated from the sample itself. The textbook formulas
assume independent normal data and are 2.5 times too small on minute returns.
See [ADR 0010](docs/adr/0010-noise-allowances-use-the-samples-own-standard-errors.md).

The bands are anchored to the same statistics measured on real m1 data. See
[`marketforge/validation/reference.py`](marketforge/validation/reference.py)
and [ADR 0006](docs/adr/0006-validation-bands-are-the-realism-contract.md).

- **Crypto** is anchored on Binance 1-minute klines of seven coins (BTC, ETH,
  SOL, XRP, DOGE, TRX, LINK; February 2024), and its spread bands on Binance
  USDT-futures best bid/ask for the same coins. Generated crypto data falls
  inside the measured real range for |r| autocorrelation from 15 minutes to
  1 day, clustering, leverage, range efficiency, volume dynamics and spread.
- **Forex and stocks** use *provisional* bands, for spread too, until real
  reference data is measured for them, and their reports say so. No free
  source of forex or stock quotes was reachable when this was calibrated.

To anchor them, or to compare against your own data:

```bash
python scripts/measure_real_data.py --name EURUSD ./my_eurusd_m1/*.csv   # timestamp,open,high,low,close[,volume,spread]
```

With two-week windows and three seeds, all 624 instrument checks pass. Across
30 seeds, 6237 of 6240 pass; the three failures are stock fortnights in which
volatility shows no memory at all, which is what that check is there to flag.

## Reproducibility contract

For a given MarketForge **major version**, `(seed, market, minute)` fully
determines every random shock. Output is identical regardless of which
instruments are selected, the timeframes, the output format, `--jobs`, whether
the spread is requested, how far `--to` extends, or whether the range was
generated at once or extended in steps. Changes that alter output for an
existing seed only ship in a new major version.

Candle values are bit-for-bit identical on a given platform and NumPy build.
Across machines they can differ in the last bit before rounding: NumPy picks
its `exp`/`log` implementation by CPU (for example AVX-512), and those differ by
one ulp on a small fraction of inputs. See
[ADR 0007](docs/adr/0007-optimise-without-changing-a-single-bit.md).

## Project layout

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
```

Each package may import from the ones listed above it, never from the ones
below; `aggregation`, `output` and `validation` do not import each other. CI
enforces this with `lint-imports`. The supported Python API is what
`import marketforge` exposes; module paths below it can change between releases.

## License

AGPL-3.0-or-later. See [LICENSE](LICENSE).
