# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the MIT License. See the LICENSE file in the project
# root for full license information.

"""
Trading calendars: which minutes each market is open, and where its bars start.

- Crypto trades every minute; bars are anchored to 00:00 UTC.
- Forex trades from Sunday 17:00 to Friday 17:00 New York time (DST-aware);
  daily bars start at 17:00 New York, the industry "New York close".
- Stocks trade the NYSE regular session, 09:30-16:00 New York time (13:00 on
  early-close days), on NYSE trading days; daily bars start at the open.

The NYSE holiday rules are the current ones, applied to every year. One-off
closures (9/11, Hurricane Sandy, national days of mourning) are not modelled.

All daylight-saving transitions happen on Sunday at 02:00 New York, when both
New York-anchored markets are closed, so a single UTC offset per UTC day is
exact for every minute those markets are open.
"""

from __future__ import annotations

import datetime as dt
from functools import lru_cache
from typing import Optional
from zoneinfo import ZoneInfo

import numpy as np

from marketforge.config.settings import MarketType

MINUTES_PER_DAY = 1440
SECONDS_PER_DAY = 86400
NEW_YORK = ZoneInfo("America/New_York")
_UTC = dt.timezone.utc
_EPOCH = dt.date(1970, 1, 1)

# NYSE regular session, in New York minutes-of-day.
NYSE_OPEN = 9 * 60 + 30
NYSE_CLOSE = 16 * 60
NYSE_EARLY_CLOSE = 13 * 60
# Forex week boundary (New York minutes-of-day).
FX_ROLLOVER = 17 * 60


def _epoch_day(d: dt.date) -> int:
    return (d - _EPOCH).days


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


def _observed(d: dt.date, saturday_to_friday: bool = True) -> Optional[dt.date]:
    """NYSE observance: Sunday holidays move to Monday, Saturday ones to Friday."""
    if d.weekday() == 6:
        return d + dt.timedelta(days=1)
    if d.weekday() == 5:
        return d - dt.timedelta(days=1) if saturday_to_friday else None
    return d


