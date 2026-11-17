# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

"""``marketforge calibrate``."""

from __future__ import annotations

import click

from marketforge.api.calibrating import calibrate as fit
from marketforge.api.calibrating import write_overrides
from marketforge.domain.markets import MarketType


@click.command()
@click.argument("files", nargs=-1, required=True, type=click.Path(exists=True, dir_okay=False))
@click.option(
    "--market",
    "-m",
    required=True,
    type=click.Choice([m.value for m in MarketType]),
    help="The market the instruments belong to (its calendar and correlations).",
)
@click.option(
    "--output",
    "-o",
    default="calibrated.toml",
    show_default=True,
    type=click.Path(dir_okay=False),
    help="Override file to write.",
)
def calibrate(files: tuple[str, ...], market: str, output: str) -> None:
    """
    Fit instruments to your own m1 candle FILES and write an override file.

    Each file is one instrument, named SYMBOL_m1.csv (or .parquet, .feather):
    a catalog symbol is re-parameterised, any other becomes a new instrument.
    Start price, annualised volatility, volume and correlations are fitted;
    use the file with --config to generate data like yours.
    """
    overrides = fit(list(files), market)
    path = write_overrides(overrides, output)
    for symbol, body in overrides.items():
        click.echo(
            f"  {symbol:<10} start {body['start_price']:,.6g}  volatility {body['volatility']:.3f}"
            + (f"  volume {body['volume_base']:,.1f}" if "volume_base" in body else "")
        )
    click.secho(f"Wrote {path}: generate with --config {path}", fg="green")
