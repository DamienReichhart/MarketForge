# Correlations intensify under stress through a common shock

One correlation matrix drove every minute, whatever the regime. In real markets co-movement intensifies in sell-offs: coins, stocks and dollar pairs move together exactly when diversification is needed. MarketForge had tail dependence (ADR 0005: extreme minutes hit everything at once), but BTC and a gaming coin were as correlated in a crash (0.55) as in a range.

**Decision.** In stressed regimes a common shock on the market's main factor, the one regimes trend along (ADR 0013), is added to every series' shock: `z_i' = sqrt(1 - s b_i^2) z_i + sqrt(s) b_i m`. Variance stays exactly 1 and the catalog's own pair structure is kept. Correlations become `sqrt((1 - s b_i^2)(1 - s b_j^2)) C_ij + s b_i b_j`, so pairs that move together move together more and pairs that move apart move apart more.

- `s` is 0.4 in high volatility and 0.75 in a crash, and 0 otherwise (`RegimeParams.stress`).
- The loadings `b` are the main-factor loadings, scaled so the most exposed series loads 0.95 and compressed (`|b|^0.3`) so weakly exposed series follow too.
- `m` is scaled by the minute's Student-t mixing variable, so the common part keeps the shocks' tails.
- `m` is a new draw, appended after the existing ones.

Measured (m5 returns, two years) from range to crash: BTC-SAND 0.55 to 0.82, AAPL-XOM 0.38 to 0.65, EURUSD-AUDUSD 0.42 to 0.70, EURUSD-USDCHF -0.66 to -0.86. The validation bands still pass for every instrument.

## Consequences

- Every seed's candles change (an *Output changes* entry, ADR 0011).
- Portfolio stress tests see diversification fail when it matters, rather than one fixed correlation.
