# Examples

Small, runnable scripts for the main uses of MarketForge. Each runs in seconds:

```bash
pip install marketforge scikit-learn   # scikit-learn for the classifier only
python examples/regime_classifier.py
```

| Script | What it shows |
| --- | --- |
| [`regime_classifier.py`](regime_classifier.py) | Train a regime detector on seed-disjoint train and test sets and score it against the ground-truth labels. |
| [`training_windows.py`](training_windows.py) | Turn generated data into `(samples, window, features)` arrays for a neural network, with a PyTorch `Dataset` when torch is installed. |
| [`backtest_smoke_test.py`](backtest_smoke_test.py) | Run a strategy that fills at the bid and ask on stocks with real NYSE sessions, overnight gaps and holidays. |
| [`monte_carlo_drawdowns.py`](monte_carlo_drawdowns.py) | Stress-test a strategy over many alternative histories in parallel and read the drawdown distribution. |

Remember what the data is for: a model trained only on MarketForge learns MarketForge. Use it to build, debug, pre-train and stress-test, and real data to decide whether anything earns money.
