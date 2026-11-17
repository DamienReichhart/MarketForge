# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

"""Running a planned request from the command line: progress bar, warnings, summary."""

from __future__ import annotations

import os
import sys
import threading
import time
import warnings
from pathlib import Path

import click
from tqdm import tqdm

from marketforge.api.disk import write_request
from marketforge.api.planning import Request
from marketforge.domain.markets import MarketType
from marketforge.domain.time import SECONDS_PER_DAY

jobs_option = click.option(
    "--jobs",
    "-j",
    type=click.IntRange(min=1),
    default=None,
    help="Markets simulated in parallel. Default: one per market, up to the CPU count.",
)
progress_option = click.option(
    "--progress/--no-progress", default=True, show_default=True, help="Show a progress bar."
)
quiet_option = click.option(
    "--quiet", "-q", is_flag=True, help="Print nothing but warnings and errors (for scripts)."
)
days_option = click.option(
    "--days",
    type=click.IntRange(min=1),
    help="Length of the range in days, instead of --to.",
)


def end_of_range(start: int, end: str | None, days: int | None) -> str | int:
    """The end the user asked for with exactly one of ``--to`` and ``--days``."""
    if end is not None and days is None:
        return end
    if days is not None and end is None:
        return start + days * SECONDS_PER_DAY
    raise click.UsageError("Give exactly one of '--to' and '--days'.")


def run(
    request: Request,
    output_dir: str,
    fmt: str,
    timestamps: str,
    jobs: int | None,
    progress: bool,
    overwrite: bool = False,
    quiet: bool = False,
) -> None:
    """Write a request's candles to ``output_dir`` and report what was done."""
    jobs = jobs or min(len(request.plans), os.cpu_count() or 1)
    t0 = time.time()
    bar = None
    lock = threading.Lock()
    if progress and not quiet:
        total = request.n_days * len(request.plans)
        bar = tqdm(total=total, unit="day", desc="Simulating", ncols=90, file=sys.stderr)

    def tick(_: MarketType) -> None:
        if bar is not None:
            with lock:
                bar.update(1)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            report = write_request(
                request,
                output_dir,
                fmt=fmt,
                timestamps=timestamps,
                jobs=jobs,
                on_day=tick,
                overwrite=overwrite,
            )
        finally:
            if bar is not None:
                bar.close()
    elapsed = time.time() - t0
    if quiet:
        for warning in caught:
            click.secho(f"Warning: {warning.message}", fg="yellow", err=True)
        return
    click.secho(
        f"\nDone in {elapsed:.1f}s: {report.n_files} files in {Path(output_dir).resolve()}",
        fg="green",
    )
    for warning in caught:
        click.secho(f"Warning: {warning.message}", fg="yellow", err=True)
