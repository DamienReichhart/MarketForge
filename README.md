# MarketForge

Realistic synthetic OHLCV market data for backtesting, strategy development and
ML research. MarketForge simulates 208 instruments across crypto, forex and US
stocks minute by minute, on each market's real trading calendar, and publishes
candles from `m1` to `W1` as CSV, Parquet or pandas DataFrames.

```bash
pip install marketforge
marketforge generate -o ./data --from 2024-01-01 --to 2025-01-01 --assets EURUSD,AAPL,BTCUSD --seed 42
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
- **Fast and bounded in memory.** Simulation streams day by day through
  compiled (Numba) kernels. A year of EURUSD across all 8 timeframes takes about
  5 s. A month of all 208 instruments takes about 11 s. Memory does not grow
  with the date range.

## Installation

Python 3.10 or newer.

```bash
pip install marketforge
```

From source, with test and type-checking tools:

```bash
git clone https://github.com/DamienReichhart/MarketForge && cd MarketForge
pip install -e ".[dev]"
pytest
```

## Command line

```bash
# One year of EURUSD, every timeframe, reproducible
marketforge generate -o ./data --from 2024-01-01 --to 2025-01-01 --assets EURUSD --seed 42

# A whole market as Parquet, with regime labels
marketforge generate -o ./data --from 2024-01-01 --to 2024-07-01 --market crypto \
    --format parquet --with-regime --seed 7

# See what a run would produce (files, rows, disk size, time) without writing anything
marketforge generate --from 2015-01-01 --to 2025-01-01 --market all --dry-run

# List instruments (forex crosses are marked as derived)
marketforge list-assets --market forex

# Check a file against real-market stylized facts (exit code 1 on failure)
marketforge validate --input ./data/forex/EURUSD_m1.csv --market forex
```

### `generate` options

| Option | Meaning |
| --- | --- |
| `-o, --output-dir` | Where to write `{market}/{SYMBOL}_{timeframe}.{csv\|parquet}`. |
| `--from`, `--to` | Range `[from, to)`. Accepts `2024-01-01`, `2024-01-01T09:30`, `2024-01-01T09:30-05:00` or Unix seconds. UTC unless an offset is given. |
| `-a, --assets` | Comma-separated instruments. Their markets are inferred. |
| `-m, --market` | `crypto`, `forex`, `stocks` or `all`. Defaults to all when `--assets` is not given. With `--assets`, it keeps only the assets in these markets. |
| `-s, --seed` | Non-negative integer. When omitted, a random seed is used and printed so the run can be reproduced. |
| `-t, --timeframes` | Any of `m1,m5,m15,m30,H1,H4,D1,W1`. Default: all. |
| `--format` | `csv` (default) or `parquet`. Parquet files are about half the size and load much faster. |
| `--anomalies` | Optional unrealistic events: `spikes`, `flash_crash`. |
| `--with-regime` | Adds a `regime` column: 0 trend_up, 1 trend_down, 2 range, 3 high_volatility, 4 crash. |
| `--config` | TOML override file (see [Custom instruments](#custom-instruments)). |
| `-j, --jobs` | Markets simulated in parallel. Default: one per market, up to the CPU count. |
| `--dry-run` | Print the plan and estimates, then exit. |
| `--no-progress` | Hide the progress bar. |
| `--debug` (before the command) | Show full tracebacks. Errors are a single line otherwise. |

The pre-3.0 form `marketforge -o ... --from ... --to ...` still works for one
release and prints a deprecation note.

## Python API

```python
import marketforge as mf

data = mf.generate(
    ["EURUSD", "AAPL"],
    start="2024-01-01", end="2024-02-01",
    seed=42, timeframes=["m1", "H1", "D1"],
)
eurusd_h1 = data["EURUSD"]["H1"]     # DataFrame indexed by UTC time
print(data.seed)                     # 42 (or the random seed that was chosen)

# Stream large ranges to disk instead of memory
report = mf.generate_to_disk("./data", markets=["stocks"],
                             start="2015-01-01", end="2025-01-01",
                             seed=1, fmt="parquet", jobs=3)
