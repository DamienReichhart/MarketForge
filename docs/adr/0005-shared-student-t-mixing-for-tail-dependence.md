# Shocks share one Student-t mixing variable per market minute

Real sell-offs hit every instrument of a market at once, which independent fat-tailed shocks cannot reproduce: correlation alone leaves extremes uncorrelated. Each minute's shocks are therefore a multivariate Student-t built as a normal-variance mixture, `z = (Z Lᵀ) / sqrt(W) · sqrt((ν−2)/ν)` with a single `W ~ χ²(ν)/ν` shared by every series of the market, giving heavy tails *and* tail dependence while keeping unit variance and the catalog correlations. The alternative, an independent Student-t per series, was rejected because it keeps tails heavy but makes simultaneous crashes rare.

## Consequences

- ν is a market-wide calibration knob with outsized effect: one small `W` scales every instrument's shock together. Crypto at ν=5 produced 20–80σ minutes market-wide, so it runs at ν=6; ν must stay above 2 for finite variance.
