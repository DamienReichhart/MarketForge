# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the MIT License. See the LICENSE file in the project
# root for full license information.

"""
Streaming, calendar-aligned candle aggregation.

m1 candles arrive one simulated day at a time for every instrument of a
market. Each :class:`BarAggregator` turns them into candles of one timeframe
whose buckets are aligned to the market's bar anchor clock (daily candles at
00:00 UTC / 17:00 New York / the 09:30 open; weekly candles on Monday), keeps
the last, still-open bucket until more data arrives, and never publishes a
*partial candle*: one whose bucket contains an open minute outside the
requested range.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from marketforge.aggregation.timeframes import Timeframe
from marketforge.trading_calendar import MINUTES_PER_DAY, TradingCalendar

SUPPORTED_TIMEFRAMES = (
    Timeframe.m1,
    Timeframe.m5,
    Timeframe.m15,
    Timeframe.m30,
    Timeframe.H1,
    Timeframe.H4,
    Timeframe.D1,
    Timeframe.W1,
)


@dataclass
class Bars:
    """Candles of one timeframe for every instrument of a market."""

    timestamps: np.ndarray  # (k,) bucket start, UTC seconds
    open: np.ndarray  # (k, I)
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    volume: np.ndarray
    regime: np.ndarray  # (k,) regime at the candle's last minute

    def __len__(self) -> int:
        return int(self.timestamps.size)

    @classmethod
    def concat(cls, parts: list[Bars]) -> Bars:
        return cls(
            *(np.concatenate([getattr(p, f) for p in parts]) for f in cls.__dataclass_fields__)
        )


def bucket_keys(
    calendar: TradingCalendar, timeframe: Timeframe, timestamps: np.ndarray
) -> np.ndarray:
    """Integer bucket id of each timestamp on the market's bar anchor clock."""
    anchor = calendar.anchor_minutes(timestamps)
    if timeframe == Timeframe.W1:
        return np.asarray((anchor // MINUTES_PER_DAY + 3) // 7)  # Monday-based weeks
    if timeframe.minutes > MINUTES_PER_DAY or MINUTES_PER_DAY % timeframe.minutes:
        raise ValueError(f"Unsupported timeframe: {timeframe.name}")
    return np.asarray(anchor // timeframe.minutes)


def bucket_start_anchor(timeframe: Timeframe, key: np.ndarray) -> np.ndarray:
    """Anchor-clock minute at which each bucket starts."""
    if timeframe == Timeframe.W1:
        return np.asarray((key * 7 - 3) * MINUTES_PER_DAY)
    return np.asarray(key * timeframe.minutes)


class BarAggregator:
    """Aggregates a market's m1 stream into one timeframe."""

    def __init__(
        self, calendar: TradingCalendar, timeframe: Timeframe, start: int, end: int
    ) -> None:
        if timeframe not in SUPPORTED_TIMEFRAMES:
            raise ValueError(f"Unsupported timeframe: {timeframe.name}")
        self.calendar = calendar
        self.timeframe = timeframe
        self.start = int(start)
        self.end = int(end)
        self._carry: Bars | None = None
        self._first = True
        # One bucket can never span more than this (W1 plus slack).
        self._span = (8 if timeframe == Timeframe.W1 else 2) * 86400

    def push(self, minutes: Bars) -> Bars | None:
        """Add m1 candles; return the candles whose buckets are now complete."""
        data = minutes if self._carry is None else Bars.concat([self._carry, minutes])
        if len(data) == 0:
            return None
        keys = bucket_keys(self.calendar, self.timeframe, data.timestamps)
        last_start = int(np.searchsorted(keys, keys[-1], side="left"))
        self._carry = _slice(data, slice(last_start, None))
        if last_start == 0:
            return None
        return self._emit(_slice(data, slice(0, last_start)), keys[:last_start])

    def finish(self) -> Bars | None:
        """Flush the last bucket if the requested range covers all of it."""
        if self._carry is None or len(self._carry) == 0:
            return None
        data, self._carry = self._carry, None
        keys = bucket_keys(self.calendar, self.timeframe, data.timestamps)
        after = self.calendar.open_minutes(self.end, self.end + self._span)
        if after.size and np.any(bucket_keys(self.calendar, self.timeframe, after) == keys[-1]):
            return self._emit(data, keys, drop_last=True)
        return self._emit(data, keys)

    def _emit(self, data: Bars, keys: np.ndarray, drop_last: bool = False) -> Bars | None:
        starts = np.r_[0, np.nonzero(np.diff(keys))[0] + 1]
        ends = np.r_[starts[1:], keys.size]
        if self._first:
            self._first = False
            before = self.calendar.open_minutes(self.start - self._span, self.start)
            if before.size and np.any(
                bucket_keys(self.calendar, self.timeframe, before) == keys[0]
            ):
                starts, ends = starts[1:], ends[1:]
        if drop_last and starts.size:
            starts, ends = starts[:-1], ends[:-1]
        if starts.size == 0:
            return None
        bucket = keys[starts]
        first_ts = data.timestamps[starts]
        offset = self.calendar.anchor_minutes(first_ts) - bucket_start_anchor(
            self.timeframe, bucket
        )
        # Restrict to the kept buckets so reduceat's last segment stops at its end.
        kept = slice(int(starts[0]), int(ends[-1]))
        seg = starts - starts[0]
        return Bars(
            timestamps=first_ts - offset * 60,
            open=data.open[starts],
            high=np.maximum.reduceat(data.high[kept], seg, axis=0),
            low=np.minimum.reduceat(data.low[kept], seg, axis=0),
            close=data.close[ends - 1],
            volume=np.add.reduceat(data.volume[kept], seg, axis=0),
            regime=data.regime[ends - 1],
        )


def _slice(b: Bars, s: slice) -> Bars:
    return Bars(
        b.timestamps[s], b.open[s], b.high[s], b.low[s], b.close[s], b.volume[s], b.regime[s]
    )
