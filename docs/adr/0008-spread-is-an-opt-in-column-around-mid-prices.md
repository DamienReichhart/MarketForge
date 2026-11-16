# Spread is an opt-in column around mid prices

A backtest of a forex or intraday strategy is wrong without trading costs, and MarketForge published none. We now simulate a quoted bid-ask spread and publish it as one optional `spread` column, in price units, next to candles whose prices are defined as mid prices (bid = price - spread / 2). We rejected separate bid and ask candle files: they double the output and force every user to choose a side, while a mid price and a spread reconstruct both. We rejected redefining the existing prices as bid prices (the MetaTrader convention): it would have changed the meaning of every dataset already generated.

The spread is opt-in and draws from its own random stream (`(seed, market, day, stream 2)`), so requesting it changes no other number and the feature did not need a seed-breaking release (ADR 0007). On higher timeframes a candle carries the mean spread of its minutes.

Per minute the spread is the instrument's typical level times the turbulence to the power 0.5, the inverse of intraday seasonality to the power 0.5, a term that decays over the first minutes after a closure, and lognormal noise, floored at one tick for stocks. It has no memory of its own: all persistence comes from turbulence, which keeps the simulator's checkpoint unchanged (ADR 0009).

## Consequences

- **Levels are estimates.** We have no quote data. Built-in instruments get their typical level from a per-market rule on their volatility (more volatile means less liquid), not from per-instrument research, and users set `spread_bps` to match their broker. The README says so wherever a number appears.
- **The validation bands for spread are provisional in every market**, including crypto, whose other bands are anchored (ADR 0006). They only rule out the absurd: a median outside 0.05 to 40 basis points, or spreads that narrow in turbulence. Measuring real quotes replaces them.
- Spread does not model commissions, slippage or depth. A strategy that trades size still needs its own cost model.
