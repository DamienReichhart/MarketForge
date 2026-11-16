# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the GNU Affero General Public License v3.0 or later.
# See the LICENSE file in the project root for full license information.

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

import numpy as np

from marketforge.calendars.trading_calendar import TradingCalendar
from marketforge.domain.bars import Bars
from marketforge.domain.time import MINUTES_PER_DAY
from marketforge.domain.timeframes import Timeframe

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


def bucket_keys(
    calendar: TradingCalendar,
    timeframe: Timeframe,
    timestamps: np.ndarray,
    anchor: np.ndarray | None = None,
) -> np.ndarray:
    """
    Integer bucket id of each timestamp on the market's bar anchor clock.

    ``anchor`` may pass ``calendar.anchor_minutes(timestamps)`` when it is
    already known (it is the same for every timeframe).
    """
    if anchor is None:
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
    """
    Aggregates a market's m1 stream into one timeframe.

    The still-open last bucket is kept as a list of chunks and copied once,
    when it completes: re-concatenating it on every push made weekly bars
    cost O(week) per simulated day. Every bucket is reduced over exactly the
    same rows as a one-shot aggregation, so output is bit-identical.
    """

    def __init__(
        self, calendar: TradingCalendar, timeframe: Timeframe, start: int, end: int
    ) -> None:
        if timeframe not in SUPPORTED_TIMEFRAMES:
            raise ValueError(f"Unsupported timeframe: {timeframe.name}")
        self.calendar = calendar
        self.timeframe = timeframe
        self.start = int(start)
        self.end = int(end)
        self._carry: list[Bars] = []  # rows of the last, still-open bucket
        self._carry_key = 0
        self._first = True
        # One bucket can never span more than this (W1 plus slack).
        self._span = (8 if timeframe == Timeframe.W1 else 2) * 86400

    def push(self, minutes: Bars, anchor: np.ndarray | None = None) -> Bars | None:
        """
        Add m1 candles; return the candles whose buckets are now complete.

        ``anchor`` optionally passes ``calendar.anchor_minutes(minutes.timestamps)``
        so that several timeframes of one market compute it only once.
        """
        if len(minutes) == 0:
            return None
        if self.timeframe == Timeframe.m1:
            # A one-minute bucket is complete as soon as it arrives.
            return minutes
        keys = bucket_keys(self.calendar, self.timeframe, minutes.timestamps, anchor)
        last_key = int(keys[-1])
        if self._carry and last_key == self._carry_key:
            self._carry.append(minutes)  # still inside the open bucket
            return None
        last_start = int(np.searchsorted(keys, last_key, side="left"))
        pieces: list[tuple[Bars, np.ndarray]] = []
        if self._carry:
            # The open bucket ends at the first row with another key.
            split = int(np.searchsorted(keys, self._carry_key, side="right"))
            rows = Bars.concat([*self._carry, minutes.rows(slice(0, split))])
            pieces.append((rows, np.full(len(rows), self._carry_key, dtype=keys.dtype)))
        else:
            split = 0
        if last_start > split:
            pieces.append((minutes.rows(slice(split, last_start)), keys[split:last_start]))
        self._carry = [minutes.rows(slice(last_start, None))]
        self._carry_key = last_key
        return self._emit(pieces) if pieces else None

    def finish(self) -> Bars | None:
        """Flush the last bucket if the requested range covers all of it."""
        if self.timeframe == Timeframe.m1 or not self._carry:
            return None
        data = self._carry[0] if len(self._carry) == 1 else Bars.concat(self._carry)
        self._carry = []
        keys = np.full(len(data), self._carry_key, dtype=np.int64)
        after = self.calendar.open_minutes(self.end, self.end + self._span)
        if after.size and np.any(
            bucket_keys(self.calendar, self.timeframe, after) == self._carry_key
        ):
            return self._emit([(data, keys)], drop_last=True)
        return self._emit([(data, keys)])

    def _emit(self, pieces: list[tuple[Bars, np.ndarray]], drop_last: bool = False) -> Bars | None:
        """Reduce complete buckets; no bucket spans two pieces."""
        parts = [self._reduce(data, keys) for data, keys in pieces]
        out = parts[0][0] if len(parts) == 1 else Bars.concat([b for b, _ in parts])
        first_key = parts[0][1]
        n = len(out)
        lo, hi = 0, n
        if self._first:
            self._first = False
            before = self.calendar.open_minutes(self.start - self._span, self.start)
            if before.size and np.any(
                bucket_keys(self.calendar, self.timeframe, before) == first_key
            ):
                lo = 1  # the first bucket started before the requested range
        if drop_last:
            hi = n - 1
        if hi <= lo:
            return None
        return out if (lo, hi) == (0, n) else out.rows(slice(lo, hi))

    def _reduce(self, data: Bars, keys: np.ndarray) -> tuple[Bars, int]:
        """One candle per bucket of contiguous rows; returns it and the first key."""
        starts = np.flatnonzero(keys[1:] != keys[:-1]) + 1
        starts = np.concatenate((np.zeros(1, dtype=starts.dtype), starts))
        ends = np.append(starts[1:], keys.size)
        bucket = keys[starts]
        first_ts = data.timestamps[starts]
        offset = self.calendar.anchor_minutes(first_ts) - bucket_start_anchor(
            self.timeframe, bucket
        )
        bars = Bars(
            timestamps=first_ts - offset * 60,
            open=data.open[starts],
            high=np.maximum.reduceat(data.high, starts, axis=0),
            low=np.minimum.reduceat(data.low, starts, axis=0),
            close=data.close[ends - 1],
            volume=np.add.reduceat(data.volume, starts, axis=0),
            regime=data.regime[ends - 1],
            spread=(
                None
                if data.spread is None
                else np.add.reduceat(data.spread, starts, axis=0) / (ends - starts)[:, None]
            ),
        )
        return bars, int(bucket[0])
