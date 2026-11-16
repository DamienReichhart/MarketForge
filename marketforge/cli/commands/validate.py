# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the MIT License. See the LICENSE file in the project
# root for full license information.

"""``marketforge validate``."""

from __future__ import annotations

import sys
from pathlib import Path

import click
import pandas as pd

from marketforge.domain.markets import MarketType
from marketforge.validation.report import validate_ohlcv


@click.command()
@click.option(
    "--input",
    "input_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="CSV or Parquet file with open/high/low/close columns.",
)
@click.option(
    "--market",
    required=True,
    type=click.Choice([m.value for m in MarketType]),
    help="Market whose target bands to apply.",
)
def validate(input_path: str, market: str) -> None:
    """Check a candle file against real-market stylized facts (exit 1 on failure)."""
    path = Path(input_path)
    df = pd.read_parquet(path) if path.suffix == ".parquet" else pd.read_csv(path)
    missing = {"open", "high", "low", "close"} - set(df.columns)
    if missing:
        raise click.UsageError(f"{path} lacks column(s): {', '.join(sorted(missing))}")
    report = validate_ohlcv(
        df["open"].to_numpy(),
        df["high"].to_numpy(),
        df["low"].to_numpy(),
        df["close"].to_numpy(),
        MarketType(market),
    )
    click.echo(report.summary())
    sys.exit(0 if report.passed else 1)
