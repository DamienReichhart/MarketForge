# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

"""``marketforge validate``."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import click

from marketforge.api.validating import validate as validate_candles
from marketforge.cli.renamed import renamed_option
from marketforge.domain.markets import MarketType
from marketforge.output.manifest import dataset_files


@click.command()
@click.argument("path", type=click.Path(exists=True))
@renamed_option("--input", "the path as an argument, marketforge validate PATH")
@click.option(
    "--market",
    "-m",
    type=click.Choice([m.value for m in MarketType], case_sensitive=False),
    help="Market whose bands to apply. Default: read from the path ({market}/{SYMBOL}_m1).",
)
@click.option("--json", "as_json", is_flag=True, help="Print each file's statistics as JSON.")
def validate(path: str, market: str | None, as_json: bool) -> None:
    """
    Check m1 candles against real-market stylized facts (exit 1 on failure).

    PATH is an m1 candle file (CSV, Parquet or Feather) with open, high, low
    and close columns, or a dataset directory: every m1 file in it.
    """
    root = Path(path)
    if root.is_dir():
        files = sorted(p for p in dataset_files(root) if p.stem.endswith("_m1"))
        if not files:
            raise click.UsageError(
                f"{root} has no m1 files to validate: the bands describe minute returns. "
                "Generate with -t m1 (add it to the other timeframes)."
            )
    else:
        files = [root]
    reports = {}
    skipped: dict[Path, str] = {}
    for file in files:
        try:
            reports[file] = validate_candles(file, market)
        except ValueError as e:
            if not root.is_dir():
                raise click.ClickException(str(e)) from None
            skipped[file] = str(e)  # one unusable file does not stop the others
    if not reports:
        raise click.ClickException(
            f"No m1 file of {root} could be validated:\n"
            + "\n".join(f"  {p.relative_to(root).as_posix()}: {why}" for p, why in skipped.items())
        )
    passed = all(r.passed for r in reports.values())
    if as_json:
        click.echo(
            json.dumps(
                {
                    (p.relative_to(root).as_posix() if root.is_dir() else str(p)): {
                        "market": r.market_type.value,
                        "passed": r.passed,
                        "metrics": {name: asdict(m) for name, m in r.metrics.items()},
                    }
                    for p, r in reports.items()
                },
                indent=2,
            )
        )
    elif root.is_dir():
        for file, report in reports.items():
            flag = "ok  " if report.passed else "FAIL"
            click.echo(f"{flag} {file.relative_to(root).as_posix()}")
            if not report.passed:
                failed = [m for m in report.metrics.values() if not m.passed]
                for m in failed:
                    click.echo(f"       {m.name} = {m.value:.4f}")
        for file, why in skipped.items():
            click.echo(f"skip {file.relative_to(root).as_posix()}: {why}")
        good = sum(r.passed for r in reports.values())
        click.secho(
            f"{good}/{len(reports)} files pass" + (f" ({len(skipped)} skipped)" if skipped else ""),
            fg="green" if passed else "red",
            bold=True,
        )
    else:
        click.echo(next(iter(reports.values())).summary())
    if not passed:
        raise click.exceptions.Exit(1)
