# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

"""``marketforge validate``."""

from __future__ import annotations

import click

from marketforge.api.validating import validate as validate_candles
from marketforge.domain.markets import MarketType


@click.command()
@click.option(
    "--input",
    "input_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="CSV or Parquet file of m1 candles with open/high/low/close columns.",
)
@click.option(
    "--market",
    type=click.Choice([m.value for m in MarketType]),
    help="Market whose bands to apply. Default: read from the path ({market}/{SYMBOL}_m1).",
)
def validate(input_path: str, market: str | None) -> None:
    """Check an m1 candle file against real-market stylized facts (exit 1 on failure)."""
    try:
        report = validate_candles(input_path, market)
    except ValueError as e:
        raise click.UsageError(str(e)) from None
    click.echo(report.summary())
    if not report.passed:
        raise click.exceptions.Exit(1)
