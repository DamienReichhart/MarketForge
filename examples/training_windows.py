"""Generated candles as fixed-size windows for a neural network.

`windows()` cuts each instrument's candles into windows of returns and log
volume (not price levels: every seed starts at the same prices), labelled
with the regime at each window's last candle. Training and validation use
disjoint seeds, so they share no path.
"""

import numpy as np

import marketforge as mf

WINDOW = 64


def windows(seed: int) -> tuple[np.ndarray, np.ndarray]:
    data = mf.generate(
        "BTCUSD,ETHUSD,SOLUSD",
        start="2024-01-01",
        days=30,
        seed=seed,
        timeframes="m5",
        with_regime=True,
    )
    x, y, _, _ = data.windows("m5", WINDOW, stride=4)
    return x, y


x_train, y_train = windows(seed=7)
x_valid, y_valid = windows(seed=8)
print("inputs", x_train.shape, "labels", y_train.shape, "classes", np.bincount(y_train))

try:
    import torch
    from torch.utils.data import DataLoader, TensorDataset
except ImportError:
    print("Install torch to wrap these arrays in a DataLoader.")
else:
    loader = DataLoader(
        TensorDataset(torch.from_numpy(x_train), torch.from_numpy(y_train)),
        batch_size=256,
        shuffle=True,
    )
    batch, target = next(iter(loader))
    print("batch", tuple(batch.shape), tuple(target.shape))
