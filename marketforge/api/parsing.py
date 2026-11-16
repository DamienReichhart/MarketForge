# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the GNU Affero General Public License v3.0 or later.
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
from marketforge.domain.timeframes import Timeframe

TimeLike = int | float | str | dt.datetime | dt.date
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


def parse_seed(seed: int | None) -> int:
    """The seed to use: the given non-negative integer, or a random one when omitted."""
    if seed is None:
        return secrets.randbits(32)
    if isinstance(seed, bool) or not isinstance(seed, (int, np.integer)):
        raise TypeError(f"seed must be an integer, got {seed!r}")
    if seed < 0:
        raise ValueError(f"seed must be a non-negative integer, got {seed}")
    return int(seed)


def parse_timeframes(values: Names) -> list[Timeframe]:
    out: list[Timeframe] = []
    for v in as_names(values):
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
