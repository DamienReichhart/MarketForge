---
title: Training ML models
description: "Use MarketForge to pre-train, augment and debug AI trading models, with ground-truth regime labels and leak-free splits."
---

Real market history is the scarcest input of a trading model: there is only one of it, it is unlabelled, and every model you fit on it leaks a little of it into the next one. MarketForge gives you as much realistic data as you need, with labels real data can never provide.

:::caution
A model trained only on synthetic data learns the generator, not the market. Use MarketForge to build and pre-train; judge the result on real, out-of-sample data. See [What it is not](../../limits/).
:::

## What you get

- **Ground-truth labels.** With `include_regime=True` (or `--with-regime`), every candle carries the hidden regime the simulator was in: `trend_up`, `trend_down`, `range`, `high_volatility` or `crash`. It is the true state, not a label inferred after the fact.
- **Unlimited, independent samples.** Each seed is a new, statistically realistic history. Disjoint seeds give train, validation and test sets that share no path, so no information leaks between them.
- **Realistic statistics.** Heavy tails, volatility clustering, long memory, the leverage effect and intraday seasonality are [validated](../../guides/validation/) against real minute data. A model that relies on returns being Gaussian fails here as it would on real data.
- **Multi-asset structure.** Instruments of a market share a correlation matrix, tail dependence and one regime, so cross-sectional models see realistic co-movement.
- **Exact reproducibility.** A seed and a version recreate a dataset bit for bit, so an experiment can be re-run from two integers.

## Split by seed, not by date

With real data you split one history by date and hope the regimes in the test period resemble the training period. With MarketForge, give each split its own seeds:

```python
import marketforge as mf

SPLITS = {"train": range(0, 64), "val": range(64, 72), "test": range(72, 80)}

def load(split: str):
    # One generation per seed, in parallel processes, yielded in seed order
    yield from mf.generate_many(
        "BTCUSD,ETHUSD,SOLUSD", seeds=SPLITS[split],
        start="2024-01-01", end="2024-04-01", timeframes=["m5"],
        include_regime=True, include_spread=True,
    )
```

Every seed starts from the catalog's start prices, so **model returns, not price levels**: the level carries no information.

## Recipe: a regime classifier

The regime label makes it possible to measure how well a detector recovers a hidden state, something you can never score on real data. A minimal scikit-learn baseline on rolling features of 5-minute returns:

```python
import numpy as np
import pandas as pd
import marketforge as mf
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import classification_report

def features(seed: int) -> pd.DataFrame:
    candles = mf.generate("BTCUSD", start="2024-01-01", end="2024-02-01", seed=seed,
                          timeframes=["m5"], include_regime=True)["BTCUSD"]["m5"]
    r = np.log(candles["close"]).diff()
    out = pd.DataFrame({
        f"{name}_{w}": getattr(r.rolling(w), name)()
        for w in (12, 48, 288) for name in ("mean", "std", "skew")
    })
    out["range"] = np.log(candles["high"] / candles["low"]).rolling(12).mean()
    out["volume"] = np.log(candles["volume"]).rolling(12).mean()
    out["regime"] = candles["regime"]
    return out.dropna()

train = pd.concat(features(s) for s in range(0, 8))
test = pd.concat(features(s) for s in range(100, 102))
X, y = train.drop(columns="regime"), train["regime"].astype(str)

model = HistGradientBoostingClassifier(max_iter=200).fit(X, y)
print(classification_report(test["regime"].astype(str), model.predict(test.drop(columns="regime"))))
```

Do not expect a high score from a baseline like this. Trained on eight seeds and tested on two others, its accuracy is around 55%: it is precise on crashes but misses half of them, and labels too many candles high volatility. That is the point: the label lets you *measure* how much of a hidden state your features recover, which real data never lets you do. Regimes last hours to days and changes ramp in, so the first candles after a switch are hard to classify, as they would be on real data.

## Recipe: windows for a sequence model

Turn a panel of returns into fixed-length windows for a PyTorch, JAX or Keras model. The target here is the next window's regime; swap in the next return, the next volatility, or anything else you can compute from the candles.

```python
import numpy as np
import marketforge as mf

def windows(seed: int, length: int = 128):
    data = mf.generate("BTCUSD,ETHUSD,SOLUSD", start="2024-01-01", end="2024-03-01",
                       seed=seed, timeframes=["m5"], include_regime=True)
    returns = np.log(data.panel("close", "m5")).diff().dropna()       # time × instrument
    regime = data["BTCUSD"]["m5"]["regime"].cat.codes.reindex(returns.index)
    x = np.lib.stride_tricks.sliding_window_view(returns.to_numpy(np.float32), length, axis=0)
    x = x.transpose(0, 2, 1)[:-1]                                     # (n, length, instruments)
    y = regime.to_numpy()[length:]                                    # regime after each window
    return x, y

x, y = windows(seed=0)
print(x.shape, y.shape)
```

Crypto trades 24/7, so its panel has no gaps. A panel that mixes markets has NaN where a market was closed, and markets start their candles on different clocks (a stock's `H1` candles at half past the hour), so their times may never coincide. MarketForge never forward-fills for you: see [Working with the data](../../guides/working-with-data/#several-instruments-side-by-side) for lining them up without look-ahead.

## Pre-training and augmentation

Two common patterns:

1. **Pre-train, then fine-tune.** Train on many synthetic seeds until the model has learned generic structure (volatility clustering, heavy tails, session effects), then fine-tune on the real data you have. Compare against a model trained on real data alone, on the same real test period.
2. **Augment.** Mix synthetic windows into real training batches to regularise a model that overfits a short history. Keep the real validation and test sets purely real.

In both cases, the only score that matters is the one on real, untouched data.

## Generating at scale

For datasets larger than memory, write Parquet to disk and stream it:

```bash check=static
for seed in $(seq 0 63); do
  marketforge generate -o ./train/seed-$seed --from 2020-01-01 --to 2024-01-01 \
      --market crypto -t m5,H1 --format parquet --with-regime --with-spread --seed $seed --no-progress
done
```

Markets are simulated in parallel (`--jobs`), memory stays flat whatever the range, and each dataset's `marketforge.json` records exactly how it was made.

## Pitfalls

- **Overfitting the generator.** Hyperparameters tuned until the synthetic validation score is perfect are tuned to MarketForge. Keep synthetic data for learning, real data for selection.
- **Regimes are market-wide.** Every instrument of a market shares one regime path; the label describes the market, not the individual instrument.
- **Labels are cleaner than reality.** Five sharp states are a simplification of real markets. A detector that is excellent here is an upper bound, not a guarantee.
- **Releases can change paths.** A seed's candles can change in any release that makes the data more realistic (see *Output changes* in the changelog). Pin the version and record it (the manifest does) next to your results.
