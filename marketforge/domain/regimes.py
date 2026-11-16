# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the GNU Affero General Public License v3.0 or later.
# See the LICENSE file in the project root for full license information.

"""Market regimes."""

from __future__ import annotations

from enum import StrEnum


class RegimeType(StrEnum):
    """Market-wide regimes, in the order used by regime parameters and labels."""

    TREND_UP = "trend_up"
    TREND_DOWN = "trend_down"
    RANGE = "range"
    HIGH_VOLATILITY = "high_volatility"
    CRASH = "crash"
