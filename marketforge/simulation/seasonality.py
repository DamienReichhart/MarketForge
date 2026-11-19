# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

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

from functools import cache

import numpy as np

from marketforge.calendars.trading_calendar import TradingCalendar, get_calendar
from marketforge.domain.markets import MarketType
from marketforge.domain.time import REFERENCE_YEAR, SECONDS_PER_DAY

# FX sessions, each on its own local clock: (start, end, weight). Tokyo has no
# daylight saving; London and New York follow their own, so the sessions
# move against each other in UTC twice a year, as in reality.
_FX_BASE = 0.35
_FX_TOKYO = (9 * 60, 15 * 60, 0.45)  # Tokyo time (UTC+9)
_FX_LONDON = (8 * 60, 16 * 60 + 30, 0.8)  # London time
_FX_NEW_YORK = (8 * 60, 16 * 60, 0.7)  # New York time
_FX_EDGE = 20.0  # minutes over which a session ramps in and out
# Scheduled bursts: London open, US data at 08:30 New York, the 16:00 London fix.
_FX_LONDON_OPEN = 0.4
_FX_US_DATA = 0.5
_FX_FIX = 0.3
# Thinner edges of the week (New York time): Friday from noon, Sunday's open.
_FX_FRIDAY = 0.7
_FX_SUNDAY = 0.6
# Crypto diurnal cycle: amplitude, peak minute (UTC) and weekend factor.
_CRYPTO_AMPLITUDE = 0.3
_CRYPTO_PEAK = 900
_CRYPTO_WEEKEND = 0.75
# Perpetual futures settle funding at 00:00, 08:00 and 16:00 UTC: brief bursts.
_CRYPTO_FUNDING = 0.4
_CRYPTO_FUNDING_WIDTH = 4.0
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
                shape = _forex_shape(ts, self._calendar.local_minutes(ts))
            else:
                # Activity peaks around the US open (~15:00 UTC) and is roughly
                # half as volatile in the Asian night; weekends are quieter.
                weekday = ((ts // SECONDS_PER_DAY) + 3) % 7
                diurnal = 1.0 + _CRYPTO_AMPLITUDE * np.cos(
                    2 * np.pi * (minutes - _CRYPTO_PEAK) / 1440.0
                )
                to_funding = (minutes + 240) % 480 - 240  # minutes from 00/08/16 UTC
                funding = _CRYPTO_FUNDING * np.exp(-((to_funding / _CRYPTO_FUNDING_WIDTH) ** 2))
                shape = (diurnal + funding) * np.where(weekday >= 5, _CRYPTO_WEEKEND, 1.0)
        return np.asarray(np.maximum(shape, 1e-3), dtype=float)


def _session(local: np.ndarray, window: tuple[int, int, float]) -> np.ndarray:
    """Smooth activity of a session over local minutes-of-day: ramps in and out."""
    start, end, weight = window
    rise = 1.0 / (1.0 + np.exp(-(local - start) / (_FX_EDGE / 4)))
    fall = 1.0 / (1.0 + np.exp((local - end) / (_FX_EDGE / 4)))
    return np.asarray(weight * rise * fall)


def _burst(local: np.ndarray, at: int, decay: float) -> np.ndarray:
    """A burst at local minute ``at`` that fades over ``decay`` minutes."""
    since = local - at
    return np.asarray(np.where(since >= 0, np.exp(-since / decay), 0.0))


def london_minutes(timestamps: np.ndarray) -> np.ndarray:
    """London wall-clock minute of the day: UTC+1 from the last Sunday of March
    to the last Sunday of October (01:00 UTC), UTC otherwise."""
    ts = np.asarray(timestamps, dtype=np.int64)
    days = ts // SECONDS_PER_DAY
    years = days.astype("datetime64[D]").astype("datetime64[Y]").astype(np.int64) + 1970
    summer = np.zeros(ts.shape, dtype=bool)
    for year in np.unique(years):
        start, end = _last_sunday(int(year), 3), _last_sunday(int(year), 10)
        in_year = years == year
        summer[in_year] = (ts[in_year] >= start) & (ts[in_year] < end)
    return np.asarray(((ts // 60) + np.where(summer, 60, 0)) % 1440)


def _last_sunday(year: int, month: int) -> int:
    """Unix seconds of 01:00 UTC on the last Sunday of a month."""
    last = np.datetime64(f"{year}-{month + 1:02d}-01") - np.timedelta64(1, "D")
    weekday = (last.astype(np.int64) + 3) % 7  # Monday = 0
    sunday = last.astype(np.int64) - (weekday - 6) % 7
    return int(sunday * SECONDS_PER_DAY + 3600)


def _forex_shape(ts: np.ndarray, new_york_minutes: np.ndarray) -> np.ndarray:
    ny = new_york_minutes % 1440
    london = london_minutes(ts)
    tokyo = ((ts // 60) + 9 * 60) % 1440
    shape = (
        _FX_BASE
        + _session(tokyo, _FX_TOKYO)
        + _session(london, _FX_LONDON)
        + _session(ny, _FX_NEW_YORK)
        + _FX_LONDON_OPEN * _burst(london, _FX_LONDON[0], 30.0)
        + _FX_US_DATA * _burst(ny, 8 * 60 + 30, 10.0)
        + _FX_FIX * np.exp(-(((london - 16 * 60) / 5.0) ** 2))
    )
    # Thin markets at the edges of the week: Friday afternoon in New York, and
    # the first hours after the Sunday 17:00 open.
    weekday = ((new_york_minutes // 1440) + 3) % 7  # Monday = 0
    shape = shape * np.where((weekday == 4) & (ny >= 12 * 60), _FX_FRIDAY, 1.0)
    shape = shape * np.where((weekday == 6) & (ny < 20 * 60), _FX_SUNDAY, 1.0)
    return np.asarray(shape)


@cache
def get_seasonality(market: MarketType) -> SessionSeasonality:
    """Shared seasonality of a market (normalised once over a reference year)."""
    return SessionSeasonality(get_calendar(market))
