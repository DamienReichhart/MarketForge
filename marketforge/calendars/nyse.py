# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the MIT License. See the LICENSE file in the project
# root for full license information.

"""
NYSE regular session and holiday rules.

The holiday rules are the current ones, applied to every year. One-off
closures (9/11, Hurricane Sandy, national days of mourning) are not modelled.
"""

from __future__ import annotations

import datetime as dt
from functools import cache

# Regular session, in New York minutes-of-day.
NYSE_OPEN = 9 * 60 + 30
NYSE_CLOSE = 16 * 60
NYSE_EARLY_CLOSE = 13 * 60


def _easter(year: int) -> dt.date:
    """Gregorian Easter Sunday (anonymous Gregorian algorithm)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    month, day = divmod(h + l_ - 7 * m + 114, 31)
    return dt.date(year, month, day + 1)


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> dt.date:
    """n-th (1-based) `weekday` (Mon=0) of a month; n=-1 means the last one."""
    if n > 0:
        first = dt.date(year, month, 1)
        offset = (weekday - first.weekday()) % 7
        return first + dt.timedelta(days=offset + 7 * (n - 1))
    nxt = dt.date(year + (month == 12), month % 12 + 1, 1)
    last = nxt - dt.timedelta(days=1)
    return last - dt.timedelta(days=(last.weekday() - weekday) % 7)


def _observed(d: dt.date, saturday_to_friday: bool = True) -> dt.date | None:
    """NYSE observance: Sunday holidays move to Monday, Saturday ones to Friday."""
    if d.weekday() == 6:
        return d + dt.timedelta(days=1)
    if d.weekday() == 5:
        return d - dt.timedelta(days=1) if saturday_to_friday else None
    return d


@cache
def nyse_holidays(year: int) -> frozenset[dt.date]:
    """Full-day NYSE closures for a year under the current holiday rules."""
    days: list[dt.date | None] = [
        # New Year's Day: a Saturday holiday is not moved to Friday Dec 31.
        _observed(dt.date(year, 1, 1), saturday_to_friday=False),
        _nth_weekday(year, 2, 0, 3),  # Washington's Birthday
        _easter(year) - dt.timedelta(days=2),  # Good Friday
        _nth_weekday(year, 5, 0, -1),  # Memorial Day
        _observed(dt.date(year, 7, 4)),  # Independence Day
        _nth_weekday(year, 9, 0, 1),  # Labor Day
        _nth_weekday(year, 11, 3, 4),  # Thanksgiving
        _observed(dt.date(year, 12, 25)),  # Christmas
    ]
    if year >= 1998:
        days.append(_nth_weekday(year, 1, 0, 3))  # Martin Luther King Jr. Day
    if year >= 2022:
        days.append(_observed(dt.date(year, 6, 19)))  # Juneteenth
    return frozenset(d for d in days if d is not None)


@cache
def nyse_early_closes(year: int) -> frozenset[dt.date]:
    """NYSE 13:00 early closes: July 3, the day after Thanksgiving, Christmas Eve."""
    candidates = [
        dt.date(year, 7, 3),
        _nth_weekday(year, 11, 3, 4) + dt.timedelta(days=1),
        dt.date(year, 12, 24),
    ]
    holidays = nyse_holidays(year)
    return frozenset(d for d in candidates if d.weekday() < 5 and d not in holidays)