print(report.n_files, report.paths["stocks"]["AAPL"]["D1"])
```

`generate` returns `{symbol: {timeframe: DataFrame}}`. Each DataFrame has a
UTC `DatetimeIndex` named `time` and the columns `open, high, low, close,
volume`, plus a categorical `regime` column with `include_regime=True`.

## Output

```
data/
├── crypto/BTCUSD_m1.csv, BTCUSD_H1.csv, ...
├── forex/EURUSD_m1.csv, ...
└── stocks/AAPL_m1.csv, ...
```

```csv
timestamp,open,high,low,close,volume
1704205800,185,185.04071674,184.83847841,184.845085,55469.4573
1704205860,184.845085,185.06763059,184.83059069,185.06591938,127601.9115
```

- `timestamp`: start of the candle, in Unix seconds (UTC). Parquet uses the same
  columns, with `timestamp` stored as int64.
- Prices are rounded to 8 decimals and volume to 4 (trailing zeros are not written).
- `high >= max(open, close)`, `low <= min(open, close)`, all prices and volumes
  positive.
- Within a session, each candle opens at the previous close. The first candle
  after a closure opens with a gap.

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

| Market | Instruments | Hours | Notes |
| --- | --- | --- | --- |
| crypto | 53 (BTCUSD, ETHUSD, SOLUSD, ...) | 24/7 | Heaviest tails (Student-t, 6 degrees of freedom). Weekends are quieter. |
| forex | 81: majors, crosses, exotics, metals (XAUUSD), index and oil CFDs | Sun 17:00 to Fri 17:00 NY | 41 anchor pairs are simulated and 40 crosses derived. Weekend gaps. |
| stocks | 74 US large caps (AAPL, MSFT, NVDA, JPM, ...) | NYSE session, holidays, early closes | Overnight and weekend gaps. U-shaped intraday volatility and volume. |

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
volume_base = 20000           # typical volume per minute
volume_volatility = 0.5       # lognormal sigma of volume noise
correlations = { BTCUSD = 0.6, ETHUSD = 0.55 }
```

```bash
marketforge generate -o ./data --from 2024-01-01 --to 2024-03-01 --assets MYCOIN,BTCUSD --config my_instruments.toml
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
  - s<sub>t</sub> is intraday seasonality.
- **Return** (open to close): μ<sub>f</sub> · d<sub>t</sub> + volatility · *z*,
  where d<sub>t</sub> is the regime drift multiplier.
- **Gaps**: after a closure of *C* minutes, the open jumps by a shock whose
  variance grows with *C*. Roughly 30% of a session's variance builds up
  overnight for stocks; a typical EURUSD weekend gap is about 10 pips.
- **High/low**: the exact maximum and minimum of a Brownian bridge from open to
  close, sampled from their closed-form distribution.
- **Volume**: a log-AR(1) process. It rises with the size of the standardized
  move, with the volatility level and with intraday seasonality, and has its
  own persistent noise.

Design decisions and their reasons are recorded in [`docs/adr/`](docs/adr), and
the vocabulary in [`GLOSSARY.md`](GLOSSARY.md).

## Validation

```bash
marketforge validate --input ./data/crypto/BTCUSD_m1.csv --market crypto
python scripts/benchmark_realism.py --seeds 123,7 --days 14   # every instrument
```

The validator measures open-to-close minute returns (overnight and weekend gaps
excluded) against per-market bands:

- **Heavy tails**: excess kurtosis in a realistic range.
- **Volatility clustering**: autocorrelation of |returns| that is significant
  and decays slowly.
- **Leverage effect**: returns are not positively correlated with next-period
  volatility. The band allows for sampling noise, and is looser for forex,
  where crosses have no natural "down".
- **Range efficiency**: mean(high − low) / mean(|close − open|). A pure random
  walk gives 2.0.

With two-week windows, about 99.8% of instrument checks pass across seeds. The
rare failures are single heavy-tailed assets on a particular seed, as with real
data.

## Reproducibility contract

For a given MarketForge **major version**, `(seed, market, minute)` fully
determines every random shock. Output is identical regardless of which
instruments are selected, the timeframes, the output format, `--jobs`, or how
far `--to` extends. Changes that alter output for an existing seed only ship in
a new major version.

## License

MIT. See [LICENSE](LICENSE).
