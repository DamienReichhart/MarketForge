---
title: "The model"
description: "How MarketForge simulates prices, volatility, regimes, the world's macro state, gaps, earnings, pegs, highs and lows, volume and ticks, minute by minute."
---

MarketForge simulates each market minute by minute, one UTC day at a time, carrying the model's state (prices, GARCH variance, regime spell, volume memory, slow volatility) from day to day. Every instrument of a market is simulated jointly, so correlation, tail dependence and the regime are shared. See [ADR 0001](../../adr/0001-simulate-whole-market-day-by-day/). The three markets are linked by a world-wide **global shock** and **macro state**, which every market computes on its own from the seed, so markets still run in parallel. See [The world](#the-world).

Each open minute *t*, every simulated series *f* (an instrument, or a forex anchor pair from which the crosses are derived) moves from open to close by the log return

<p style="text-align:center;font-size:1.2em">r<sub>f,t</sub> = μ<sub>f</sub> + m<sub>f,t</sub> + λ<sub>f</sub> · d<sub>t</sub> + σ<sub>f</sub> · v<sub>f,t</sub> · √h<sub>t</sub> · g<sub>t</sub> · s<sub>t</sub> · z<sub>f,t</sub></p>

the instrument's own drift, plus the world's bull or bear drift, plus the regime's trend along the market's main factor, plus a shock scaled by five volatility terms. Prices are then quoted with microstructure noise and rounded to the tick. The sections below define each term, then how gaps, highs and lows, volume and the spread are built around it.

