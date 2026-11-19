# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

"""
Trading calendars: which minutes each market is open, and where its bars start.

- Crypto trades every minute; bars are anchored to 00:00 UTC.
- Forex trades from Sunday 17:00 to Friday 17:00 New York time (DST-aware);
  daily bars start at 17:00 New York, the industry "New York close".
- Stocks trade the NYSE regular session, 09:30-16:00 New York time (13:00 on
  early-close days), on NYSE trading days; daily bars start at the open.

All daylight-saving transitions happen on Sunday at 02:00 New York, when both
New York-anchored markets are closed, so a single UTC offset per UTC day is
exact for every minute those markets are open.
"""

from __future__ import annotations

import datetime as dt
from functools import cache
from zoneinfo import ZoneInfo

import numpy as np

from marketforge.calendars.nyse import (
    NYSE_CLOSE,
    NYSE_EARLY_CLOSE,
    NYSE_OPEN,
    nyse_early_closes,
    nyse_holidays,
)
from marketforge.domain.markets import MarketType
from marketforge.domain.time import MINUTES_PER_DAY, SECONDS_PER_DAY

NEW_YORK = ZoneInfo("America/New_York")
_UTC = dt.UTC
_EPOCH = dt.date(1970, 1, 1)

# Forex week boundary (New York minutes-of-day).
FX_ROLLOVER = 17 * 60


def _epoch_day(d: dt.date) -> int:
    return (d - _EPOCH).days


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
            self.timezone: ZoneInfo | None = None
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
        lo, hi = int(days.min()), int(days.max())
        if hi - lo <= ts.size:
            # Typical case (a day or a few of minutes): direct lookup, no sort.
            table = np.array(
                [self.utc_offset_minutes(d) for d in range(lo, hi + 1)], dtype=np.int64
            )
            return np.asarray(minutes + table[days - lo])
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


@cache
def get_calendar(market: MarketType) -> TradingCalendar:
    """Shared calendar instance for a market."""
    return TradingCalendar(MarketType(market))
