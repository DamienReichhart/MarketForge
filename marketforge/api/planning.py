# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the MIT License. See the LICENSE file in the project
# root for full license information.

"""Resolving what the user asked for into a generation request."""

from __future__ import annotations

import secrets
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from marketforge.api.parsing import TimeLike, parse_anomalies, parse_time, parse_timeframes
from marketforge.config.loader import load_catalog
from marketforge.domain.markets import MarketType
from marketforge.domain.time import SECONDS_PER_DAY
from marketforge.domain.timeframes import Timeframe
from marketforge.simulation.spec import MarketSpec, build_market_spec

DEFAULT_TIMEFRAMES = ("m1", "m5", "m15", "m30", "H1", "H4", "D1", "W1")


@dataclass
class MarketPlan:
    """What to simulate for one market and which instruments to output."""

    spec: MarketSpec
    selected: list[str]

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

    @property
    def n_days(self) -> int:
        return (self.end - 1) // SECONDS_PER_DAY - self.start // SECONDS_PER_DAY + 1


def plan_request(
    assets: Sequence[str] | None = None,
    markets: Sequence[str | MarketType] | None = None,
    *,
    start: TimeLike,
    end: TimeLike,
    seed: int | None = None,
    timeframes: Sequence[str] = DEFAULT_TIMEFRAMES,
    anomalies: Sequence[str] = (),
    include_regime: bool = False,
    overrides: str | Path | None = None,
) -> Request:
    """
    Resolve user input into a :class:`Request`.

    With ``assets`` only, their markets are inferred; with ``markets`` only,
    every instrument of those markets is produced; with both, only the listed
    assets that belong to the listed markets are produced. With neither, all
    markets are produced.

    Raises:
        ValueError: on unknown assets or markets, an empty selection, or an
            invalid time range.
    """
    t0, t1 = parse_time(start), parse_time(end)
    if t0 >= t1:
        raise ValueError(f"start ({t0}) must be before end ({t1})")
    if seed is None:
        seed = secrets.randbits(32)
    if seed < 0:
        raise ValueError(f"seed must be a non-negative integer, got {seed}")
    tfs = parse_timeframes(timeframes)
    anomaly_types = parse_anomalies(anomalies)
    catalog = load_catalog(overrides)

    wanted_markets = (
        [m if isinstance(m, MarketType) else MarketType(str(m).strip().lower()) for m in markets]
        if markets
        else None
    )
    symbol_market = {s: m for m, cfg in catalog.items() for s in cfg.symbols}
    by_market: dict[MarketType, list[str]] = {}
    if assets:
        requested = list(dict.fromkeys(a.strip().upper() for a in assets if a.strip()))
        unknown = [a for a in requested if a not in symbol_market]
        if unknown:
            raise ValueError(
                f"Unknown instrument(s): {', '.join(unknown)}. Run 'marketforge list-assets'."
            )
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
    return Request(plans, t0, t1, int(seed), tfs, include_regime)
