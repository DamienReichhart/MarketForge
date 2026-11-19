# The volatility budget holds at every horizon

The catalog's volatility and correlations were what the minute shocks had, not what a user measures. Two things outside the shocks added variance that nothing accounted for:

- **Regime trends.** A trend moved its market by about one spell standard deviation per spell, and a crash by 1.5 (ADR 0013). Over a day that added 0.4 to 1 times the diffusion's variance, and over a year 3 to 6 times: BTC, with a catalog volatility of 55%, moved 1.6 a year (in log), its median log drift was -0.6 a year from the variance drag, and over 2010-2020 seed 0 took every coin to the bottom of its tick grid. Trends move every series of a market together, so they also raised daily correlations: 0.72 among coins against the catalog's 0.53, 0.52 among stocks against 0.42.
- **Earnings.** Four jumps of 2.5 days' volatility a year, and the raised volatility after each, added 17% to a stock's variance: NVDA's daily volatility came out 13% above the catalog's.

**Decision.** The catalog's figures are those of daily returns, and the model is held to them at the daily horizon and kept near them beyond.

- **Trends are weak, and each label means what it says.** The strengths are solved per market so that, once centred, a spell of `trend_down` or a crash falls a quarter of its own standard deviation, `range` is flat, and `trend_up` rises by what offsets them (0.75; 0.5 in forex). The trend now adds 2-6% of the diffusion's variance at a day and 13-30% at a year: a mild momentum, as in real markets.
- **Reports fit in the stock's volatility.** The diffusion's variance makes room for the jumps and the raised volatility after them, in closed form (`earnings.diffusion_scale`).
- **Correlations are fitted at the daily horizon.** ADR 0012's fit gives the daily matrix; the minute shocks get the matrix whose simulated daily returns correlate as it says, found offline by simulation (`scripts/fit_correlations.py`). Both ship in `fitted_correlation.json`, with the model revision they were fitted for: loading fails if the model changed without a refit. An override file's correlations are daily ones too and go through the same mapping.

## Considered options

- **Keeping the trends and shrinking the diffusion to make room.** The catalog's volatility would hold at one horizon only: at a day minutes would be too quiet, at a year still too volatile, and a variance ratio of 2 at a month is not a market.
- **Normalising volatility to the year.** Same objection, the other way round: daily volatility, what every user measures first, would come out low.
- **A closed form for the daily correlations.** The trends are rank one along each market's main factor, but the stress shocks (ADR 0014), the world's coupling (ADR 0016) and the regimes' volatility interact, and an approximation would need checking by simulation anyway; fitting by simulation is exact for the model as it is, and runs offline.

## Consequences

- Every seed's candles and labels change (model revision 2). Regime labels carry less trend: a detector finds them mostly by their volatility.
- Over 2010-2020, daily volatility is 0.99 to 1.04 times the catalog's for coins, stocks and forex (ten seeds). Annual volatility (sixteen seeds) is 0.94 to 1.0 times for forex, 1.08 times for stocks, NVDA included, and 1.15 to 1.2 times for BTC and SPXUSD, whose trends and crashes cluster in the world's stressed spells. A 50%-volatile stock's decade now spreads as its volatility implies, within a factor of about 5.5 either way of its median for two seeds in three, and 30 for nineteen in twenty (NVDA: median 2.2 times its start over ten seeds, 0.1 to 197 at the extremes, where the tails of a heavy-tailed decade show); its trends no longer widen it.
- A change to the model or to a catalog's correlations or volatilities needs `python scripts/fit_correlations.py` (about half an hour).
