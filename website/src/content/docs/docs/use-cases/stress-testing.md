---
title: Stress testing
description: Run a strategy through hundreds of alternative histories, crashes and flash crashes included, and look at the distribution of outcomes instead of one equity curve.
---

History happened once. A strategy that survived it may simply have been lucky with the order of events. MarketForge lets you replay the same market structure many times over, with a different sequence of regimes, shocks and crashes each time.

## Many seeds, one distribution

Each seed is an independent history with the same statistical properties. Run the strategy across a range of seeds and collect the metrics you care about:

```python
import numpy as np
import marketforge as mf

def max_drawdown(equity: np.ndarray) -> float:
    return float((equity / np.maximum.accumulate(equity) - 1).min())

results = []
for seed in range(200):
    data = mf.generate("SPXUSD,XAUUSD,EURUSD", start="2024-01-01", end="2025-01-01",
                       seed=seed, timeframes=["H1"], include_spread=True, include_regime=True)
    equity = run_my_strategy(data)            # your backtest, returning an equity curve
    results.append(max_drawdown(equity))

print(np.percentile(results, [50, 95, 99]))   # typical, bad and very bad drawdown
```

The 99th percentile of drawdown across 200 histories says far more about risk than the single drawdown of one backtest.

## Crash and high-volatility regimes

The base model already contains stress. The market moves between trend, range, **high volatility** and **crash** regimes, with heavy-tailed Student-t shocks whose tail risk is shared across a market, so sell-offs hit every instrument at once. With `include_regime=True`, you can break results down by regime and see where a strategy loses:

```python
candles = data["SPXUSD"]["H1"]
pnl = strategy_returns(candles)               # per-candle P&L of your strategy
print(pnl.groupby(candles["regime"], observed=True).agg(["mean", "std", "count"]))
```

## Anomalies: deliberately extreme events

On top of the realistic base you can inject events that are **deliberately unrealistic** in size or frequency, to check how a system behaves at the edge:

| Anomaly | What it does |
| --- | --- |
| `spikes` | Single-candle fat-tail moves with long wicks. |
| `flash_crash` | Multi-candle V-shaped crashes and recoveries. |

```bash
marketforge generate -o ./stress --from 2024-01-01 --days 90 --market crypto \
    --anomalies spikes,flash_crash --with-regime --seed 13
```

Use them to test stop-loss logic, margin checks, circuit breakers, alerting and data-quality filters. Anomalies are excluded from the realism contract: validate stress datasets for robustness, not for realism.

## Turn up the volatility

To test a strategy in a calmer or wilder world, change an instrument's annual volatility or drift with an [override file](../../guides/custom-instruments/):

```toml
[instruments.BTCUSD]
volatility = 1.20   # twice its usual annualised volatility
drift = -0.5        # a bear market
```

Regime multipliers are normalised, so they change *when* volatility and drift happen, not how much: the annual figures you set are what you get.
