"""Run a strategy over many alternative histories and read its drawdowns.

One backtest gives one drawdown. Fifty seeds give a distribution, with
crash and high-volatility regimes in some of them, and its tail is the risk.
"""

import numpy as np

import marketforge as mf


def max_drawdown(equity: np.ndarray) -> float:
    return float((equity / np.maximum.accumulate(equity) - 1).min())


def buy_and_hold(data: mf.GeneratedData) -> np.ndarray:
    closes = data.panel("close", "H1").dropna()
    return (closes / closes.iloc[0]).mean(axis=1).to_numpy()  # equal-weight portfolio


if __name__ == "__main__":  # generate_many() starts processes: guard scripts like this
    drawdowns = [
        max_drawdown(buy_and_hold(data))
        for data in mf.generate_many(
            "BTCUSD,ETHUSD,SOLUSD",
            seeds=range(50),
            start="2024-01-01",
            days=90,
            timeframes="H1",
        )
    ]
    # Drawdowns are negative: the bad tail is the low percentiles.
    median, bad, worst = np.percentile(drawdowns, [50, 5, 1])
    print(f"max drawdown: median {median:.1%}, worst 5% {bad:.1%}, worst 1% {worst:.1%}")
