# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

"""``marketforge verify``."""

from __future__ import annotations

import click

from marketforge.api.inspecting import verify as verify_dataset


@click.command()
@click.argument("dataset", type=click.Path(exists=True, file_okay=False))
@click.option(
    "--checksums",
    is_flag=True,
    help="Only compare every file with the checksum its manifest recorded: fast, nothing "
    "is regenerated.",
)
@click.option("--jobs", "-j", type=click.IntRange(min=1), default=None, help="Markets in parallel.")
def verify(dataset: str, checksums: bool, jobs: int | None) -> None:
    """
    Regenerate DATASET from its manifest and compare every file with it.

    CSV files must be identical byte for byte, Parquet and Feather files value
    for value. The fresh copy is written beside DATASET, so it needs as much
    free space. Exits 1 if any file differs or is missing: the dataset was
    modified, or it was written on another kind of machine. With --checksums,
    each file is compared with the checksum recorded when it was written.
    """
    report = verify_dataset(dataset, checksums=checksums, jobs=jobs)
    for rel in report.differs:
        click.echo(f"differs: {rel}")
    for rel in report.missing:
        click.echo(f"missing: {rel}")
    for rel in report.extra:
        click.echo(f"extra:   {rel}")
    click.secho(
        f"{len(report.identical)}/{report.expected} files identical to "
        + ("their recorded checksums" if checksums else "a fresh generation"),
        fg="green" if report.passed else "red",
        bold=True,
    )
    if not report.passed:
        raise click.exceptions.Exit(1)
