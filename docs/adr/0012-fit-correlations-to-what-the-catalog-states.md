# Fit correlations to what the catalog states, through the forex anchors

The catalogs state the correlations that matter (BTC-ETH 0.88, EURUSD-USDCHF -0.92) and fill every other pair with a market default (0.50 crypto, 0.40 stocks, 0.25 forex). Together those values are not a valid correlation matrix (minimum eigenvalues -0.67, -0.29 and -2.0), and 3.x clipped its eigenvalues. Clipping treats every entry alike, so it moved stated pairs as much as the defaults: EURUSD-USDCHF became -0.45 and AUDUSD-NZDUSD 0.41. For forex it was also applied to a matrix that includes crosses, which are not simulated but derived from anchors (ADR 0002), so cross entries pulled the anchors, and cross volatilities came out about 1.5 times their stated values.

**Decision.** Each market's matrix is the valid one whose *implied* correlations come closest, in weighted least squares, to what the catalog states (`marketforge/config/catalog/correlation.py`). The factors are parametrised as `A A^T` with a unit diagonal, so every candidate is valid, and minimised with L-BFGS.

- **Weights say what was meant.** A stated pair counts 1, a default 0.05.
- **Forex is fitted through its anchors.** The unknown is the anchors' matrix. Every instrument's correlations and volatility are implied from it and the anchors' volatilities, so crosses are scored as what they are. A stated pair that involves a cross counts 0.1, because many of the hand-written values are impossible given the anchors (USDCHF-EURCHF is stated -0.78, but EURCHF = EURUSD x USDCHF makes it positive). The crosses' stated volatilities count fully, since they are measured directly, and defaults that involve a cross count 0.
- **The fit ships as data.** `scripts/fit_correlations.py` writes `fitted_correlation.json` beside each catalog. Loading it needs no optimiser and gives the same matrix on every platform. The file carries a digest of the problem it solves, and loading fails if a catalog changed without a refit.

Results: crypto and stocks move stated pairs by 0.012 and 0.003 on average (largest 0.05). Forex moves its 61 stated anchor pairs by 0.044 on average, and crosses come out at 0.72 to 1.16 times their stated volatilities. The largest forex shifts are where the catalog contradicts itself. For example, with real volatilities EURUSD-USDCHF near -0.73 is what makes EURCHF's 5-6% possible, and the fit gives -0.72.

## Consequences

- Every seed's candles change (an *Output changes* entry, ADR 0011).
- Changing a catalog's stated correlations or volatilities needs `python scripts/fit_correlations.py`, and its printout shows how far the fit had to move them.
- Override edits that contradict the market are repaired with the nearest correlation matrix (Higham's alternating projections), only on the simulated block. The edited pairs are held fixed when they can all hold, and when they cannot, every entry moves as little as possible. It runs in NumPy, so overrides need no optimiser.
