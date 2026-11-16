# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the MIT License. See the LICENSE file in the project
# root for full license information.

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
            *(None if (v := getattr(self, f)) is None else v[s] for f in self.__dataclass_fields__)
        )

    def after(self, timestamp: int) -> Bars:
        """The candles that start after ``timestamp``."""
        k = int(np.searchsorted(self.timestamps, timestamp, side="right"))
        return self if k == 0 else self.rows(slice(k, None))

    @classmethod
    def concat(cls, parts: list[Bars]) -> Bars:
        return cls(
            *(
                None
                if getattr(parts[0], f) is None
                else np.concatenate([getattr(p, f) for p in parts])
                for f in cls.__dataclass_fields__
            )
        )
