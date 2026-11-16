# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the MIT License. See the LICENSE file in the project
# root for full license information.
"""
Deterministic intraday and weekly volatility seasonality.

Real markets concentrate volatility at specific times (equity open/close,
FX session overlaps) and quieter periods (lunch, weekends for crypto). This
module produces a strictly-positive multiplicative factor s(t) applied to the
per-minute conditional volatility (and reused by the volume model).

The factor is variance-neutralized over the generated window (mean(s²) == 1)
so it reshapes *when* volatility occurs without changing the asset's overall
configured volatility level.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from marketforge.config.settings import MarketType

if TYPE_CHECKING:
    from marketforge.trading_calendar import TradingCalendar

SECONDS_PER_DAY = 86400

# US cash session in UTC minutes-of-day (EST baseline ~14:30–21:00).
_STOCK_OPEN_MIN = 870
_STOCK_CLOSE_MIN = 1260

# FX session windows (UTC minutes-of-day).
_FX_LONDON = (420, 960)        # 07:00–16:00
_FX_NY_OVERLAP = (780, 960)    # 13:00–16:00
_FX_ASIAN = (0, 420)           # 00:00–07:00


class SeasonalityModel:
    """Per-market deterministic volatility seasonality factor."""

    def __init__(self, market_type: MarketType) -> None:
        self._market_type = market_type

    def multiplier_series(self, timestamps: np.ndarray) -> np.ndarray:
        """
        Return a positive, variance-neutral seasonality factor per timestamp.

        Args:
            timestamps: int64 Unix seconds, shape (n,).

        Returns:
            float array shape (n,) with mean(s²) == 1 over the window.
        """
        minutes = (timestamps % SECONDS_PER_DAY) // 60  # minute-of-day [0,1440)
        # day-of-week with Monday=0 (1970-01-01 was a Thursday => +3)
        dow = ((timestamps // SECONDS_PER_DAY) + 3) % 7

        if self._market_type == MarketType.STOCKS:
            shape = self._stock_shape(minutes)
        elif self._market_type == MarketType.FOREX:
            shape = self._forex_shape(minutes, dow)
        else:
            shape = self._crypto_shape(minutes, dow)

        shape = np.maximum(shape, 1e-3)
        # variance-neutralize over the window
        norm = np.sqrt(np.mean(shape ** 2))
        return np.asarray(shape / norm)

    @staticmethod
    def _stock_shape(minutes: np.ndarray) -> np.ndarray:
        in_session = (minutes >= _STOCK_OPEN_MIN) & (minutes <= _STOCK_CLOSE_MIN)
        base = np.where(in_session, 1.0, 0.45)
        open_bump = 0.9 * np.exp(-((minutes - _STOCK_OPEN_MIN) / 25.0) ** 2)
        close_bump = 0.7 * np.exp(-((minutes - _STOCK_CLOSE_MIN) / 25.0) ** 2)
        return base + open_bump + close_bump

    @staticmethod
    def _forex_shape(minutes: np.ndarray, dow: np.ndarray) -> np.ndarray:
        s = np.full(minutes.shape, 0.7)
        london = (minutes >= _FX_LONDON[0]) & (minutes < _FX_LONDON[1])
        overlap = (minutes >= _FX_NY_OVERLAP[0]) & (minutes < _FX_NY_OVERLAP[1])
        asian = (minutes >= _FX_ASIAN[0]) & (minutes < _FX_ASIAN[1])
        s[london] = 1.2
        s[overlap] = 1.5
        s[asian] = 0.8
        s = np.where(dow >= 5, s * 0.3, s)
        return s

    @staticmethod
    def _crypto_shape(minutes: np.ndarray, dow: np.ndarray) -> np.ndarray:
        diurnal = 1.0 + 0.12 * np.sin((minutes / 1440.0) * 2 * np.pi - 1.0)
        weekend = np.where(dow >= 5, 0.82, 1.0)
        return diurnal * weekend


# Reference window used to normalise session seasonality: a full calendar
# year, so the scale never depends on the requested range or chunking.
_REFERENCE_START = 1672531200  # 2023-01-01T00:00:00Z
_REFERENCE_END = 1704067200    # 2024-01-01T00:00:00Z


class SessionSeasonality:
    """
    Calendar-aware intraday volatility seasonality.

    Unlike :class:`SeasonalityModel`, which normalised over whatever window it
    was given, this model is normalised once over a fixed reference year of
    *open* minutes, so mean(s^2) == 1 across a typical year and the factor at a
    given minute never depends on the requested range.

    - Stocks: U-shape keyed to the New York session (open and close bumps,
      lunch lull), honouring early closes.
    - Forex: Asian / London / London-New York overlap activity (UTC).
    - Crypto: mild diurnal cycle and quieter weekends (UTC).
    """

    def __init__(self, calendar: TradingCalendar) -> None:
        self._calendar = calendar
        ref = calendar.open_minutes(_REFERENCE_START, _REFERENCE_END)
        raw = self._raw(ref)
        self._norm = float(np.sqrt(np.mean(raw ** 2)))
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
            since_open = mod - 570
            to_close = close - 1 - mod
            shape = (
                1.0
                + 0.9 * np.exp(-((since_open / 25.0) ** 2))
                + 0.7 * np.exp(-((to_close / 25.0) ** 2))
                - 0.2 * np.exp(-(((mod - 750) / 60.0) ** 2))
            )
        else:
            minutes = (ts % SECONDS_PER_DAY) // 60
            dow = ((ts // SECONDS_PER_DAY) + 3) % 7
            if market == MarketType.FOREX:
                shape = SeasonalityModel._forex_shape(minutes, np.zeros_like(dow))
            else:
                shape = SeasonalityModel._crypto_shape(minutes, dow)
        return np.asarray(np.maximum(shape, 1e-3), dtype=float)
