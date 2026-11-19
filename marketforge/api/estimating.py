# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

"""What a generation would produce and cost, without running it."""

from __future__ import annotations

from dataclasses import dataclass, field

from marketforge.api.parsing import Names, TimeLike, parse_format
from marketforge.api.planning import MarketPlan, Request, plan_request
from marketforge.api.renamed import renamed_arguments
from marketforge.calendars.trading_calendar import get_calendar
from marketforge.config.overrides import Overrides
from marketforge.domain.markets import MarketType
from marketforge.domain.timeframes import Timeframe
from marketforge.output.formats import OutputFormat

# Cost model (one core, measured on 3.1). Random draws are market-wide and
# fixed-shape: 1440 x (factors + 3 x instruments) per simulated day, whatever
# is selected. The rest of the simulation runs only for the selected
# instruments' open minutes.
_DRAW_SECONDS = 7e-9
_INSTRUMENT_MINUTE_SECONDS = 35e-9
_MARKET_DAY_SECONDS = 1e-3  # per-day bookkeeping (calendar, aggregation, buffers)
_ROW_SECONDS = {"csv": 0.75e-6, "parquet": 0.6e-6, "feather": 0.5e-6, "memory": 0.2e-6}
# Bytes per written row (timestamp, OHLCV), and for the spread column.
_ROW_BYTES = {"csv": 68, "parquet": 33, "feather": 45}
_SPREAD_BYTES = {"csv": 11, "parquet": 6, "feather": 7}
_QUOTE_BYTES = {"csv": 15, "parquet": 8, "feather": 9}  # each of bid and ask


@dataclass(frozen=True)
class Estimate:
    """What a request would produce.

    Attributes:
        files: Output files (one per instrument and timeframe).
        rows: Candles across all of them.
        disk_bytes: Approximate size on disk in the requested format.
        memory_bytes: Approximate peak memory of :func:`generate` (in memory).
        seconds: Approximate time on one core.
        open_minutes: Open minutes of each market in the range.
    """

    files: int
    rows: int
    disk_bytes: int
    memory_bytes: int
    seconds: float
    open_minutes: dict[str, int] = field(default_factory=dict)
    _market_seconds: tuple[float, ...] = ()

    def wall_seconds(self, jobs: int = 1) -> float:
        """Approximate elapsed time with ``jobs`` markets simulated in parallel."""
        if jobs <= 1 or len(self._market_seconds) <= 1:
            return self.seconds
        shared = self.seconds - sum(self._market_seconds)
        return shared + max(max(self._market_seconds), sum(self._market_seconds) / jobs)


@renamed_arguments
def estimate(
    instruments: Names | None = None,
    *,
    start: TimeLike,
    end: TimeLike | None = None,
    days: int | None = None,
    markets: Names | None = None,
    seed: int | None = None,
    timeframes: Names | None = None,
    anomalies: Names = (),
    with_regime: bool = False,
    with_spread: bool = False,
    with_bid_ask: bool = False,
    overrides: Overrides | None = None,
    format: str | OutputFormat = OutputFormat.CSV,
) -> Estimate:
    """
    Estimate the files, rows, size and time of a generation, without running it.

    Takes the arguments of :func:`generate_to_disk` (``format`` sets the size
    per row); ``memory_bytes`` is what :func:`generate` would need instead,
    and :meth:`Estimate.wall_seconds` the time with markets in parallel.
    """
    request = plan_request(
        instruments,
        markets,
        start=start,
        end=end,
        days=days,
        seed=seed if seed is not None else 0,
        timeframes=timeframes,
        anomalies=anomalies,
        include_regime=with_regime,
        include_spread=with_spread,
        include_bid_ask=with_bid_ask,
        overrides=overrides,
    )
    return estimate_request(request, parse_format(format).value)


def estimate_request(request: Request, fmt: str) -> Estimate:
    """Estimate an already planned request (also the CLI's ``--dry-run``)."""
    since = request.start if request.extends_from is None else request.extends_from
    rows = 0
    market_seconds = []
    open_minutes: dict[str, int] = {}
    for plan in request.plans:
        minutes = get_calendar(plan.market).count_open_minutes(since, request.end)
        open_minutes[plan.market.value] = minutes
        per_instrument = sum(_candles(plan.market, minutes, tf) for tf in request.timeframes)
        rows += per_instrument * len(plan.selected)
        market_seconds.append(_simulation_seconds(plan, request.n_days, minutes))
    columns = 6 + request.include_spread + 2 * request.include_bid_ask + request.include_regime
    row_bytes = (
        _ROW_BYTES[fmt]
        + request.include_spread * _SPREAD_BYTES[fmt]
        + 2 * request.include_bid_ask * _QUOTE_BYTES[fmt]
    )
    return Estimate(
        files=sum(len(p.selected) for p in request.plans) * len(request.timeframes),
        rows=rows,
        disk_bytes=rows * row_bytes,
        # Chunks, then one block of float64 columns, then the frames over it.
        memory_bytes=rows * columns * 8 * 2,
        seconds=sum(market_seconds) + rows * _ROW_SECONDS[fmt],
        open_minutes=open_minutes,
        _market_seconds=tuple(market_seconds),
    )


# Open minutes in a market's day, and trading days in its week, for D1 and W1.
_SESSION_MINUTES = {MarketType.CRYPTO: 1440, MarketType.FOREX: 1440, MarketType.STOCKS: 390}
_WEEK_DAYS = {MarketType.CRYPTO: 7, MarketType.FOREX: 5, MarketType.STOCKS: 5}


def _candles(market: MarketType, open_minutes: int, tf: Timeframe) -> int:
    """Candles of one instrument and timeframe over ``open_minutes`` of its market."""
    if tf.minutes < 1440:
        return open_minutes // tf.minutes
    days = open_minutes / _SESSION_MINUTES[market]
    return round(days if tf == Timeframe.D1 else days / _WEEK_DAYS[market])


def _simulation_seconds(plan: MarketPlan, n_days: int, open_minutes: int) -> float:
    structure = plan.spec.structure
    draws = 1440 * (len(structure.factors) + 3 * len(structure.instruments))
    return n_days * (draws * _DRAW_SECONDS + _MARKET_DAY_SECONDS) + (
        open_minutes * len(plan.selected) * _INSTRUMENT_MINUTE_SECONDS
    )
