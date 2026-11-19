# Regimes trend along the market's main factor, with a strength per spell

Up to 3.x a regime scaled each instrument's catalog drift by a multiplier (trend_up 2.5, crash -6). Catalog drifts are a few percent a year, so the per-minute effect was invisible: over 90 days of BTC, mean returns within each regime had t-statistics below 1, and `trend_up` averaged a negative return. Every forex pair has a catalog drift of 0, so forex regimes could not trend at all. A classifier trained on the labels learned the volatility level and nothing else, which made "ground-truth regimes" an empty claim.

**Decision.** Each regime has a **trend strength**: the expected log return over an average spell of the regime, divided by that spell's volatility. The per-minute trend of regime r is then `k_r * v_r / sqrt(D_r)`, with `D_r` the mean spell length in open minutes and `v_r` the normalised volatility multiplier, times each series' volatility and its **loading on the market's main factor**.

- The main factor is the first principal component in crypto and stocks, so all coins and stocks trend together, idiosyncratic names less. In forex it is an equal-weight **dollar index** of the anchors: the anchors' first component is a risk factor on which EURUSD barely loads. It is signed so the market's lead series (BTCUSD, EURUSD, AAPL) loads positively: `trend_up` means BTC and stocks rise and the dollar falls.
- **Trends are additive and centred.** Their long-run mean is 0, so the catalog's annual drift is still what you get. Centering offsets the crashes and lifts every regime by about 0.3-0.4, so the defaults are (trend_up 1.0, trend_down -1.4, range 0, high_volatility -0.3, crash -1.5). After centering, a spell of `trend_up` or `trend_down` ends in its direction about 70-90% of the time, and a crash falls about 1.5 of its own standard deviations. (The strengths were cut in 5.0, ADR 0018: they added several times the diffusion's variance over a year.)
- No random draw changes, only the arithmetic of the drift.

## Consequences

- Every seed's candles change (an *Output changes* entry, ADR 0011).
- Labels are now learnable from the path over a spell. At the minute scale the trend is still small next to the noise, as in real markets. A detector needs hours of context, and that is the honest difficulty.
- `RegimeParams.drift_multipliers` is gone; `trend_strength` replaces it.