@lru_cache(maxsize=None)
def nyse_holidays(year: int) -> frozenset[dt.date]:
    """Full-day NYSE closures for a year under the current holiday rules."""
    days: list[Optional[dt.date]] = [
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


@lru_cache(maxsize=None)
def nyse_early_closes(year: int) -> frozenset[dt.date]:
    """NYSE 13:00 early closes: July 3, the day after Thanksgiving, Christmas Eve."""
    candidates = [
        dt.date(year, 7, 3),
        _nth_weekday(year, 11, 3, 4) + dt.timedelta(days=1),
        dt.date(year, 12, 24),
    ]
    holidays = nyse_holidays(year)
    return frozenset(d for d in candidates if d.weekday() < 5 and d not in holidays)


class TradingCalendar:
    """
    Open/closed status per minute and bar anchoring for one market.

    Attributes:
        market: The market this calendar describes.
        timezone: Zone whose wall clock defines sessions and bar anchors.
        anchor_shift: Minutes added to local wall-clock time so that daily bars
            start at local midnight of the *shifted* clock (forex: +420 puts
            17:00 New York at midnight; stocks: -570 puts 09:30 at midnight).
    """

    def __init__(self, market: MarketType) -> None:
        self.market = market
        if market == MarketType.CRYPTO:
            self.timezone: Optional[ZoneInfo] = None
            self.anchor_shift = 0
        elif market == MarketType.FOREX:
            self.timezone = NEW_YORK
            self.anchor_shift = MINUTES_PER_DAY - FX_ROLLOVER
        elif market == MarketType.STOCKS:
            self.timezone = NEW_YORK
            self.anchor_shift = -NYSE_OPEN
        else:  # pragma: no cover - exhaustive enum
            raise ValueError(f"Unknown market: {market}")
        self._offset_cache: dict[int, int] = {}

    # ------------------------------------------------------------------ time
    def utc_offset_minutes(self, utc_day: int) -> int:
        """Offset (local - UTC) in minutes, valid for every open minute of a UTC day."""
        if self.timezone is None:
            return 0
        off = self._offset_cache.get(utc_day)
        if off is None:
            noon = dt.datetime.fromtimestamp(utc_day * SECONDS_PER_DAY + 43200, tz=_UTC)
            delta = noon.astimezone(self.timezone).utcoffset()
            off = int(delta.total_seconds() // 60) if delta is not None else 0
            self._offset_cache[utc_day] = off
        return off

    def local_minutes(self, timestamps: np.ndarray) -> np.ndarray:
        """Local wall-clock minutes since the epoch for each UTC timestamp."""
        ts = np.asarray(timestamps, dtype=np.int64)
        minutes = ts // 60
        if self.timezone is None or ts.size == 0:
            return minutes
        days = ts // SECONDS_PER_DAY
        uniq, inv = np.unique(days, return_inverse=True)
        offsets = np.array([self.utc_offset_minutes(int(d)) for d in uniq], dtype=np.int64)
        return np.asarray(minutes + offsets[inv])

    def anchor_minutes(self, timestamps: np.ndarray) -> np.ndarray:
        """Minutes on the bar-anchored clock: daily bars start at its midnight."""
        return self.local_minutes(timestamps) + self.anchor_shift

    # --------------------------------------------------------------- opening
    def open_mask(self, timestamps: np.ndarray) -> np.ndarray:
        """Boolean mask: True where the minute starting at the timestamp is open."""
        ts = np.asarray(timestamps, dtype=np.int64)
        if self.market == MarketType.CRYPTO:
            return np.ones(ts.shape, dtype=bool)
        local = self.local_minutes(ts)
        day = local // MINUTES_PER_DAY
        mod = local % MINUTES_PER_DAY
        weekday = (day + 3) % 7  # epoch day 0 was a Thursday; Monday == 0
        if self.market == MarketType.FOREX:
            return np.asarray(
                (weekday <= 3)
                | ((weekday == 4) & (mod < FX_ROLLOVER))
                | ((weekday == 6) & (mod >= FX_ROLLOVER))
            )
        close = self.session_close_minute(day)
        return np.asarray((mod >= NYSE_OPEN) & (mod < close))

    def session_close_minute(self, local_days: np.ndarray) -> np.ndarray:
        """
        NYSE close (local minute-of-day) for each local epoch day; 0 when closed all day.
        """
        days = np.asarray(local_days, dtype=np.int64)
        close = np.full(days.shape, NYSE_CLOSE, dtype=np.int64)
        if days.size == 0:
            return close
        weekday = (days + 3) % 7
        close[weekday >= 5] = 0
        lo = (_EPOCH + dt.timedelta(days=int(days.min()))).year
        hi = (_EPOCH + dt.timedelta(days=int(days.max()))).year
        hol = [_epoch_day(d) for y in range(lo, hi + 1) for d in nyse_holidays(y)]
        early = [_epoch_day(d) for y in range(lo, hi + 1) for d in nyse_early_closes(y)]
        close[np.isin(days, early)] = NYSE_EARLY_CLOSE
        close[np.isin(days, hol)] = 0
        return close

    def open_minutes(self, start: int, end: int) -> np.ndarray:
        """Timestamps (UTC seconds, minute-aligned) of open minutes in [start, end)."""
        first = -(-int(start) // 60) * 60
        ts = np.arange(first, int(end), 60, dtype=np.int64)
        return np.asarray(ts[self.open_mask(ts)])

    def count_open_minutes(self, start: int, end: int, chunk_days: int = 366) -> int:
        """Number of open minutes in [start, end), computed in bounded memory."""
        total = 0
        step = chunk_days * SECONDS_PER_DAY
        for lo in range(int(start), int(end), step):
            total += int(self.open_minutes(lo, min(lo + step, int(end))).size)
        return total


@lru_cache(maxsize=None)
def get_calendar(market: MarketType) -> TradingCalendar:
    """Shared calendar instance for a market."""
    return TradingCalendar(MarketType(market))
