# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the MIT License. See the LICENSE file in the project
# root for full license information.

"""Resolving what the user asked for into a generation request."""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from typing import Any

from marketforge.api.parsing import (
    Names,
    TimeLike,
    as_names,
    parse_anomalies,
    parse_markets,
    parse_seed,
    parse_time,
    parse_timeframes,
)
from marketforge.config.loader import load_catalog
from marketforge.config.overrides import Overrides, resolve_overrides
from marketforge.domain.anomalies import AnomalyType
from marketforge.domain.markets import MarketType
from marketforge.domain.time import SECONDS_PER_DAY
from marketforge.domain.timeframes import Timeframe
from marketforge.simulation.spec import MarketSpec, build_market_spec

DEFAULT_TIMEFRAMES = ("m1", "m5", "m15", "m30", "H1", "H4", "D1", "W1")


# A candle that is still open when a dataset ends started less than this many
# UTC days before the dataset's last day (the longest candle is a week), so an
# extension that resumes this far back rebuilds every open candle from its
# first minute.
RESUME_DAYS = 8


@dataclass
class Checkpoint:
    """Where the simulation of one market can be resumed to extend a dataset."""

    day: int  # UTC day to resume from
    state: dict[str, Any]  # the simulator's snapshot at the start of that day
    written: dict[str, int]  # timeframe -> start of the last candle already published


@dataclass
class MarketPlan:
    """What to simulate for one market and which instruments to output."""

    spec: MarketSpec
    selected: list[str]
    resume: Checkpoint | None = None

    @property
    def market(self) -> MarketType:
        return self.spec.market


@dataclass
class Request:
    """A fully resolved generation request."""

    plans: list[MarketPlan]
    start: int
    end: int
    seed: int
    timeframes: list[Timeframe]
    include_regime: bool = False
    anomalies: frozenset[AnomalyType] = frozenset()
    overrides: dict[str, dict[str, Any]] = field(default_factory=dict)
    extends_from: int | None = None  # the end of the dataset this request extends

    @property
    def first_day(self) -> int:
        """The first UTC day to simulate: the start, or where an extension resumes."""
        resumed = [plan.resume.day for plan in self.plans if plan.resume is not None]
        return min(resumed) if resumed else self.start // SECONDS_PER_DAY

    @property
    def last_day(self) -> int:
        return (self.end - 1) // SECONDS_PER_DAY

    @property
    def n_days(self) -> int:
        return self.last_day - self.first_day + 1


def plan_request(
    instruments: Names | None = None,
    markets: Names | None = None,
    *,
    start: TimeLike,
    end: TimeLike,
    seed: int | None = None,
    timeframes: Names = DEFAULT_TIMEFRAMES,
    anomalies: Names = (),
    include_regime: bool = False,
    overrides: Overrides | None = None,
) -> Request:
    """
    Resolve user input into a :class:`Request`.

    With ``instruments`` only, their markets are inferred; with ``markets`` only,
    every instrument of those markets is produced; with both, only the listed
    instruments that belong to the listed markets are produced. With neither, all
    markets are produced.

    Names (instruments, markets, timeframes, anomalies) may be given as a list or
    as one comma-separated string, in any letter case.

    Raises:
        ValueError: on unknown instruments or markets, an empty selection, or an
            invalid time range.
        TypeError: on a seed that is not an integer.
    """
    t0, t1 = parse_time(start), parse_time(end)
    if t0 >= t1:
        raise ValueError(f"start ({t0}) must be before end ({t1})")
    seed = parse_seed(seed)
    tfs = parse_timeframes(timeframes)
    anomaly_types = parse_anomalies(anomalies)
    resolved = resolve_overrides(overrides)
    catalog = load_catalog(resolved)

    wanted_markets = parse_markets(markets)
    symbol_market = {s: m for m, cfg in catalog.items() for s in cfg.symbols}
    by_market: dict[MarketType, list[str]] = {}
    requested = [a.upper() for a in as_names(instruments)]
    if requested:
        unknown = [a for a in requested if a not in symbol_market]
        if unknown:
            raise ValueError(_unknown_instruments(unknown, list(symbol_market)))
        for a in requested:
            m = symbol_market[a]
            if wanted_markets is None or m in wanted_markets:
                by_market.setdefault(m, []).append(a)
        if not by_market:
            raise ValueError("None of the requested instruments belong to the requested markets")
    else:
        for m in wanted_markets or list(MarketType):
            by_market[m] = list(catalog[m].symbols)

    plans = [
        MarketPlan(build_market_spec(catalog[m], anomaly_types), selected)
        for m, selected in by_market.items()
    ]
    return Request(plans, t0, t1, seed, tfs, include_regime, anomaly_types, resolved)


def _unknown_instruments(unknown: list[str], known: list[str]) -> str:
    """Error text naming the unknown instruments and, where one is close, what was meant."""
    parts = []
    for symbol in unknown:
        close = difflib.get_close_matches(symbol, known, n=1, cutoff=0.7)
        parts.append(f"{symbol} (did you mean {close[0]}?)" if close else symbol)
    return f"Unknown instrument(s): {', '.join(parts)}. Run 'marketforge list-instruments'."
