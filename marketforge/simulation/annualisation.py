# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the GNU Affero General Public License v3.0 or later.
# See the LICENSE file in the project root for full license information.

"""Conversion between annual parameters and open minutes, closures included."""

from __future__ import annotations

from functools import cache

import numpy as np

from marketforge.calendars.trading_calendar import get_calendar
from marketforge.config.defaults import MarketDefaults
from marketforge.domain.markets import MarketType
from marketforge.domain.time import REFERENCE_YEAR


def closure_variance(minutes: np.ndarray, defaults: MarketDefaults) -> np.ndarray:
    m = np.asarray(minutes, dtype=float)
    return np.asarray(
        defaults.closure_variance_scale * np.power(m, defaults.closure_variance_exponent)
    )


@cache
def effective_minutes_per_year(market: MarketType, scale: float, exponent: float) -> float:
    """Open minutes per year plus closure variance, in open-minute units."""
    cal = get_calendar(market)
    ts = cal.open_minutes(*REFERENCE_YEAR)
    closed = np.diff(ts) // 60 - 1
    closed = closed[closed > 0]
    gap_var = (
        float(np.sum(scale * np.power(closed.astype(float), exponent))) if closed.size else 0.0
    )
    return float(ts.size) + gap_var
