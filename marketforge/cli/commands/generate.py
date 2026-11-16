# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the MIT License. See the LICENSE file in the project
# root for full license information.

"""``marketforge generate``."""

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
from marketforge.api.planning import plan_request
from marketforge.cli.plan_summary import print_plan
from marketforge.domain.markets import MarketType


@click.command()
@click.option(
    "--output-dir",
    "-o",
    type=click.Path(file_okay=False),
    help="Directory to write {market}/{SYMBOL}_{tf}.{csv|parquet} files into.",
)
@click.option(
    "--from",
    "start",
    required=True,
    metavar="TIME",
    help="Start (inclusive): 2024-01-01, 2024-01-01T09:30, or Unix seconds. UTC unless an offset is given.",
)
@click.option(
    "--to", "end", required=True, metavar="TIME", help="End (exclusive), same formats as --from."
)
@click.option(
    "--assets",
    "-a",
    metavar="LIST",
    help="Comma-separated instruments, e.g. EURUSD,AAPL,BTCUSD. Markets are inferred.",
)
@click.option(
    "--market",
    "-m",
    "markets",
    metavar="LIST",
    help="Comma-separated markets: crypto, forex, stocks, or all (default when --assets is not given).",
)
@click.option(
    "--seed",
    "-s",
    type=click.IntRange(min=0),
    help="Seed for reproducible output. Printed when omitted so any run can be repeated.",
)
@click.option(
    "--timeframes",
    "-t",
    default="m1,m5,m15,m30,H1,H4,D1,W1",
    show_default=True,
    help="Comma-separated, in any letter case: m1,m5,m15,m30,H1,H4,D1,W1.",
)
@click.option(
    "--anomalies", metavar="LIST", help="Optional unrealistic events: spikes, flash_crash."
)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["csv", "parquet"]),
    default="csv",
    show_default=True,
    help="Output file format.",
)
@click.option(
    "--config",
    "overrides",
    type=click.Path(exists=True, dir_okay=False),
    help="TOML override file to change or add instruments.",
)
@click.option(
    "--with-regime",
    is_flag=True,
    help="Add a 'regime' column (0=trend_up 1=trend_down 2=range 3=high_volatility 4=crash).",
)
@click.option(
    "--jobs",
    "-j",
    type=click.IntRange(min=1),
    default=None,
    help="Markets simulated in parallel. Default: one per market, up to the CPU count.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Print what would be generated (files, rows, size, time) and exit.",
)
@click.option(
    "--progress/--no-progress", default=True, show_default=True, help="Show a progress bar."
)
def generate(
    output_dir: str | None,
    start: str,
    end: str,
    assets: str | None,
    markets: str | None,
    seed: int | None,
    timeframes: str,
    anomalies: str | None,
    fmt: str,
    overrides: str | None,
    with_regime: bool,
    jobs: int | None,
    dry_run: bool,
    progress: bool,
) -> None:
    """Generate candles and write them to disk."""
    if not dry_run and not output_dir:
        raise click.UsageError("Missing option '--output-dir' / '-o'.")
    request = plan_request(
        assets,
        markets,
        start=start,
        end=end,
        seed=seed,
        timeframes=timeframes,
        anomalies=anomalies or (),
        include_regime=with_regime,
        overrides=overrides,
    )
    jobs = jobs or min(len(request.plans), os.cpu_count() or 1)
    print_plan(request, fmt, output_dir, seed is None)
    if dry_run or not output_dir:
        return

    t0 = time.time()
    total = request.n_days * len(request.plans)
    bar = None
    lock = threading.Lock()
    if progress:
        bar = tqdm(total=total, unit="day", desc="Simulating", ncols=90, file=sys.stderr)

    def tick(_: MarketType) -> None:
        if bar is not None:
            with lock:
                bar.update(1)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            report = write_request(request, output_dir, fmt=fmt, jobs=jobs, on_day=tick)
        finally:
            if bar is not None:
                bar.close()
    elapsed = time.time() - t0
    click.secho(
        f"\nDone in {elapsed:.1f}s: {report.n_files} files in {Path(output_dir).resolve()}",
        fg="green",
    )
    click.echo(f"Reproduce with --seed {report.seed}")
    for warning in caught:
        click.secho(f"Warning: {warning.message}", fg="yellow", err=True)
