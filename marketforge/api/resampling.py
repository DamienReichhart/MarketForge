# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

"""Candles of a coarser timeframe from m1 candles, aligned as MarketForge aligns them."""

from __future__ import annotations

import numpy as np
import pandas as pd

from marketforge.aggregation.streaming import BarAggregator
from marketforge.api.parsing import parse_timeframes
from marketforge.calendars.trading_calendar import get_calendar
from marketforge.domain.bars import Bars
from marketforge.domain.markets import MarketType
from marketforge.domain.regimes import RegimeType

_PRICES = ("open", "high", "low", "close", "volume")


def resample(frame: pd.DataFrame, timeframe: str, market: str | MarketType) -> pd.DataFrame:
    """
    Aggregate m1 candles into ``timeframe`` exactly as MarketForge would have.

    Buckets follow the market's anchor clock (forex days start at 17:00 New
    York, stock days at the 09:30 open, weeks on Monday), which a plain
    ``DataFrame.resample`` gets wrong, and a candle whose bucket is not fully
    covered by ``frame`` is dropped, never published partial. Open is the
    first open, high the max, low the min, close the last close, volume the
    sum, spread the mean and regime the last.

    Args:
        frame: m1 candles with a UTC ``DatetimeIndex`` and at least
            open/high/low/close/volume (a frame from :func:`generate` or
            :func:`read`, or your own).
        timeframe: Any timeframe MarketForge generates (``m3``, ``H4``, ``D1``, ...).
        market: Whose calendar and anchors to use.
    """
    tf = parse_timeframes(timeframe)[0]
    calendar = get_calendar(MarketType(str(market).lower()))
    if frame.empty:
        return frame.copy()
    times = pd.DatetimeIndex(frame.index)
    stamps = (
        times.as_unit("s").asi8
        if times.tz is not None
        else times.tz_localize("UTC").as_unit("s").asi8
    )
    has_regime = "regime" in frame.columns
    has_spread = "spread" in frame.columns

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
        spread=column("spread") if has_spread else None,
    )
    aggregator = BarAggregator(calendar, tf, int(stamps[0]), int(stamps[-1]) + 60)
    parts = [b for b in (aggregator.push(bars), aggregator.finish()) if b is not None and len(b)]
    columns = [*_PRICES, *(["spread"] if has_spread else []), *(["regime"] if has_regime else [])]
    if not parts:
        return pd.DataFrame(columns=columns, index=pd.DatetimeIndex([], tz="UTC", name="time"))
    out = parts[0] if len(parts) == 1 else Bars.concat(parts)
    result = pd.DataFrame(
        {
            name: getattr(out, name)[:, 0]
            for name in (*_PRICES, *(["spread"] if has_spread else []))
        },
        index=pd.DatetimeIndex(pd.to_datetime(out.timestamps, unit="s", utc=True), name="time"),
    )
    if has_regime:
        result["regime"] = pd.Categorical.from_codes(
            out.regime.astype(int), categories=[r.value for r in RegimeType]
        )
    return result[columns]
