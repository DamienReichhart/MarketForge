# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the MIT License. See the LICENSE file in the project
# root for full license information.

"""Candles streamed to CSV or Parquet files."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from marketforge.api.execution import execute, warn_about_empty
from marketforge.api.parsing import Names, TimeLike
from marketforge.api.planning import DEFAULT_TIMEFRAMES, MarketPlan, Request, plan_request
from marketforge.domain.bars import Bars
from marketforge.domain.markets import MarketType
from marketforge.domain.timeframes import Timeframe
from marketforge.output.file_limits import ensure_open_file_capacity
from marketforge.output.formats import OutputFormat
from marketforge.output.writer import CandleWriter


@dataclass
class DiskReport:
    """Result of :func:`generate_to_disk`."""

    seed: int
    paths: dict[str, dict[str, dict[str, Path]]] = field(
        default_factory=dict
    )  # market -> symbol -> tf -> path

    @property
    def n_files(self) -> int:
        return sum(len(tfs) for syms in self.paths.values() for tfs in syms.values())


def generate_to_disk(
    output_dir: str | Path,
    assets: Names | None = None,
    *,
    start: TimeLike,
    end: TimeLike,
    markets: Names | None = None,
    seed: int | None = None,
    timeframes: Names = DEFAULT_TIMEFRAMES,
    anomalies: Names = (),
    include_regime: bool = False,
    overrides: str | Path | None = None,
    fmt: str | OutputFormat = OutputFormat.CSV,
    jobs: int = 1,
    on_day: Callable[[MarketType], None] | None = None,
) -> DiskReport:
    """
    Generate candles and stream them to ``{output_dir}/{market}/{SYMBOL}_{tf}.{fmt}``.

    Takes the same arguments as :func:`generate` plus ``fmt`` (``csv`` or
    ``parquet``) and ``jobs`` (markets simulated in parallel). Memory use does
    not grow with the length of the range.
    """
    request = plan_request(
        assets,
        markets,
        start=start,
        end=end,
        seed=seed,
        timeframes=timeframes,
        anomalies=anomalies,
        include_regime=include_regime,
        overrides=overrides,
    )
    return write_request(request, output_dir, fmt=fmt, jobs=jobs, on_day=on_day)


def write_request(
    request: Request,
    output_dir: str | Path,
    *,
    fmt: str | OutputFormat = OutputFormat.CSV,
    jobs: int = 1,
    on_day: Callable[[MarketType], None] | None = None,
) -> DiskReport:
    """Run an already resolved request and stream its candles to ``output_dir``."""
    fmt = OutputFormat(fmt)
    if fmt == OutputFormat.PARQUET:
        n_files = sum(len(p.selected) for p in request.plans) * len(request.timeframes)
        ensure_open_file_capacity(n_files)
    writers = {
        plan.market: CandleWriter(
            output_dir,
            plan.market.value,
            plan.selected,
            list(range(len(plan.selected))),
            request.timeframes,
            fmt,
            request.include_regime,
        )
        for plan in request.plans
    }

    def write(plan: MarketPlan, tf: Timeframe, bars: Bars | None) -> None:
        writers[plan.market].write(tf, bars)

    report = DiskReport(seed=request.seed)

    def close_all() -> BaseException | None:
        # Close every writer even if one fails; return the first error.
        first: BaseException | None = None
        for market, writer in writers.items():
            try:
                paths = writer.close()
            except BaseException as e:
                first = first or e
                continue
            report.paths[market.value] = {s: dict(tfs) for s, tfs in paths.items()}
        return first

    try:
        execute(request, write, jobs=jobs, on_day=on_day)
    except BaseException:
        close_all()  # the generation error wins over any error while closing
        raise
    error = close_all()
    if error is not None:
        raise error
    warn_about_empty(pair for writer in writers.values() for pair in writer.empty)
    return report
