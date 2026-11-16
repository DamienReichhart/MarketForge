# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the MIT License. See the LICENSE file in the project
# root for full license information.

"""Turning user input (times, timeframe names, anomaly names) into domain values."""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable

import numpy as np

from marketforge.aggregation.streaming import SUPPORTED_TIMEFRAMES
from marketforge.domain.anomalies import AnomalyType
from marketforge.domain.timeframes import Timeframe

TimeLike = int | float | str | dt.datetime | dt.date


def parse_time(value: TimeLike) -> int:
    """
    Convert a time to Unix seconds (UTC).

    Accepts Unix seconds (int, float or digit string), ISO 8601 dates or
    datetimes ("2024-01-01", "2024-01-01T09:30", "2024-01-01T09:30-05:00"),
    and ``date`` / ``datetime`` objects. Naive values are taken as UTC.
    """
    if isinstance(value, bool):
        raise TypeError("time must not be a bool")
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, float):
        return int(value)
    if isinstance(value, dt.datetime):
        moment = value
    elif isinstance(value, dt.date):
        moment = dt.datetime(value.year, value.month, value.day, tzinfo=dt.UTC)
    elif isinstance(value, str):
        text = value.strip()
        if text.lstrip("-").isdigit():
            return int(text)
        try:
            moment = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError(
                f"Cannot parse time {value!r}: use Unix seconds or ISO 8601 "
                "like 2024-01-01 or 2024-01-01T09:30"
            ) from None
    else:
        raise TypeError(f"Unsupported time value: {value!r}")
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=dt.UTC)
    return int(moment.timestamp())


def parse_timeframes(values: Iterable[str]) -> list[Timeframe]:
    out: list[Timeframe] = []
    for v in values:
        tf = Timeframe.from_string(v.strip())
        if tf not in SUPPORTED_TIMEFRAMES:
            raise ValueError(
                f"Unsupported timeframe {v!r}; choose from {[t.name for t in SUPPORTED_TIMEFRAMES]}"
            )
        if tf not in out:
            out.append(tf)
    if not out:
        raise ValueError("At least one timeframe is required")
    return out


def parse_anomalies(values: Iterable[str]) -> frozenset[AnomalyType]:
    out = set()
    for v in values:
        try:
            out.add(AnomalyType(v.strip().lower()))
        except ValueError:
            raise ValueError(f"Unknown anomaly {v!r}; choose from spikes, flash_crash") from None
    return frozenset(out)
