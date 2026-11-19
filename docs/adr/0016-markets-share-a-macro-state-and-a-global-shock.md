# Markets share a macro state and a global shock

Each market was simulated from its own random stream and nothing else, so markets were statistically independent: BTC and AAPL had a daily correlation of 0.02, a stock crash never touched crypto, and the S&P CFD (SPXUSD, a forex instrument) did not follow S&P stocks. Cross-market stress tests and risk-on/risk-off models had nothing to learn from.

**Decision.** Two world-wide inputs link the markets. Both are drawn from streams keyed by the seed and the UTC day but not by the market, so every market computes them on its own: markets still run in parallel (ADR 0001) and a market's candles still do not depend on which other markets are generated (ADR 0007).

- The **global shock**, one normal per minute. Each market has a global direction, portfolio weights on its factors: its main factor for coins and stocks, and for forex a risk loading per code (equity CFDs most, commodity and emerging currencies up, havens down). The shock M of that portfolio is replaced by `c w + sqrt(1 - c^2) M`, which keeps the market's own correlation matrix exactly (ADR 0012) and correlates it with every other market. A closed market receives in its gap what the world did while it was shut.
- The **macro state**, calm or stressed, a two-state chain of days (about a month stressed per eight calm), run over eras of 4096 days that each start from the stationary distribution, so a day's state never needs more than one era. Stress raises the coupling `c`, makes the within-market stress shock (ADR 0014) partly a world-wide one from a third stream, tilts every market's next regime towards high volatility and crashes and ends calm spells early, and drifts every global direction down (a world bear market, about one spell standard deviation; calm days drift up by the share that keeps the long-run drift at the catalog's).

## Considered options

- **One regime for every market.** Crypto crashes without stocks, and stocks have quiet weeks while coins swing: a shared label is wrong, so each market keeps its own regime and the macro state only shifts its odds.
- **Solving for the factor exposure that reproduces a target loading** (`R a = g`). The fitted forex matrix gives almost no variance to the risk direction, so the solution blew up (weights of norm 100); a portfolio direction is always defined.
- **Reusing the global shock as the stress shock.** Every shock already holds it along its direction, so stressed minutes counted it twice, their variance rose above 1 and GARCH exploded within a session.

## Consequences

- Every seed's candles change (model revision 2).
- Daily correlations over 2022-2023, seed 3: BTC-AAPL 0.13 (0.28 weekly, 0.39 monthly), AUDUSD-SPXUSD 0.24, USDJPY-SPXUSD 0.50. Crypto is in high volatility or a crash 39% of the time stocks are, against 25% otherwise.
- SPXUSD follows the stocks' shocks (0.26 at m1) but not their own regime trends, which it cannot see from the forex market: its weekly correlation with AAPL stays near 0.1. Giving the index CFDs the stock market's trend would need the forex simulator to run the stock regime chain too.
- The global direction of a custom forex code without a risk loading is 0: it moves with the world only through its correlations.