| Term | What it is | Section |
| --- | --- | --- |
| *z* | Correlated Student-t shock, shared tail risk | [Shocks](#shocks) |
| σ<sub>f</sub> | The instrument's volatility per minute | [Volatility](#volatility) |
| h<sub>t</sub> | GJR-GARCH clustering and leverage | [Volatility](#volatility) |
| s<sub>t</sub> | Intraday and weekly seasonality | [Volatility](#volatility) |
| g<sub>t</sub> | The regime's volatility multiplier | [Regimes](#regimes) |
| d<sub>t</sub>, λ<sub>f</sub> | The regime's trend, and the series' exposure to it | [Regimes](#regimes) |
| μ<sub>f</sub> | The instrument's drift per minute | [Returns](#returns) |
| m<sub>f,t</sub> | The macro state's drift: a world bear market while stressed | [The world](#the-world) |
| v<sub>f,t</sub> | Slow volatility, and the boost after an earnings report | [Volatility](#volatility) |

## Shocks

Correlated, unit-variance **Student-t shocks** *z*, built as a normal variance mixture. The mixing variable is shared by the whole market, which creates **tail dependence**: in a sell-off, every instrument gets the large shock at once, as in real markets, rather than independently. See [ADR 0005](../../adr/0005-shared-student-t-mixing-for-tail-dependence/).

Crypto shocks have 6 degrees of freedom, the heaviest tails of the three markets.

In high-volatility and crash regimes a common shock is added to every instrument, so **correlations intensify under stress** as they do in real sell-offs. From range to crash, BTC-SAND goes from 0.55 to 0.82, AAPL-XOM from 0.38 to 0.65 and EURUSD-USDCHF from -0.66 to -0.86. See [ADR 0014](../../adr/0014-correlations-intensify-under-stress/).

## The world

Two world-wide inputs, drawn from streams keyed by the seed and the day but not by the market, link the three markets, and the index CFDs follow the stock market's own regime. See [ADR 0016](../../adr/0016-markets-share-a-macro-state-and-a-global-shock/).

- **The global shock** is one normal per minute. Each market has a global direction: its main factor for coins and stocks, and for forex a risk loading per code (equity index CFDs most, commodity and emerging currencies up, the yen, the franc, the dollar and gold down). The shock of that direction is partly replaced by the global shock, which keeps the market's own correlations exactly and correlates it with the other markets: BTC-AAPL is about 0.13 daily, 0.3 weekly and 0.4 monthly. A market that was closed receives in its gap what the world did meanwhile.
- **The stock market's regime chain** is run by the forex market too (regime draws have a random stream of their own in every market), so during NYSE hours the index CFDs follow the stock market's regime: its trend (each by its risk loading relative to the S&P 500's), its volatility and its stress shocks. SPXUSD correlates about 0.6 weekly with a basket of large caps.
- **The macro state**, calm or stressed, changes at UTC midnight: about a month stressed per eight months calm. While stressed, every market's coupling to the world rises, its next regime is tilted towards high volatility and crashes, its calm spells end early, and the world drifts down along every market's global direction by about one standard deviation of the stressed spell (calm days drift up by the share that keeps the long-run drift at the catalog's). `GeneratedData.macro()` labels every day.

## Volatility

σ<sub>f</sub> · v<sub>f,t</sub> · √h<sub>t</sub> · g<sub>t</sub> · s<sub>t</sub>, where:

- σ<sub>f</sub> is the per-minute level implied by the instrument's annual volatility on its market's calendar.
- v<sub>f,t</sub> is **slow volatility**: the log volatility of each series wanders from day to day (an AR(1) with a half-life of 60 days, mean square 1), so a decade has calm and turbulent years. For a stock it is also raised after an [earnings report](#earnings).
- h<sub>t</sub> is a **GJR-GARCH(1,1)** multiplier with unit mean. It gives volatility clustering and the **leverage effect**: down-moves raise volatility more than up-moves.
- g<sub>t</sub> is the **regime** multiplier, smoothed so regime changes ramp in.
- s<sub>t</sub> is **intraday seasonality**:
  - **Stocks:** the U shape of the session, with first minutes about three times as volatile as midday.
  - **Forex:** the Tokyo, London and New York sessions, each on its own clock, so London's open moves an hour in UTC with British summer time. Add bursts at the London open, at 08:30 New York (US data releases) and at the 16:00 London fix, thinner Friday afternoons and Sunday opens, and thin holidays: about a third of normal activity on 25 December and 1 January, two thirds around them.
  - **Crypto:** a peak around the US open, quieter weekends, and short bursts at the 00:00, 08:00 and 16:00 UTC funding settlements of perpetual futures.

## Regimes

A market-wide hidden state: **trend up**, **trend down**, **range**, **high volatility** or **crash**. It sets the trend and scales the volatility of every instrument of the market at once. Regimes last hours to days: crypto trends average about 1.7 days and crashes about 13 hours.

A regime lasts a **spell** of its mean length times a Gamma(2) draw: a typical length (coefficient of variation 0.71) rather than a Markov chain's memoryless one (1.0), so a hidden Markov model is not the exact model of the data. When a spell ends, the next regime is drawn from the transition matrix's off-diagonal row, tilted by the [macro state](#the-world). Regimes never react to prices, so the label stays an independent ground truth. See [ADR 0017](../../adr/0017-regimes-are-semi-markov-spells-and-never-react-to-price/).

A regime trends along the market's main factor: all coins together, all stocks together, and in forex the dollar (`trend_up` is the dollar falling, so EURUSD rises and USDCHF falls). A spell of `trend_down` or a crash falls a quarter of its own standard deviation on average, `range` is flat, and `trend_up` climbs by what offsets them (about three quarters of a standard deviation; half in forex): markets climb slowly and fall fast. Trends are weak, as in real markets: they add 2-6% of the variance at a day and 13-30% at a year, and within a minute they are lost in the noise. Trends average to zero, volatility multipliers are normalised, and a stock's earnings reports are inside its volatility, so the catalog's volatility is what daily returns show and its drift what you get over the long run ([ADR 0018](../../adr/0018-the-volatility-budget-holds-at-every-horizon/)). See [ADR 0013](../../adr/0013-regimes-trend-along-the-market-factor/). With `--with-regime`, the regime of each candle is written next to it.

## Returns

The open-to-close log return adds three parts: μ<sub>f</sub>, the per-minute drift implied by the instrument's annual drift; the regime's trend λ<sub>f</sub> · d<sub>t</sub>, where d<sub>t</sub> is the regime's trend strength (smoothed, so it ramps in) and λ<sub>f</sub> is the series' volatility times its loading on the market's main factor; and the volatility times the shock *z*. The trend is additive and averages to zero over the long run, so the catalog's annual drift is what you get. Each candle opens at the previous close, except after a closure.

## Gaps

After a closure of *C* minutes, the open jumps by a shock whose variance grows with *C*, and which carries the global shocks of the closed minutes. Roughly 30% of a session's variance builds up overnight for stocks; a typical EURUSD weekend gap is about 10 pips.

## Earnings

Every stock reports four times a year, after the close of a trading day of its own in the fourth to sixth week of each quarter, the same days whatever the seed (`GeneratedData.earnings()` lists them). The next open jumps by about 2.5 days of the stock's volatility, Student-t with 4 degrees of freedom, so a few reports move a stock three or four times more; NVDA's reach about 20%. Volatility doubles on the first session and decays over a few days, which raises volume and the spread too. `earnings_move` in an [override file](../../guides/custom-instruments/) sets the jump's size, 0 for none. Stocks pay no dividends and never split.

## Pegs

USDHKD stays in Hong Kong's 7.75-7.85 band and EURDKK within ERM II's 2.25% of 7.46038, each pulled towards its centre with a half-life of weeks; USDCNH is managed, with a weak pull within 8% of its start price. The pull acts on the pegged currency's anchor pair, so its crosses follow.

## High and low

The exact maximum and minimum of a **Brownian bridge** from open to close, sampled from their closed-form distribution, so `high >= max(open, close)` and `low <= min(open, close)` by construction. The excursion uses a fraction of the bar's volatility (0.62 for crypto), because real minutes wander less inside the bar than a pure random walk. A minute that moved far was turbulent, so 40% of its squared body is added to that variance: the biggest moves keep retracement wicks (range about 1.3 to 1.4 times the body) instead of being bare bodies.

## Volume

A **log-AR(1)** process. Volume rises with the size of the standardized move, with the volatility level (the mixture-of-distributions hypothesis) and with intraday seasonality, and has its own persistent noise. Stocks add the NYSE **auctions**: the closing cross prints about 5-9% of a day's volume, the open about 3%. Stock volume is whole shares and forex tick volume whole ticks.

## Quotes and ticks

The published mid jitters around the simulated, efficient price by a share of the minute's volatility (0.25 for stocks and forex, 0.15 for crypto), the **microstructure noise** of real quotes: minute returns revert slightly (AAPL's lag-1 autocorrelation is about -0.04) and minute correlations are lower than daily ones (AAPL-MSFT 0.73 at m1, 0.81 daily: the Epps effect). Each open is still the previous close.

Every price is then a whole number of the instrument's **tick**: a cent for stocks (a hundredth of a cent below $1), and about five significant digits elsewhere (0.00001 on EURUSD, 0.001 on USDJPY, 0.01 on XAUUSD, 0.1 on BTCUSD). `tick_size` in an override file sets it. A forex cross equals the product of its anchors to within the rounding of the three prices.

## Spread

An optional column around the mid price, modelled separately so asking for it changes no other column. See [Bid-ask spread](../spread/).

## Anomalies

Optional, deliberately unrealistic events layered on top of the base simulation: `spikes` (single-candle fat-tail moves) and `flash_crash` (multi-candle V-shaped crashes). They are not part of the realism contract.

## Performance

The kernels are compiled with [Numba](https://numba.pydata.org/), and only the instruments you ask for are computed past the random draws. A year of EURUSD across the eight standard timeframes takes about 2 s; a month of all 208 instruments, all eight, about 6 s. Memory does not grow with the date range. See [ADR 0003](../../adr/0003-stay-in-python-with-numba/).
