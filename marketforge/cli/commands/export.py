# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

"""``marketforge export``."""

from __future__ import annotations

import click

from marketforge.api.exporting import export as export_dataset
from marketforge.output.engines import ENGINES


@click.command()
@click.argument("engine", type=click.Choice(ENGINES, case_sensitive=False))
@click.argument("dataset", type=click.Path(exists=True, file_okay=False))
@click.argument("dest", type=click.Path(file_okay=False))
@click.option(
    "--quote",
    metavar="CODE",
    help="freqtrade: name the dollar quote CODE in pair names (USDT: BTC_USDT-5m.feather).",
)
def export(engine: str, dataset: str, dest: str, quote: str | None) -> None:
    """Write DATASET in the file layout ENGINE reads, under DEST.

    freqtrade: DEST is its data directory (--datadir). lean: DEST is LEAN's
    data folder; the dataset needs m1 candles.
    """
    try:
        report = export_dataset(engine, dataset, dest, quote=quote)
    except ValueError as e:
        raise click.UsageError(str(e)) from None
    for line in report.skipped:
        click.echo(f"skipped {line}", err=True)
    click.echo(f"Wrote {len(report.files)} {report.engine} file(s) under {dest}")
