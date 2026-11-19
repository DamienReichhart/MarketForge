# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

"""The plan ``generate`` prints before running: what will be produced, how big, how long."""

from __future__ import annotations

import datetime as dt

import click

from marketforge import __version__
from marketforge.api.estimating import estimate_request
from marketforge.api.planning import Request


def print_plan(
    request: Request,
    fmt: str,
    output_dir: str | None,
    random_seed: bool,
    jobs: int | None = None,
    layout: str = "split",
) -> None:
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
    guess = estimate_request(request, fmt)
    for plan in request.plans:
        names = ", ".join(plan.selected[:6]) + (
            f" (+{len(plan.selected) - 6} more)" if len(plan.selected) > 6 else ""
        )
        minutes = guess.open_minutes[plan.market.value]
        click.echo(
            f"  {plan.market.value:<11} {len(plan.selected)} instrument(s), {minutes:,} open minutes: {names}"
        )
    files = len(request.plans) * len(request.timeframes) if layout == "long" else guess.files
    click.echo(
        f"  Output      {files} {fmt} files, ~{guess.rows:,} rows, ~{_human(guess.disk_bytes)}"
        + (
            f" {'added to' if request.extends_from is not None else 'in'} {output_dir}"
            if output_dir
            else ""
        )
    )
    jobs = jobs or len(request.plans)
    click.echo(
        f"  Estimate    ~{_duration(guess.wall_seconds(jobs))}"
        + (f" with {jobs} markets in parallel" if jobs > 1 and len(request.plans) > 1 else "")
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
