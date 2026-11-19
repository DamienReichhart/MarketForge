# MarketForge

Synthetic market-data generation: simulating price, volume and regime paths for
tradable instruments and publishing them as candles at several timeframes.

## Language

### Markets and instruments

**Market**:
A family of instruments that share one trading calendar, one regime path and one set of model parameters: `crypto`, `forex` or `stocks`.
_Avoid_: asset class, exchange, venue

**Instrument**:
A tradable symbol whose candles MarketForge publishes (e.g. `EURUSD`, `AAPL`, `BTCUSD`).
_Avoid_: asset, ticker, pair (when meaning the general concept)

**Code**:
One side of a forex instrument's symbol: the base or quote currency, metal, index or commodity (`EUR`, `JPY`, `XAU`, `SPX`).
_Avoid_: currency (codes are not all currencies), leg

**Anchor pair**:
The single forex instrument that ties a code to the rest of the forex market; anchor pairs are simulated directly.
_Avoid_: major, base pair, primary pair

**Cross**:
A forex instrument that is not an anchor pair; its prices are derived from anchor pairs so that every triangle is arbitrage-free.
_Avoid_: derived pair, synthetic pair

**Catalog**:
The built-in list of instruments per market with their start price, volatility, drift, base volume and correlations.
_Avoid_: universe, config, asset list

**Override file**:
A user TOML file that changes catalog entries or adds new instruments without editing the package.
_Avoid_: custom config, settings file

### Time

**Trading calendar**:
The rules that say which minutes a market is open: crypto always, forex Sunday 17:00 to Friday 17:00 New York, stocks the NYSE session on NYSE trading days.
_Avoid_: schedule, session handler

**Session**:
One contiguous run of open minutes between two closures.
_Avoid_: trading day (a forex session spans five days)

**Closure**:
A run of minutes during which a market is closed; no candles exist for it.
_Avoid_: gap (a gap is the price jump a closure produces), downtime

**Gap**:
The difference between a session's first open and the previous session's last close, produced naturally by the closure between them.
_Avoid_: jump, discontinuity

**Bar anchor**:
The local wall-clock time at which a market's daily and weekly candles start: 00:00 UTC for crypto, 17:00 New York for forex, 09:30 New York for stocks.
_Avoid_: day start, rollover

**Timeframe**:
The duration a candle summarises: `m1`, `m5`, `m15`, `m30`, `H1`, `H4`, `D1`, `W1`.
_Avoid_: resolution, interval, period

**Tick volume**:
The number of price updates in a minute; the volume reported for forex, which has no consolidated traded volume.
_Avoid_: lots, notional (for forex volume)

**Candle**:
One open/high/low/close/volume record for an instrument over one timeframe bucket.
_Avoid_: bar (in prose), row, tick

**Partial candle**:
A candle whose bucket is not fully covered by the requested range; it is never published.
_Avoid_: incomplete bar, stub

### Simulation

**Seed**:
The integer that, together with the market and the minute, fully determines every random shock MarketForge draws.
_Avoid_: random state, salt

**Shock**:
The standardized random innovation that drives one minute of one anchor series.
_Avoid_: noise, innovation (in user-facing text), epsilon

**Regime**:
The market-wide hidden state (trend up, trend down, range, high volatility, crash) that sets the trend and scales the volatility of every instrument of a market at once. A trend moves the market's main factor: all coins, all stocks, or the dollar. Each market has its own regime; the macro state only shifts the odds of the next one.
_Avoid_: phase, mode, state

**Spell**:
One uninterrupted stay of a market in a single regime, from the minute it enters it to the minute it leaves.
_Avoid_: episode, run, duration (a spell has a duration)

**Macro state**:
The world-wide hidden state, calm or stressed, shared by every market; while it is stressed, each market is more likely to enter high volatility or a crash.
_Avoid_: global regime (a regime belongs to one market), contagion, risk-off

**Global shock**:
The common random innovation every market's shocks load on, which links crypto, forex and stocks; index CFDs load on it most.
_Avoid_: world factor, macro factor, stress (stress acts within one market)

**Trend strength**:
A regime's expected log return over an average spell of the regime, in units of that spell's volatility, along the market's main factor.
_Avoid_: drift multiplier (the 3.x mechanism it replaced)

**Stress**:
The weight of a common shock added to every instrument's shock in high-volatility and crash regimes, which makes correlations intensify.
_Avoid_: contagion, correlation breakdown

**Model revision**:
The integer that names a generation of the model's output (`marketforge.MODEL_REVISION`). It is incremented in any release that changes what a seed produces; `extend` only continues a dataset written with the same one.
_Avoid_: model version, output version

**Anomaly**:
An optional, deliberately unrealistic event layered on top of the base simulation: a spike or a flash crash.
_Avoid_: event, glitch, gap (gaps are not anomalies)

**Turbulence**:
The market's current volatility level relative to normal (GARCH multiplier times regime multiplier, excluding intraday seasonality); volume rises with it.
_Avoid_: stress, heat

**Tick size**:
The smallest price step an instrument's prices are quoted in; every published price is a whole number of ticks.
_Avoid_: pip (a pip is a forex convention, often ten ticks), precision, decimals

**Earnings event**:
A stock's scheduled quarterly results, released while its market is closed, that open the next session with a jump and raise its volatility and volume for a few days.
_Avoid_: earnings gap (the gap is what the event produces), announcement, news

**Spread**:
The quoted bid-ask difference around a candle's mid price, in price units; candle prices are mid prices.
_Avoid_: commission, slippage, cost

**Validation band**:
The range a stylized-fact statistic of generated data must fall in for a market, anchored to the same statistic measured on real data.
_Avoid_: threshold, target, KPI

**Stylized fact**:
A statistical property documented for real returns (heavy tails, volatility clustering, leverage effect, realistic range) that generated data is validated against.
_Avoid_: realism metric, KPI

### Datasets

**Dataset**:
The directory of candle files one generation produces, together with its manifest.
_Avoid_: output directory (in prose), dump, export

**Layout**:
How a dataset's candles are split into files: one file per instrument and timeframe (the default), or the long layout of one file per timeframe holding every instrument.
_Avoid_: structure, partitioning, schema

**Manifest**:
The record kept inside a dataset of how it was produced: version, seed, range, instruments, timeframes, format and overrides.
_Avoid_: metadata, run log, config

**Extension**:
Continuing a dataset forward in time so that it equals the dataset a single longer generation would have produced.
_Avoid_: append, resume, update
