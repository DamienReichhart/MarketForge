# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

"""``marketforge info``."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

import click

from marketforge._version import MODEL_REVISION, __version__
from marketforge.output.manifest import dataset_files, read_manifest


@click.command()
@click.argument("dataset", type=click.Path(exists=True, file_okay=False))
@click.option("--json", "as_json", is_flag=True, help="Print the summary as JSON.")
def info(dataset: str, as_json: bool) -> None:
    """Summarise a dataset: how it was made, what it holds, and whether it can be extended."""
    manifest = read_manifest(dataset)
    files = [p for p in dataset_files(dataset) if p.name != "marketforge.json"]
    reason = (
        None
        if manifest.model_revision == MODEL_REVISION
        else f"written by model revision {manifest.model_revision}; MarketForge {__version__} "
        f"has {MODEL_REVISION} (install marketforge=={manifest.version})"
    )
    doc: dict[str, Any] = {
        "path": str(Path(dataset).resolve()),
        "marketforge": manifest.version,
        "model_revision": manifest.model_revision,
        "seed": manifest.seed,
        "start": _iso(manifest.start),
        "end": _iso(manifest.end),
        "format": manifest.format,
        "timestamps": manifest.timestamps,
        "timeframes": manifest.timeframes,
        "instruments": manifest.instruments,
        "columns": {"spread": manifest.include_spread, "regime": manifest.include_regime},
        "anomalies": manifest.anomalies,
        "overrides": sorted(manifest.overrides),
        "files": len(files),
        "bytes": sum(p.stat().st_size for p in files),
        "extendable": reason is None,
    }
    if as_json:
        click.echo(json.dumps(doc, indent=2))
        return

    def when(seconds: int) -> str:
        return dt.datetime.fromtimestamp(seconds, dt.UTC).strftime("%Y-%m-%d %H:%M UTC")

    click.secho(f"Dataset {doc['path']}", bold=True)
    click.echo(
        f"  Written by  MarketForge {manifest.version} (model revision {manifest.model_revision})"
    )
    click.echo(f"  Seed        {manifest.seed}")
    click.echo(f"  Range       {when(manifest.start)} -> {when(manifest.end)}")
    for market, symbols in manifest.instruments.items():
        names = ", ".join(symbols[:6]) + (
            f" (+{len(symbols) - 6} more)" if len(symbols) > 6 else ""
        )
        click.echo(f"  {market:<11} {len(symbols)} instrument(s): {names}")
    extra = [name for name, on in doc["columns"].items() if on]
    click.echo(
        f"  Files       {doc['files']} {manifest.format} files, {_human(doc['bytes'])}; "
        f"timeframes {', '.join(manifest.timeframes)}"
        + (f"; with {' and '.join(extra)}" if extra else "")
    )
    if manifest.anomalies:
        click.echo(f"  Anomalies   {', '.join(manifest.anomalies)}")
    if manifest.overrides:
        click.echo(f"  Overrides   {', '.join(sorted(manifest.overrides))}")
    click.echo(f"  Can extend  {'yes' if reason is None else 'no: ' + reason}")


def _iso(seconds: int) -> str:
    return dt.datetime.fromtimestamp(seconds, dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"
