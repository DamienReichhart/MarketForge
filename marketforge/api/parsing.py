# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

"""Turning user input (times, names of timeframes, markets and anomalies, seeds) into domain values."""

from __future__ import annotations

import datetime as dt
import secrets
from collections.abc import Iterable

import numpy as np

from marketforge.aggregation.streaming import SUPPORTED_TIMEFRAMES
from marketforge.domain.anomalies import AnomalyType
from marketforge.domain.markets import MarketType
from marketforge.domain.timeframes import STANDARD_TIMEFRAMES, Timeframe
from marketforge.output.formats import OutputFormat, TimestampFormat

TimeLike = int | float | str | dt.datetime | dt.date
# Unix seconds past this (the year 5138) are milliseconds or microseconds
# taken for seconds: crypto exchanges export milliseconds.
_LARGEST_SECONDS = 100_000_000_000
# One name, several names separated by commas, or any iterable of names.
Names = str | Iterable[str]


def as_names(value: Names | None) -> list[str]:
    """The non-empty names of ``value``, stripped, in order and without duplicates."""
    if value is None:
        return []
    parts = value.split(",") if isinstance(value, str) else [str(v) for v in value]
    return list(dict.fromkeys(name for part in parts if (name := part.strip())))


def parse_time(value: TimeLike) -> int:
    """
    Convert a time to Unix seconds (UTC).

    Accepts Unix seconds (int, float or digit string), ISO 8601 dates or
    datetimes ("2024-01-01", "2024-01-01T09:30", "2024-01-01T09:30-05:00"),
    and ``date`` / ``datetime`` objects. Naive values are taken as UTC.

    Raises:
        ValueError: on a number too large to be Unix seconds, such as Unix
            milliseconds; nothing is converted silently.
    """
    if isinstance(value, bool):
        raise TypeError("time must not be a bool")
    if isinstance(value, (int, np.integer, float)):
        return _seconds(value)
    if isinstance(value, dt.datetime):
        moment = value
    elif isinstance(value, dt.date):
        moment = dt.datetime(value.year, value.month, value.day, tzinfo=dt.UTC)
    elif isinstance(value, str):
        text = value.strip()
        if text.lstrip("-").isdigit():
            return _seconds(int(text))
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


def _seconds(value: float) -> int:
    if abs(value) >= _LARGEST_SECONDS:
        unit, divisor = ("milliseconds", 1000) if abs(value) < 1e14 else ("microseconds", 10**6)
        raise ValueError(
            f"Time {value} is not Unix seconds (it would be after the year 5000); it looks "
            f"like Unix {unit}: divide it by {divisor:,}"
        )
    return int(value)


def parse_seed(seed: int | None) -> int:
    """The seed to use: the given non-negative integer, or a random one when omitted."""
    if seed is None:
        return secrets.randbits(32)
    if isinstance(seed, bool) or not isinstance(seed, (int, np.integer)):
        raise TypeError(f"seed must be an integer, got {seed!r}")
    if seed < 0:
        raise ValueError(f"seed must be a non-negative integer, got {seed}")
    return int(seed)


def parse_timeframes(values: Names | None) -> list[Timeframe]:
    """The timeframes named: the standard eight when ``None``, all of them for ``all``."""
    if values is None:
        return list(STANDARD_TIMEFRAMES)
    out: list[Timeframe] = []
    for v in as_names(values):
        if v.lower() == "all":
            return list(SUPPORTED_TIMEFRAMES)
        tf = Timeframe.from_string(v)
        if tf not in SUPPORTED_TIMEFRAMES:
            raise ValueError(
                f"Unsupported timeframe {v!r}; choose from "
                f"{', '.join(t.name for t in SUPPORTED_TIMEFRAMES)}"
            )
        if tf not in out:
            out.append(tf)
    if not out:
        raise ValueError("At least one timeframe is required")
    return out


def parse_markets(values: Names | None) -> list[MarketType] | None:
    """The requested markets, or None for every market (nothing given, or ``all``)."""
    out: list[MarketType] = []
    for name in as_names(values):
        if name.lower() == "all":
            return None
        try:
            market = MarketType(name.lower())
        except ValueError:
            raise ValueError(
                f"Unknown market {name!r}; choose from "
                f"{', '.join(m.value for m in MarketType)} or all"
            ) from None
        if market not in out:
            out.append(market)
    return out or None


def parse_anomalies(values: Names) -> frozenset[AnomalyType]:
    out = set()
    for v in as_names(values):
        try:
            out.add(AnomalyType(v.lower()))
        except ValueError:
            raise ValueError(
                f"Unknown anomaly {v!r}; choose from {', '.join(a.value for a in AnomalyType)}"
            ) from None
    return frozenset(out)


def parse_format(value: str | OutputFormat) -> OutputFormat:
    """A file format by name, in any letter case."""
    try:
        return OutputFormat(str(value).strip().lower())
    except ValueError:
        raise ValueError(
            f"Unknown format {value!r}; choose from {', '.join(f.value for f in OutputFormat)}"
        ) from None


def parse_timestamps(value: str | TimestampFormat) -> TimestampFormat:
    """A way of writing time by name, in any letter case."""
    try:
        return TimestampFormat(str(value).strip().lower())
    except ValueError:
        raise ValueError(
            f"Unknown timestamps {value!r}; choose from "
            f"{', '.join(f.value for f in TimestampFormat)}"
        ) from None


def range_end(start: int, end: TimeLike | None, days: int | None) -> int:
    """The end of a range given as exactly one of ``end`` and ``days`` (from ``start``)."""
    if (end is None) == (days is None):
        raise ValueError("Give exactly one of end and days")
    if days is not None:
        if isinstance(days, bool) or not isinstance(days, int | np.integer) or days < 1:
            raise ValueError(f"days must be a positive integer, got {days!r}")
        return start + int(days) * 86_400
    assert end is not None
    return parse_time(end)
