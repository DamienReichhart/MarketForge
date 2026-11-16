# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the GNU Affero General Public License v3.0 or later.
# See the LICENSE file in the project root for full license information.

"""Candles."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class Bars:
    """Candles of one timeframe for every instrument of a market."""

    timestamps: np.ndarray  # (k,) bucket start, UTC seconds
    open: np.ndarray  # (k, I)
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    volume: np.ndarray
    regime: np.ndarray  # (k,) regime at the candle's last minute
    spread: np.ndarray | None = None  # (k, I) mean quoted spread, when simulated

    def __len__(self) -> int:
        return int(self.timestamps.size)

    def rows(self, s: slice) -> Bars:
        """The candles of a slice of rows."""
        return Bars(
            self.timestamps[s],
            self.open[s],
            self.high[s],
            self.low[s],
            self.close[s],
            self.volume[s],
            self.regime[s],
            None if self.spread is None else self.spread[s],
        )

    def after(self, timestamp: int) -> Bars:
        """The candles that start after ``timestamp``."""
        k = int(np.searchsorted(self.timestamps, timestamp, side="right"))
        return self if k == 0 else self.rows(slice(k, None))

    @classmethod
    def concat(cls, parts: list[Bars]) -> Bars:
        def joined(name: str) -> np.ndarray:
            return np.concatenate([getattr(p, name) for p in parts])

        return cls(
            joined("timestamps"),
            joined("open"),
            joined("high"),
            joined("low"),
            joined("close"),
            joined("volume"),
            joined("regime"),
            None if parts[0].spread is None else joined("spread"),
        )
