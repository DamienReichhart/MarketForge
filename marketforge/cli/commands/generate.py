# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

"""``marketforge generate``."""

from __future__ import annotations

import click

from marketforge.api.parsing import parse_time
from marketforge.api.planning import plan_request
from marketforge.cli.plan_summary import print_plan
from marketforge.cli.running import (
    days_option,
    end_of_range,
    jobs_option,
    progress_option,
    quiet_option,
    run,
)
from marketforge.output.manifest import dataset_files


@click.command()
@click.option(
    "--output-dir",
    "-o",
    type=click.Path(file_okay=False),
    help="Directory to write {market}/{SYMBOL}_{tf}.{csv|parquet|feather} files into.",
)
@click.option(
    "--from",
    "start",
    required=True,
    metavar="TIME",
    help="Start (inclusive): 2024-01-01, 2024-01-01T09:30, or Unix seconds. UTC unless an offset is given.",
)
@click.option("--to", "end", metavar="TIME", help="End (exclusive), same formats as --from.")
@days_option
@click.option(
    "--instruments",
    "-i",
    metavar="LIST",
    help="Comma-separated instruments, e.g. EURUSD,AAPL,BTCUSD. Markets are inferred.",
)
@click.option(
    "--market",
    "-m",
    "markets",
    metavar="LIST",
    help="Comma-separated markets: crypto, forex, stocks, or all (default when --instruments is not given).",
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
    help="Comma-separated, in any letter case. Any of m1,m2,m3,m5,m10,m15,m20,m30,"
    "H1,H2,H3,H4,H6,H8,H12,D1,W1; the default is the eight shown.",
)
@click.option(
    "--anomalies", metavar="LIST", help="Optional unrealistic events: spikes, flash_crash."
)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["csv", "parquet", "feather"]),
    default="csv",
    show_default=True,
    help="Output file format. Feather (Arrow IPC) loads fastest; Parquet is smallest.",
)
@click.option(
    "--timestamps",
    type=click.Choice(["unix", "iso", "datetime"]),
    default="unix",
    show_default=True,
    help="How time is written: Unix seconds; ISO 8601 like 2024-01-02T14:30:00Z (CSV); "
    "or a native UTC time column (Parquet, Feather).",
)
@click.option(
    "--config",
    "overrides",
    type=click.Path(exists=True, dir_okay=False),
    help="TOML override file to change or add instruments.",
)
@click.option(
    "--with-spread",
    is_flag=True,
    help="Add a 'spread' column: the mean quoted bid-ask spread of the candle, in price units.",
)
@click.option(
    "--with-regime",
    is_flag=True,
    help="Add a 'regime' column: trend_up, trend_down, range, high_volatility or crash.",
)
@jobs_option
@click.option(
    "--dry-run",
    is_flag=True,
    help="Print what would be generated (files, rows, size, time) and exit.",
)
@click.option(
    "--overwrite",
    is_flag=True,
    help="Replace the dataset already in --output-dir. Without it, a directory that holds one is refused.",
)
@progress_option
@quiet_option
def generate(
    output_dir: str | None,
    start: str,
    end: str | None,
    days: int | None,
    instruments: str | None,
    markets: str | None,
    seed: int | None,
    timeframes: str,
    anomalies: str | None,
    fmt: str,
    timestamps: str,
    overrides: str | None,
    with_spread: bool,
    with_regime: bool,
    jobs: int | None,
    dry_run: bool,
    overwrite: bool,
    progress: bool,
    quiet: bool,
) -> None:
    """Generate a dataset: candle files and the manifest that records how they were made."""
    if not dry_run and not output_dir:
        raise click.UsageError("Missing option '--output-dir' / '-o'.")
    if fmt != "csv" and timestamps == "iso":
        raise click.UsageError(
            f"--timestamps iso is for CSV files; for {fmt} use --timestamps datetime (a native "
            "time column) or unix."
        )
    if fmt == "csv" and timestamps == "datetime":
        raise click.UsageError(
            "--timestamps datetime is for Parquet and Feather files; for CSV use iso or unix."
        )
    if output_dir and not dry_run and not overwrite and (existing := dataset_files(output_dir)):
        raise click.ClickException(
            f"{output_dir} already holds a MarketForge dataset ({len(existing)} files). "
            "Add --overwrite to replace it, or continue it with `marketforge extend`."
        )
    request = plan_request(
        instruments,
        markets,
        start=start,
        end=end_of_range(parse_time(start), end, days),
        seed=seed,
        timeframes=timeframes,
        anomalies=anomalies or (),
        include_regime=with_regime,
        include_spread=with_spread,
        overrides=overrides,
    )
    if not quiet or dry_run:
        print_plan(request, fmt, output_dir, seed is None, jobs)
    if dry_run or not output_dir:
        return
    run(request, output_dir, fmt, timestamps, jobs, progress, overwrite, quiet)
    if not quiet:
        click.echo(f"Reproduce with --seed {request.seed} (the manifest records every setting)")
