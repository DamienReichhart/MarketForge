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

    def __len__(self) -> int:
        return int(self.timestamps.size)

    @classmethod
    def concat(cls, parts: list[Bars]) -> Bars:
        return cls(
            *(np.concatenate([getattr(p, f) for p in parts]) for f in cls.__dataclass_fields__)
        )
