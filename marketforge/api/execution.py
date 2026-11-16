# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the MIT License. See the LICENSE file in the project
# root for full license information.

"""Running a request: simulate each market day by day and aggregate every timeframe."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from threadpoolctl import threadpool_limits

from marketforge.aggregation.streaming import BarAggregator
from marketforge.api.planning import MarketPlan, Request
from marketforge.calendars.trading_calendar import get_calendar
from marketforge.domain.bars import Bars
from marketforge.domain.markets import MarketType
from marketforge.domain.time import SECONDS_PER_DAY
from marketforge.domain.timeframes import Timeframe
from marketforge.simulation.simulator import MarketSimulator

# Receives candles of the plan's *selected* instruments, in plan.selected order.
Sink = Callable[[MarketPlan, Timeframe, Bars | None], None]


def _run_market(
    request: Request,
    plan: MarketPlan,
    sink: Sink,
    on_day: Callable[[MarketType], None] | None = None,
) -> None:
    # Random draws are market-wide; everything after them runs only for the
    # selected instruments, whose columns come back in plan.selected order.
    sim = MarketSimulator(plan.spec, request.seed, instruments=plan.selected)
    cal = get_calendar(plan.market)
    aggs = {tf: BarAggregator(cal, tf, request.start, request.end) for tf in request.timeframes}
    first = request.start // SECONDS_PER_DAY
    last = (request.end - 1) // SECONDS_PER_DAY
    for day in range(first, last + 1):
        m1 = sim.simulate_day(day, request.start, request.end)
        if m1 is not None:
            anchor = cal.anchor_minutes(m1.timestamps)  # shared by every timeframe
            for tf, agg in aggs.items():
                sink(plan, tf, agg.push(m1, anchor))
        if on_day is not None:
            on_day(plan.market)
    for tf, agg in aggs.items():
        sink(plan, tf, agg.finish())


def execute(
    request: Request,
    sink: Sink,
    jobs: int = 1,
    on_day: Callable[[MarketType], None] | None = None,
) -> None:
    """Run every market of a request, optionally in parallel threads."""
    # The matrix products here are tiny; multithreaded BLAS only burns CPU
    # (4x the CPU time for the same wall time) and oversubscribes parallel jobs.
    with threadpool_limits(limits=1, user_api="blas"):
        if jobs <= 1 or len(request.plans) == 1:
            for plan in request.plans:
                _run_market(request, plan, sink, on_day)
            return
        with ThreadPoolExecutor(max_workers=min(jobs, len(request.plans))) as pool:
            for f in [pool.submit(_run_market, request, p, sink, on_day) for p in request.plans]:
                f.result()
