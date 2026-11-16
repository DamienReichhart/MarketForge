# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the GNU Affero General Public License v3.0 or later.
# See the LICENSE file in the project root for full license information.

"""Running a request: simulate each market day by day and aggregate every timeframe."""

from __future__ import annotations

import warnings
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor

from threadpoolctl import threadpool_limits

from marketforge.aggregation.streaming import BarAggregator
from marketforge.api.planning import RESUME_DAYS, Checkpoint, MarketPlan, Request
from marketforge.calendars.trading_calendar import get_calendar
from marketforge.domain.bars import Bars
from marketforge.domain.markets import MarketType
from marketforge.domain.timeframes import Timeframe
from marketforge.simulation.simulator import MarketSimulator

# Receives candles of the plan's *selected* instruments, in plan.selected order.
Sink = Callable[[MarketPlan, Timeframe, Bars], None]


def _run_market(
    request: Request,
    plan: MarketPlan,
    sink: Sink,
    on_day: Callable[[MarketType], None] | None = None,
) -> Checkpoint:
    # Random draws are market-wide; everything after them runs only for the
    # selected instruments, whose columns come back in plan.selected order.
    sim = MarketSimulator(
        plan.spec, request.seed, instruments=plan.selected, spread=request.include_spread
    )
    cal = get_calendar(plan.market)
    aggs = {tf: BarAggregator(cal, tf, request.start, request.end) for tf in request.timeframes}
    # An extension re-simulates the last days of the dataset to rebuild the
    # candles that were still open at its end, and publishes only the candles
    # after the ones the dataset already holds.
    written: dict[Timeframe, int] = {}
    first = request.first_day
    if plan.resume is not None:
        sim.restore(plan.resume.state)
        written = {Timeframe[name]: ts for name, ts in plan.resume.written.items()}
        first = plan.resume.day

    def publish(tf: Timeframe, bars: Bars | None) -> None:
        if bars is not None and tf in written:
            bars = bars.after(written[tf])
        if bars is not None and len(bars):
            written[tf] = int(bars.timestamps[-1])
            sink(plan, tf, bars)

    resume_day = max(first, request.last_day - RESUME_DAYS)
    state = sim.snapshot()
    for day in range(first, request.last_day + 1):
        if day == resume_day:
            state = sim.snapshot()
        m1 = sim.simulate_day(day, request.start, request.end)
        if m1 is not None:
            anchor = cal.anchor_minutes(m1.timestamps)  # shared by every timeframe
            for tf, agg in aggs.items():
                publish(tf, agg.push(m1, anchor))
        if on_day is not None:
            on_day(plan.market)
    for tf, agg in aggs.items():
        publish(tf, agg.finish())
    return Checkpoint(resume_day, state, {tf.name: ts for tf, ts in written.items()})


def execute(
    request: Request,
    sink: Sink,
    jobs: int = 1,
    on_day: Callable[[MarketType], None] | None = None,
) -> dict[MarketType, Checkpoint]:
    """
    Run every market of a request, optionally in parallel threads.

    Returns, per market, the checkpoint a later extension resumes from.
    """
    # The matrix products here are tiny; multithreaded BLAS only burns CPU
    # (4x the CPU time for the same wall time) and oversubscribes parallel jobs.
    with threadpool_limits(limits=1, user_api="blas"):
        if jobs <= 1 or len(request.plans) == 1:
            return {p.market: _run_market(request, p, sink, on_day) for p in request.plans}
        with ThreadPoolExecutor(max_workers=min(jobs, len(request.plans))) as pool:
            futures = [pool.submit(_run_market, request, p, sink, on_day) for p in request.plans]
            return {p.market: f.result() for p, f in zip(request.plans, futures, strict=True)}


def warn_about_empty(empty: Iterable[tuple[str, str]]) -> None:
    """Warn once about the (instrument, timeframe) outputs that received no candle."""
    names = [f"{symbol} {timeframe}" for symbol, timeframe in empty]
    if not names:
        return
    shown = ", ".join(names[:6]) + (f" and {len(names) - 6} more" if len(names) > 6 else "")
    warnings.warn(
        f"No candles for {shown}: the range holds no complete candle of that timeframe "
        "(the market is closed, or the range is shorter than the candle)",
        stacklevel=3,
    )
