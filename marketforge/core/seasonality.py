# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the MIT License. See the LICENSE file in the project
# root for full license information.

"""
Intraday volatility seasonality.

Real markets concentrate activity at specific times: the equity open and
close, FX session overlaps, weekday crypto hours. :class:`SessionSeasonality`
returns a positive factor s(t) that scales each open minute's volatility (and,
through its log, volume). It is normalised once over a fixed reference year of
open minutes, so mean(s^2) == 1 over a typical year and the factor at a given
minute never depends on the requested range.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from marketforge.domain.markets import MarketType
from marketforge.domain.time import REFERENCE_YEAR, SECONDS_PER_DAY

if TYPE_CHECKING:
    from marketforge.trading_calendar import TradingCalendar

# FX activity windows (UTC minutes-of-day).
_FX_ASIAN = (0, 420)  # 00:00-07:00
_FX_LONDON = (420, 960)  # 07:00-16:00
_FX_NY_OVERLAP = (780, 960)  # 13:00-16:00
# Crypto diurnal cycle: amplitude, peak minute (UTC) and weekend factor.
_CRYPTO_AMPLITUDE = 0.3
_CRYPTO_PEAK = 900
_CRYPTO_WEEKEND = 0.75
# NYSE session landmarks (New York minutes-of-day).
_NY_OPEN = 570
_NY_LUNCH = 750


class SessionSeasonality:
    """
    Calendar-aware intraday volatility seasonality for one market.

    - Stocks: U-shape over the New York session (open and close bumps, lunch
      lull), honouring early closes.
    - Forex: Asian / London / London-New York overlap activity (UTC).
    - Crypto: diurnal cycle peaking near the US open and quieter weekends (UTC).
    """

    def __init__(self, calendar: TradingCalendar) -> None:
        self._calendar = calendar
        ref = calendar.open_minutes(*REFERENCE_YEAR)
        raw = self._raw(ref)
        self._norm = float(np.sqrt(np.mean(raw**2)))
        self._log_var = float(np.var(np.log(raw / self._norm)))

    @property
    def log_variance(self) -> float:
        """Variance of log s(t) over the reference year (for lognormal corrections)."""
        return self._log_var

    def factor(self, timestamps: np.ndarray) -> np.ndarray:
        """Seasonality multiplier s(t) for open-minute timestamps."""
        return np.asarray(self._raw(np.asarray(timestamps, dtype=np.int64)) / self._norm)

    def _raw(self, ts: np.ndarray) -> np.ndarray:
        market = self._calendar.market
        if market == MarketType.STOCKS:
            local = self._calendar.local_minutes(ts)
            mod = local % 1440
            close = self._calendar.session_close_minute(local // 1440)
            since_open = mod - _NY_OPEN
            to_close = close - 1 - mod
            shape = (
                1.0
                + 0.9 * np.exp(-((since_open / 25.0) ** 2))
                + 0.7 * np.exp(-((to_close / 25.0) ** 2))
                - 0.2 * np.exp(-(((mod - _NY_LUNCH) / 60.0) ** 2))
            )
        else:
            minutes = (ts % SECONDS_PER_DAY) // 60
            if market == MarketType.FOREX:
                shape = np.full(minutes.shape, 0.7)
                shape[(minutes >= _FX_ASIAN[0]) & (minutes < _FX_ASIAN[1])] = 0.8
                shape[(minutes >= _FX_LONDON[0]) & (minutes < _FX_LONDON[1])] = 1.2
                shape[(minutes >= _FX_NY_OVERLAP[0]) & (minutes < _FX_NY_OVERLAP[1])] = 1.5
            else:
                # Activity peaks around the US open (~15:00 UTC) and is roughly
                # half as volatile in the Asian night; weekends are quieter.
                weekday = ((ts // SECONDS_PER_DAY) + 3) % 7
                diurnal = 1.0 + _CRYPTO_AMPLITUDE * np.cos(
                    2 * np.pi * (minutes - _CRYPTO_PEAK) / 1440.0
                )
                shape = diurnal * np.where(weekday >= 5, _CRYPTO_WEEKEND, 1.0)
        return np.asarray(np.maximum(shape, 1e-3), dtype=float)
