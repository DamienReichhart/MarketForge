# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

"""
Earnings events: a stock's quarterly results, released while its market is closed.

Every stock reports four times a year, after the close of a trading day in
the fourth to sixth week of each quarter, on a day of its own that does not
depend on the seed (as real companies keep their calendar). The next session
opens with a jump whose size the seed draws, about 2.5 days of the stock's
volatility, heavy-tailed, and its volatility (and so its volume) is raised
for a few days after.
"""

from __future__ import annotations

import datetime as dt
import zlib
from functools import lru_cache

import numpy as np

from marketforge.calendars.trading_calendar import TradingCalendar

# A report's jump, in days of the stock's volatility (one standard deviation).
EARNINGS_MOVE_DAYS = 2.5
# Student-t degrees of freedom of the jump: a few reports move a stock 3-4x more.
EARNINGS_NU = 4.0
# Volatility after a report: doubled on the first session, back within a week.
BOOST = 1.0
BOOST_DAYS = 2.0
BOOST_HORIZON = 10  # calendar days after which the boost is gone
_QUARTER_MONTHS = (1, 4, 7, 10)
REPORTS_PER_YEAR = len(_QUARTER_MONTHS)
_FIRST_DAY = 21  # days into the quarter of the earliest report
_SPREAD_DAYS = 21  # reports spread over three weeks


@lru_cache(maxsize=4096)
def earnings_days(symbol: str, year: int, calendar: TradingCalendar) -> tuple[int, ...]:
    """The local epoch days (New York) after whose close ``symbol`` reports in ``year``."""
    offset = _FIRST_DAY + zlib.crc32(symbol.encode()) % _SPREAD_DAYS
    days = []
    for month in _QUARTER_MONTHS:
        day = (dt.date(year, month, 1) - dt.date(1970, 1, 1)).days + offset
        while calendar.session_close_minute(np.array([day]))[0] == 0:  # the next trading day
            day += 1
        days.append(day)
    return tuple(days)


def reports_between(
    symbol: str, first_day: int, last_day: int, calendar: TradingCalendar
) -> list[int]:
    """The report days of ``symbol`` in ``[first_day, last_day]`` (local epoch days)."""
    lo = (dt.date(1970, 1, 1) + dt.timedelta(days=first_day)).year
    hi = (dt.date(1970, 1, 1) + dt.timedelta(days=last_day)).year
    return [
        d
        for year in range(lo, hi + 1)
        for d in earnings_days(symbol, year, calendar)
        if first_day <= d <= last_day
    ]


def boost_variance_days() -> float:
    """Extra variance a report's volatility boost adds, in trading days of the stock's variance."""
    days = np.arange(BOOST_HORIZON + 1)
    return float(np.sum(volatility_boost(days) ** 2 - 1.0) * 5.0 / 7.0)  # trading days only


def diffusion_scale(volatility: float, move: float) -> float:
    """The share of a stock's volatility left to its diffusion once its reports have theirs.

    The catalog's volatility is the stock's total: four jumps of ``move``
    (log, one standard deviation) a year and the boosts after them included,
    so the diffusion's variance s^2 vol^2 solves
    s^2 vol^2 (1 + 4 B / 252) + 4 move^2 = vol^2. Never below half.
    """
    if move <= 0.0 or volatility <= 0.0:
        return 1.0
    share = (1.0 - REPORTS_PER_YEAR * move**2 / volatility**2) / (
        1.0 + REPORTS_PER_YEAR * boost_variance_days() / 252.0
    )
    return float(np.sqrt(max(share, 0.25)))


def volatility_boost(days_since_open: np.ndarray) -> np.ndarray:
    """Volatility multiplier ``days_since_open`` calendar days after a report's first session."""
    d = np.asarray(days_since_open, dtype=float)
    boost = 1.0 + BOOST * np.exp(-d / BOOST_DAYS)
    return np.asarray(np.where((d >= 0) & (d <= BOOST_HORIZON), boost, 1.0))
