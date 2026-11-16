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
The market-wide hidden state (trend up, trend down, range, high volatility, crash) that scales drift and volatility for every instrument of a market at once.
_Avoid_: phase, mode, state

**Anomaly**:
An optional, deliberately unrealistic event layered on top of the base simulation: a spike or a flash crash.
_Avoid_: event, glitch, gap (gaps are not anomalies)

**Stylized fact**:
A statistical property documented for real returns (heavy tails, volatility clustering, leverage effect, realistic range) that generated data is validated against.
_Avoid_: realism metric, KPI
