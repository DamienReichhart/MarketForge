# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

"""``marketforge extend``."""

from __future__ import annotations

import click

from marketforge.api.disk import plan_extension
from marketforge.cli.plan_summary import print_plan
from marketforge.cli.running import (
    days_option,
    end_of_range,
    jobs_option,
    progress_option,
    quiet_option,
    run,
)
from marketforge.output.manifest import read_manifest


@click.command()
@click.argument("dataset", type=click.Path(exists=True, file_okay=False))
@click.option(
    "--to",
    "end",
    metavar="TIME",
    help="New end (exclusive): 2025-02-01, 2025-02-01T09:30, or Unix seconds. UTC unless an offset is given.",
)
@days_option
@jobs_option
@click.option("--dry-run", is_flag=True, help="Print what would be added and exit.")
@progress_option
@quiet_option
def extend(
    dataset: str,
    end: str | None,
    days: int | None,
    jobs: int | None,
    dry_run: bool,
    progress: bool | None,
    quiet: bool,
) -> None:
    """
    Continue DATASET forward in time.

    The seed, instruments, timeframes and format are those the dataset was
    generated with. Afterwards it holds exactly the candles a single
    generation up to the new end would have produced.
    """
    new_end = end_of_range(read_manifest(dataset).end, end, days)
    request, fmt, timestamps = plan_extension(dataset, new_end)
    if not quiet or dry_run:
        print_plan(request, fmt, dataset, random_seed=False, jobs=jobs)
    if not dry_run:
        run(request, dataset, fmt, timestamps, jobs, progress, quiet=quiet)
