# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the MIT License. See the LICENSE file in the project
# root for full license information.

"""The plan ``generate`` prints before running: what will be produced, how big, how long."""

from __future__ import annotations

import datetime as dt

import click

from marketforge import __version__
from marketforge.api.planning import MarketPlan, Request
from marketforge.calendars.trading_calendar import get_calendar


def print_plan(request: Request, fmt: str, output_dir: str | None, random_seed: bool) -> None:
    def iso(t: int) -> str:
        return dt.datetime.fromtimestamp(t, dt.UTC).strftime("%Y-%m-%d %H:%M UTC")

    since = request.start if request.extends_from is None else request.extends_from
    click.secho("MarketForge " + __version__, bold=True)
    click.echo(f"  Range       {iso(since)} -> {iso(request.end)}")
    click.echo(
        f"  Seed        {request.seed}"
        + ("  (random; pass --seed to fix it)" if random_seed else "")
    )
    click.echo(f"  Timeframes  {', '.join(tf.name for tf in request.timeframes)}")
    rows = 0
    seconds = 0.0
    for plan in request.plans:
        open_minutes = get_calendar(plan.market).count_open_minutes(since, request.end)
        per_instrument = sum(
            open_minutes // max(1, min(tf.minutes, 1440)) for tf in request.timeframes
        )
        rows += per_instrument * len(plan.selected)
        seconds += _simulation_seconds(plan, request.n_days, open_minutes)
        names = ", ".join(plan.selected[:6]) + (
            f" (+{len(plan.selected) - 6} more)" if len(plan.selected) > 6 else ""
        )
        click.echo(
            f"  {plan.market.value:<11} {len(plan.selected)} instrument(s), {open_minutes:,} open minutes: {names}"
        )
    bytes_per_row = (68 if fmt == "csv" else 33) + request.include_spread * (
        11 if fmt == "csv" else 6
    )
    seconds += rows * (_CSV_ROW_SECONDS if fmt == "csv" else _PARQUET_ROW_SECONDS)
    n_files = sum(len(p.selected) for p in request.plans) * len(request.timeframes)
    click.echo(
        f"  Output      {n_files} {fmt} files, ~{rows:,} rows, ~{_human(rows * bytes_per_row)}"
        + (
            f" {'added to' if request.extends_from is not None else 'in'} {output_dir}"
            if output_dir
            else ""
        )
    )
    click.echo(f"  Estimate    ~{_duration(seconds)} on one core")


# Cost model behind --dry-run's time estimate (one core, measured on 3.1).
# Random draws are market-wide and fixed-shape: 1440 x (factors + 3 x
# instruments) per simulated day, whatever is selected. The rest of the
# simulation runs only for the selected instruments' open minutes.
_DRAW_SECONDS = 7e-9
_INSTRUMENT_MINUTE_SECONDS = 35e-9
_MARKET_DAY_SECONDS = 1e-3  # per-day bookkeeping (calendar, aggregation, buffers)
_CSV_ROW_SECONDS = 0.75e-6  # aggregation + formatting + writing, per output row
_PARQUET_ROW_SECONDS = 0.6e-6


def _simulation_seconds(plan: MarketPlan, n_days: int, open_minutes: int) -> float:
    structure = plan.spec.structure
    draws = 1440 * (len(structure.factors) + 3 * len(structure.instruments))
    return n_days * (draws * _DRAW_SECONDS + _MARKET_DAY_SECONDS) + (
        open_minutes * len(plan.selected) * _INSTRUMENT_MINUTE_SECONDS
    )


def _human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _duration(s: float) -> str:
    if s < 60:
        return f"{max(1, round(s))}s"
    if s < 3600:
        return f"{s / 60:.0f} min"
    return f"{s / 3600:.1f} h"
