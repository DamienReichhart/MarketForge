# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

"""``marketforge verify``."""

from __future__ import annotations

import tempfile
from pathlib import Path

import click

from marketforge._version import MODEL_REVISION, __version__
from marketforge.api.disk import write_request
from marketforge.api.planning import plan_request
from marketforge.output.manifest import dataset_files, read_manifest


@click.command()
@click.argument("dataset", type=click.Path(exists=True, file_okay=False))
@click.option("--jobs", "-j", type=click.IntRange(min=1), default=None, help="Markets in parallel.")
def verify(dataset: str, jobs: int | None) -> None:
    """
    Regenerate DATASET from its manifest and compare every file, byte for byte.

    Exits 1 if any file differs or is missing: the dataset was modified, or it
    was written by another version or on another kind of machine.
    """
    root = Path(dataset)
    m = read_manifest(root)
    if m.model_revision != MODEL_REVISION:
        raise click.ClickException(
            f"{root} was written by MarketForge {m.version} (model revision {m.model_revision}); "
            f"{__version__} has model revision {MODEL_REVISION} and produces other candles. "
            f"Verify it with marketforge=={m.version}."
        )
    request = plan_request(
        [s for symbols in m.instruments.values() for s in symbols],
        start=m.start,
        end=m.end,
        seed=m.seed,
        timeframes=m.timeframes,
        anomalies=m.anomalies,
        include_regime=m.include_regime,
        include_spread=m.include_spread,
        include_bid_ask=m.include_bid_ask,
        overrides=m.overrides or None,
    )
    ours = sorted(p.relative_to(root) for p in dataset_files(root) if p.name != "marketforge.json")
    with tempfile.TemporaryDirectory() as tmp:
        write_request(
            request, tmp, fmt=m.format, timestamps=m.timestamps, jobs=jobs or len(request.plans)
        )
        fresh = Path(tmp)
        expected = sorted(
            p.relative_to(fresh) for p in dataset_files(fresh) if p.name != "marketforge.json"
        )
        same = 0
        for rel in expected:
            if (root / rel).is_file() and (root / rel).read_bytes() == (fresh / rel).read_bytes():
                same += 1
            elif (root / rel).is_file():
                click.echo(f"differs: {rel.as_posix()}")
            else:
                click.echo(f"missing: {rel.as_posix()}")
    for rel in sorted(set(ours) - set(expected)):
        click.echo(f"extra:   {rel.as_posix()}")
    ok = same == len(expected) and set(ours) == set(expected)
    click.secho(
        f"{same}/{len(expected)} files identical to a fresh generation",
        fg="green" if ok else "red",
        bold=True,
    )
    if not ok:
        raise click.exceptions.Exit(1)
