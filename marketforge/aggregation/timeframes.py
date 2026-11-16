# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the MIT License. See the LICENSE file in the project
# root for full license information.

"""Supported candle timeframes."""

from __future__ import annotations

from enum import Enum


class Timeframe(Enum):
    """Candle timeframes, valued in minutes."""

    m1 = 1
    m5 = 5
    m15 = 15
    m30 = 30
    H1 = 60
    H4 = 240
    D1 = 1440
    W1 = 10080

    @property
    def minutes(self) -> int:
        return int(self.value)

    @classmethod
    def from_string(cls, s: str) -> "Timeframe":
        """Parse a timeframe name such as ``m5``, ``H1`` or ``D1``."""
        try:
            return cls[s]
        except KeyError:
            raise ValueError(f"Unknown timeframe {s!r}; valid: {[t.name for t in cls]}") from None
