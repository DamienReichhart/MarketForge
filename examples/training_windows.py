"""Generated candles as fixed-size windows for a neural network.

`to_numpy()` gives a (time, instrument, column) array. Windows of returns
(not price levels: every seed starts at the same prices) make the inputs,
and the regime at the window's end the label.
"""

import numpy as np

import marketforge as mf

WINDOW = 64

data = mf.generate(
    "BTCUSD,ETHUSD,SOLUSD",
    start="2024-01-01",
    days=30,
    seed=7,
    timeframes="m5",
    with_regime=True,
)
array, times, symbols = data.to_numpy("m5", columns=["close", "volume", "regime"])
log_close = np.log(array[:, :, 0])
returns = np.diff(log_close, axis=0)  # (time - 1, instrument)
volume = np.log1p(array[1:, :, 1])
regime = array[1:, 0, 2].astype(int)  # crypto shares one regime

x = np.stack([returns, volume], axis=-1).reshape(len(returns), -1)  # (time, features)
windows = np.lib.stride_tricks.sliding_window_view(x, WINDOW, axis=0).transpose(0, 2, 1)
labels = regime[WINDOW - 1 :]
print("inputs", windows.shape, "labels", labels.shape, "classes", np.bincount(labels))

try:
    import torch
    from torch.utils.data import DataLoader, TensorDataset
except ImportError:
    print("Install torch to wrap these arrays in a DataLoader.")
else:
    loader = DataLoader(
        TensorDataset(torch.from_numpy(windows.copy()).float(), torch.from_numpy(labels)),
        batch_size=256,
        shuffle=True,
    )
    batch, target = next(iter(loader))
    print("batch", tuple(batch.shape), tuple(target.shape))
