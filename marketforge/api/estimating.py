# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

"""What a generation would produce and cost, without running it."""

from __future__ import annotations

from dataclasses import dataclass, field

from marketforge.api.parsing import Names, TimeLike
from marketforge.api.planning import DEFAULT_TIMEFRAMES, MarketPlan, Request, plan_request
from marketforge.calendars.trading_calendar import get_calendar
from marketforge.config.overrides import Overrides
from marketforge.output.formats import OutputFormat

# Cost model (one core, measured on 3.1). Random draws are market-wide and
# fixed-shape: 1440 x (factors + 3 x instruments) per simulated day, whatever
# is selected. The rest of the simulation runs only for the selected
# instruments' open minutes.
_DRAW_SECONDS = 7e-9
_INSTRUMENT_MINUTE_SECONDS = 35e-9
_MARKET_DAY_SECONDS = 1e-3  # per-day bookkeeping (calendar, aggregation, buffers)
_ROW_SECONDS = {"csv": 0.75e-6, "parquet": 0.6e-6, "memory": 0.2e-6}
# Bytes per written row (timestamp, OHLCV), and for the spread column.
_ROW_BYTES = {"csv": 68, "parquet": 33}
_SPREAD_BYTES = {"csv": 11, "parquet": 6}


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


def estimate(
    instruments: Names | None = None,
    *,
    start: TimeLike,
    end: TimeLike | None = None,
    days: int | None = None,
    markets: Names | None = None,
    timeframes: Names = DEFAULT_TIMEFRAMES,
    include_regime: bool = False,
    include_spread: bool = False,
    overrides: Overrides | None = None,
    fmt: str | OutputFormat = OutputFormat.CSV,
    seed: int | None = None,
) -> Estimate:
    """
    Estimate the files, rows, size and time of a generation, without running it.

    Takes the arguments of :func:`generate_to_disk` (``fmt`` sets the size per
    row); ``memory_bytes`` is what :func:`generate` would need instead. The
    timeframes default to all eight, as on disk.
    """
    request = plan_request(
        instruments,
        markets,
        start=start,
        end=end,
        days=days,
        seed=seed if seed is not None else 0,
        timeframes=timeframes,
        include_regime=include_regime,
        include_spread=include_spread,
        overrides=overrides,
    )
    return estimate_request(request, OutputFormat(fmt).value)


def estimate_request(request: Request, fmt: str) -> Estimate:
    """Estimate an already planned request (also the CLI's ``--dry-run``)."""
    since = request.start if request.extends_from is None else request.extends_from
    rows = 0
    market_seconds = []
    open_minutes: dict[str, int] = {}
    for plan in request.plans:
        minutes = get_calendar(plan.market).count_open_minutes(since, request.end)
        open_minutes[plan.market.value] = minutes
        per_instrument = sum(minutes // max(1, min(tf.minutes, 1440)) for tf in request.timeframes)
        rows += per_instrument * len(plan.selected)
        market_seconds.append(_simulation_seconds(plan, request.n_days, minutes))
    columns = 6 + request.include_spread + request.include_regime
    row_bytes = _ROW_BYTES[fmt] + request.include_spread * _SPREAD_BYTES[fmt]
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


def _simulation_seconds(plan: MarketPlan, n_days: int, open_minutes: int) -> float:
    structure = plan.spec.structure
    draws = 1440 * (len(structure.factors) + 3 * len(structure.instruments))
    return n_days * (draws * _DRAW_SECONDS + _MARKET_DAY_SECONDS) + (
        open_minutes * len(plan.selected) * _INSTRUMENT_MINUTE_SECONDS
    )
