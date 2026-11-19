# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

"""Candles of a coarser timeframe from m1 candles, aligned as MarketForge aligns them."""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from marketforge._warnings import PACKAGE_DIRS
from marketforge.aggregation.streaming import BarAggregator, bucket_keys
from marketforge.api.memory import time_index
from marketforge.api.parsing import parse_timeframes
from marketforge.calendars.trading_calendar import TradingCalendar, get_calendar
from marketforge.domain.bars import Bars
from marketforge.domain.markets import MarketType
from marketforge.domain.regimes import RegimeType
from marketforge.domain.timeframes import Timeframe

_PRICES = ("open", "high", "low", "close", "volume")


def resample(frame: pd.DataFrame, timeframe: str, market: str | MarketType) -> pd.DataFrame:
    """
    Aggregate m1 candles into ``timeframe`` exactly as MarketForge would have.

    Buckets follow the market's anchor clock (forex days start at 17:00 New
    York, stock days at the 09:30 open, weeks on Monday), which a plain
    ``DataFrame.resample`` gets wrong, and a candle whose bucket is not fully
    covered by ``frame`` is dropped, never published partial: at the edges,
    and around open minutes missing inside the frame (with a warning). Open
    is the first open, high the max, low the min, close the last close,
    volume the sum, spread the mean and regime the last; ``bid`` and ``ask``
    quote the new close around the new mean spread, as generated candles do.

    Args:
        frame: m1 candles with a UTC ``DatetimeIndex`` and at least
            open/high/low/close/volume (a frame from :func:`generate` or
            :func:`read`, or your own).
        timeframe: Any timeframe MarketForge generates (``m3``, ``H4``, ``D1``, ...).
        market: Whose calendar and anchors to use.

    Raises:
        ValueError: if the candles are not m1, not in time order, or fall in
            minutes when ``market`` is closed (the wrong market).
    """
    tf = parse_timeframes(timeframe)[0]
    market_type = MarketType(str(market).lower())
    calendar = get_calendar(market_type)
    if frame.empty:
        return frame.copy()
    times = pd.DatetimeIndex(frame.index)
    stamps = np.asarray(
        times.as_unit("s").asi8
        if times.tz is not None
        else times.tz_localize("UTC").as_unit("s").asi8,
        dtype=np.int64,
    )
    _check_minutes(stamps, market_type)
    has_regime = "regime" in frame.columns
    has_quotes = "bid" in frame.columns and "ask" in frame.columns
    has_spread = "spread" in frame.columns
    simulates_spread = has_spread or has_quotes

    def column(name: str) -> np.ndarray:
        return np.ascontiguousarray(frame[name].to_numpy(dtype=float)[:, None])

    regime = (
        frame["regime"].astype(pd.CategoricalDtype([r.value for r in RegimeType])).cat.codes
        if has_regime
        else pd.Series(np.zeros(len(frame), dtype=np.int8))
    )
    bars = Bars(
        timestamps=np.asarray(stamps, dtype=np.int64),
        open=column("open"),
        high=column("high"),
        low=column("low"),
        close=column("close"),
        volume=column("volume"),
        regime=regime.to_numpy(dtype=np.int8),
        spread=(
            column("spread")
            if has_spread
            else np.ascontiguousarray((frame["ask"] - frame["bid"]).to_numpy(dtype=float)[:, None])
            if has_quotes
            else None
        ),
    )
    aggregator = BarAggregator(calendar, tf, int(stamps[0]), int(stamps[-1]) + 60)
    parts = [b for b in (aggregator.push(bars), aggregator.finish()) if b is not None and len(b)]
    columns = [
        *_PRICES,
        *(["spread"] if has_spread else []),
        *(["bid", "ask"] if has_quotes else []),
        *(["regime"] if has_regime else []),
    ]
    if not parts:
        return pd.DataFrame(columns=columns, index=pd.DatetimeIndex([], tz="UTC", name="time"))
    out = parts[0] if len(parts) == 1 else Bars.concat(parts)
    out = _without_gapped_buckets(out, stamps, calendar, tf)
    result = pd.DataFrame(
        {
            name: getattr(out, name)[:, 0]
            for name in (*_PRICES, *(["spread"] if simulates_spread else []))
        },
        index=time_index(out.timestamps),
    )
    if has_quotes:
        result["bid"] = result["close"] - result["spread"] / 2
        result["ask"] = result["close"] + result["spread"] / 2
    if has_regime:
        result["regime"] = pd.Categorical.from_codes(
            out.regime.astype(int), categories=[r.value for r in RegimeType]
        )
    return result[columns]


def _check_minutes(stamps: np.ndarray, market: MarketType) -> None:
    steps = np.diff(stamps)
    if steps.size and steps.min() <= 0:
        raise ValueError("resample needs candles in time order, each minute once")
    if steps.size and steps.min() != 60:
        raise ValueError(
            f"resample needs m1 candles; these are {steps.min() / 60:g} minutes apart. "
            "Resample the m1 candles instead"
        )
    closed = ~get_calendar(market).open_mask(stamps)
    if closed.any():
        first = pd.Timestamp(int(stamps[np.argmax(closed)]), unit="s", tz="UTC")
        raise ValueError(
            f"{int(closed.sum())} candle(s) fall in minutes when {market.value} is closed "
            f"(the first at {first:%Y-%m-%d %H:%M} UTC): are these {market.value} candles?"
        )


def _without_gapped_buckets(
    out: Bars, stamps: np.ndarray, calendar: TradingCalendar, tf: Timeframe
) -> Bars:
    """Drop the candles whose bucket misses an open minute inside the frame."""
    expected = calendar.open_minutes(int(stamps[0]), int(stamps[-1]) + 60)
    if expected.size == stamps.size:
        return out
    missing = np.setdiff1d(expected, stamps, assume_unique=True)
    gapped = np.isin(bucket_keys(calendar, tf, out.timestamps), bucket_keys(calendar, tf, missing))
    if gapped.any():
        warnings.warn(
            f"The m1 candles miss {missing.size} open minute(s); the {int(gapped.sum())} "
            f"{tf.name} candle(s) they fall in are dropped rather than published partial",
            skip_file_prefixes=PACKAGE_DIRS,
        )
    return Bars(
        timestamps=out.timestamps[~gapped],
        open=out.open[~gapped],
        high=out.high[~gapped],
        low=out.low[~gapped],
        close=out.close[~gapped],
        volume=out.volume[~gapped],
        regime=out.regime[~gapped],
        spread=None if out.spread is None else out.spread[~gapped],
    )
