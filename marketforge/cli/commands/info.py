# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

"""``marketforge info``."""

from __future__ import annotations

import json

import click

from marketforge.api.inspecting import info as dataset_info


@click.command()
@click.argument("dataset", type=click.Path(exists=True, file_okay=False))
@click.option("--json", "as_json", is_flag=True, help="Print the summary as JSON.")
def info(dataset: str, as_json: bool) -> None:
    """Summarise a dataset: how it was made, what it holds, and whether it can be extended."""
    summary = dataset_info(dataset)
    doc = summary.to_dict()
    if as_json:
        click.echo(json.dumps(doc, indent=2))
        return

    def when(iso: str) -> str:
        return iso.replace("T", " ")[:16] + " UTC"

    click.secho(f"Dataset {summary.path}", bold=True)
    click.echo(
        f"  Written by  MarketForge {summary.version} (model revision {summary.model_revision})"
    )
    click.echo(f"  Seed        {summary.seed}")
    click.echo(f"  Range       {when(summary.start)} -> {when(summary.end)}")
    for market, symbols in summary.instruments.items():
        names = ", ".join(symbols[:6]) + (
            f" (+{len(symbols) - 6} more)" if len(symbols) > 6 else ""
        )
        click.echo(f"  {market:<11} {len(symbols)} instrument(s): {names}")
    extra = [name.replace("_", "/") for name, on in summary.columns.items() if on]
    files = f"{summary.files} {summary.format} file{'' if summary.files == 1 else 's'}"
    click.echo(
        f"  Files       {files}, {_human(summary.bytes)}; "
        f"timeframes {', '.join(summary.timeframes)}"
        + (f"; with {' and '.join(extra)}" if extra else "")
    )
    if summary.anomalies:
        click.echo(f"  Anomalies   {', '.join(summary.anomalies)}")
    if summary.overrides:
        click.echo(f"  Overrides   {', '.join(summary.overrides)}")
    because = summary.not_extendable_because
    click.echo(f"  Can extend  {'yes' if because is None else 'no: ' + because}")


def _human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"
