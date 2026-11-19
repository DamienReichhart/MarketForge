# Markets share a macro state and a global shock

Each market was simulated from its own random stream and nothing else, so markets were statistically independent: BTC and AAPL had a daily correlation of 0.02, a stock crash never touched crypto, and the S&P CFD (SPXUSD, a forex instrument) did not follow S&P stocks. Cross-market stress tests and risk-on/risk-off models had nothing to learn from.

**Decision.** Two world-wide inputs link the markets. Both are drawn from streams keyed by the seed and the UTC day but not by the market, so every market computes them on its own: markets still run in parallel (ADR 0001) and a market's candles still do not depend on which other markets are generated (ADR 0007).

- The **global shock**, one normal per minute. Each market has a global direction, portfolio weights on its factors: its main factor for coins and stocks, and for forex a risk loading per code (equity CFDs most, commodity and emerging currencies up, havens down). The shock M of that portfolio is replaced by `c w + sqrt(1 - c^2) M`, which keeps the market's own correlation matrix exactly (ADR 0012) and correlates it with every other market. A closed market receives in its gap what the world did while it was shut.
- The **stock market's regime chain**, for the index CFDs. A market's regime draws come from a random stream of their own, so the forex simulator runs the stock market's chain too, over NYSE's open minutes, and gets the stock simulator's exact path. Each index CFD follows the stock market's trend during those minutes, by its risk loading relative to the S&P 500's (SPXUSD and NSXUSD fully, UKXGBP 0.7, JPXJPY 0.6), scaled to its own volatility; the forex checkpoint carries the chain.
- The **macro state**, calm or stressed, a two-state chain of days (about a month stressed per eight calm), run over eras of 4096 days that each start from the stationary distribution, so a day's state never needs more than one era. Stress raises the coupling `c`, makes the within-market stress shock (ADR 0014) partly a world-wide one from a third stream, tilts every market's next regime towards high volatility and crashes and ends calm spells early, and drifts every global direction down (a world bear market, about one spell standard deviation; calm days drift up by the share that keeps the long-run drift at the catalog's).

## Considered options

- **One regime for every market.** Crypto crashes without stocks, and stocks have quiet weeks while coins swing: a shared label is wrong, so each market keeps its own regime and the macro state only shifts its odds.
- **Solving for the factor exposure that reproduces a target loading** (`R a = g`). The fitted forex matrix gives almost no variance to the risk direction, so the solution blew up (weights of norm 100); a portfolio direction is always defined.
- **Reusing the global shock as the stress shock.** Every shock already holds it along its direction, so stressed minutes counted it twice, their variance rose above 1 and GARCH exploded within a session.

## Consequences

- Every seed's candles change (model revision 2).
- Daily correlations over 2022-2023, seed 3: BTC-AAPL 0.13 (0.28 weekly, 0.39 monthly), AUDUSD-SPXUSD 0.24, USDJPY-SPXUSD 0.50. Crypto is in high volatility or a crash 39% of the time stocks are, against 25% otherwise.
- SPXUSD follows the stocks' shocks and their regime trends: over 2016-2023 (three seeds) it correlates with an equal-weight basket of ten large caps 0.66 weekly and 0.77 monthly, and with AAPL 0.58 weekly. Before the stock chain was shared its weekly correlation with AAPL was about 0.1: it followed the stocks' shocks but not their bull and bear spells.
- At m1, during NYSE hours, SPXUSD and AAPL correlate 0.31 (daily 0.43): the forex catalog's correlations allow SPXUSD's shock to be about 0.84 the world's, and quote noise does the rest. Real index futures correlate more with large caps minute by minute.
- Running the stock chain costs the forex simulator two draws of 1440 numbers and a 390-step loop a day, only when an index CFD is generated.
- The global direction of a custom forex code without a risk loading is 0: it moves with the world only through its correlations.
