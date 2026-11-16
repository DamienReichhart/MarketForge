# Noise allowances use the sample's own standard errors

A two-week sample of stock minutes is about 3,900 returns, so a statistic can fall outside its validation band by chance. The leverage and long-memory bands therefore allowed two standard errors, taken as 1/sqrt(n). That formula holds for independent normal data. Minute returns are heavy-tailed and their volatility clusters: across seeds, the leverage correlation of a generated stock scatters by 0.042 where 1/sqrt(n) says 0.017. Sound samples failed for that reason alone (9 of 2080 instrument checks over ten seeds, 7 of them on leverage, all stocks).

The allowance is still two standard errors, but the standard error is now estimated from the sample: a Newey-West variance of the standardised cross-products for the two correlations, and the fourth-to-eighth-moment formula for kurtosis, whose floor gets the same allowance. On independent normal data they reduce to the textbook values, so the validator is exactly as strict as before on data without tails or clustering, and i.i.d. returns still fail the long-memory check. On generated stocks the leverage standard error is calibrated: the statistic's scatter across seeds is 1.06 times it.

We considered and rejected widening the bands instead (ADR 0006 forbids loosening a band to make a calibration pass, and the bands were not the error), allowing three standard errors of the wrong size, and bootstrapping every statistic, which is correct but too slow for a benchmark over every instrument.

## Consequences

- **The long-memory standard error is still an underestimate.** How much volatility persists over an hour depends on a handful of regime changes that no two-week sample can count: with a bandwidth of four times the lag the estimate is 0.043 on stocks, against a scatter of 0.067 across seeds. Over 30 seeds, 3 of 6240 instrument checks still fail, all on long memory, in stock fortnights whose volatility shows no memory at all.
- The allowance is widest on the samples with the fattest tails. The kurtosis ceiling gets no allowance, so one giant minute still fails it.
- The crypto bands were widened separately, on evidence: measuring four more coins (XRP, DOGE, TRX, LINK) showed a fortnight of XRP reaching an excess kurtosis of 1331, twice the most extreme window of BTC, ETH and SOL.
