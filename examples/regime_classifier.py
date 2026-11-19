"""Train a regime detector on synthetic data and score it on ground-truth labels.

Train and test sets come from disjoint seeds, so they share no path: a score
that real data, with its single history and no labels, can never give.
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import classification_report

import marketforge as mf


def features(candles: pd.DataFrame) -> pd.DataFrame:
    r = np.log(candles["close"]).diff()
    out = pd.DataFrame(index=candles.index)
    for hours in (6, 24, 72):
        out[f"ret_{hours}h"] = r.rolling(hours).sum()  # trend over the window
        out[f"vol_{hours}h"] = r.rolling(hours).std()  # volatility level
    out["regime"] = candles["regime"].astype(str)
    return out.dropna()


def dataset(seeds: range) -> pd.DataFrame:
    frames = [
        features(data["BTCUSD"]["H1"])
        for data in mf.generate_many(
            "BTCUSD",
            seeds=seeds,
            start="2023-01-01",
            days=180,
            timeframes="H1",
            with_regime=True,
        )
    ]
    return pd.concat(frames)


if __name__ == "__main__":
    train, test = dataset(range(6)), dataset(range(100, 102))
    model = HistGradientBoostingClassifier(max_iter=200).fit(
        train.drop(columns="regime"), train["regime"]
    )
    print(classification_report(test["regime"], model.predict(test.drop(columns="regime"))))
