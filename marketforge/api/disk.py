# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the MIT License. See the LICENSE file in the project
# root for full license information.

"""Datasets: candles streamed to CSV or Parquet files, and extended later."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from marketforge._version import __version__
from marketforge.api.execution import execute, warn_about_empty
from marketforge.api.parsing import Names, TimeLike, parse_time
from marketforge.api.planning import (
    DEFAULT_TIMEFRAMES,
    Checkpoint,
    MarketPlan,
    Request,
    plan_request,
)
from marketforge.config.overrides import Overrides
from marketforge.domain.bars import Bars
from marketforge.domain.markets import MarketType
from marketforge.domain.timeframes import Timeframe
from marketforge.output.file_limits import ensure_open_file_capacity
from marketforge.output.formats import OutputFormat
from marketforge.output.manifest import (
    Manifest,
    begin_extension,
    commit_extension,
    discard_manifest,
    iso_time,
    read_manifest,
    recover,
    write_manifest,
)
from marketforge.output.writer import CandleWriter


@dataclass
class DiskReport:
    """Result of :func:`generate_to_disk` and :func:`extend`."""

    seed: int
    paths: dict[str, dict[str, dict[str, Path]]] = field(
        default_factory=dict
    )  # market -> symbol -> tf -> path
    manifest: Path | None = None  # the dataset's marketforge.json

    @property
    def n_files(self) -> int:
        return sum(len(tfs) for syms in self.paths.values() for tfs in syms.values())


def generate_to_disk(
    output_dir: str | Path,
    instruments: Names | None = None,
    *,
    start: TimeLike,
    end: TimeLike,
    markets: Names | None = None,
    seed: int | None = None,
    timeframes: Names = DEFAULT_TIMEFRAMES,
    anomalies: Names = (),
    include_regime: bool = False,
    overrides: Overrides | None = None,
    fmt: str | OutputFormat = OutputFormat.CSV,
    jobs: int = 1,
    on_day: Callable[[MarketType], None] | None = None,
) -> DiskReport:
    """
    Generate a dataset: ``{output_dir}/{market}/{SYMBOL}_{tf}.{fmt}`` and a manifest.

    Takes the same arguments as :func:`generate` plus ``fmt`` (``csv`` or
    ``parquet``) and ``jobs`` (markets simulated in parallel). Memory use does
    not grow with the length of the range. The manifest (``marketforge.json``)
    records how the dataset was produced, so that it can be reproduced, and
    continued later with :func:`extend`.
    """
    request = plan_request(
        instruments,
        markets,
        start=start,
        end=end,
        seed=seed,
        timeframes=timeframes,
        anomalies=anomalies,
        include_regime=include_regime,
        overrides=overrides,
    )
    return write_request(request, output_dir, fmt=fmt, jobs=jobs, on_day=on_day)


def extend(
    dataset: str | os.PathLike[str],
    end: TimeLike,
    *,
    jobs: int = 1,
    on_day: Callable[[MarketType], None] | None = None,
) -> DiskReport:
    """
    Continue a dataset up to ``end``.

    The seed, instruments, timeframes, format and overrides are those of the
    dataset's manifest. Afterwards the dataset holds exactly the candles a
    single generation up to ``end`` would have produced.

    Raises:
        ValueError: if the directory is not a dataset, ``end`` is not after the
            dataset's end, or the dataset was written by another major version.
    """
    request, fmt = plan_extension(dataset, end)
    return write_request(request, dataset, fmt=fmt, jobs=jobs, on_day=on_day)


def plan_extension(dataset: str | os.PathLike[str], end: TimeLike) -> tuple[Request, OutputFormat]:
    """Resolve the extension of a dataset into a request and the dataset's format."""
    recover(dataset)
    manifest = read_manifest(dataset)
    if manifest.version.split(".")[0] != __version__.split(".")[0]:
        raise ValueError(
            f"{Path(dataset)} was written by MarketForge {manifest.version}; a seed's candles "
            f"differ between major versions, so {__version__} cannot extend it"
        )
    new_end = parse_time(end)
    if new_end <= manifest.end:
        raise ValueError(
            f"{Path(dataset)} already ends at {iso_time(manifest.end)}; an extension must end later"
        )
    request = plan_request(
        [symbol for symbols in manifest.instruments.values() for symbol in symbols],
        start=manifest.start,
        end=new_end,
        seed=manifest.seed,
        timeframes=manifest.timeframes,
        anomalies=manifest.anomalies,
        include_regime=manifest.include_regime,
        overrides=manifest.overrides,
    )
    request.extends_from = manifest.end
    for plan in request.plans:
        plan.resume = Checkpoint(**manifest.checkpoint[plan.market.value])
    return request, OutputFormat(manifest.format)


def write_request(
    request: Request,
    output_dir: str | os.PathLike[str],
    *,
    fmt: str | OutputFormat = OutputFormat.CSV,
    jobs: int = 1,
    on_day: Callable[[MarketType], None] | None = None,
) -> DiskReport:
    """Run an already resolved request (a new dataset or an extension) into ``output_dir``."""
    fmt = OutputFormat(fmt)
    root = Path(output_dir)
    extending = request.extends_from is not None
    if fmt == OutputFormat.PARQUET:
        n_files = sum(len(p.selected) for p in request.plans) * len(request.timeframes)
        ensure_open_file_capacity(n_files)
    if not extending:
        root.mkdir(parents=True, exist_ok=True)
        discard_manifest(root)
    writers = {
        plan.market: CandleWriter(
            root,
            plan.market.value,
            plan.selected,
            list(range(len(plan.selected))),
            request.timeframes,
            fmt,
            request.include_regime,
            extend=extending,
        )
        for plan in request.plans
    }
    if extending:
        files = [p for w in writers.values() for tfs in w.paths.values() for p in tfs.values()]
        begin_extension(root, files if fmt == OutputFormat.CSV else [])

    def write(plan: MarketPlan, tf: Timeframe, bars: Bars) -> None:
        writers[plan.market].write(tf, bars)

    report = DiskReport(seed=request.seed)

    def close_all() -> BaseException | None:
        # Close every writer even if one fails; return the first error.
        first: BaseException | None = None
        for market, writer in writers.items():
            try:
                paths = writer.close()
            except BaseException as e:
                first = first or e
                continue
            report.paths[market.value] = {s: dict(tfs) for s, tfs in paths.items()}
        return first

    try:
        checkpoints = execute(request, write, jobs=jobs, on_day=on_day)
    except BaseException:
        close_all()  # the generation error wins over any error while closing
        recover(root)  # an interrupted extension leaves the dataset as it was
        raise
    error = close_all()
    if error is not None:
        recover(root)
        raise error
    manifest = Manifest(
        version=__version__,
        seed=request.seed,
        start=request.start,
        end=request.end,
        format=fmt.value,
        timeframes=[tf.name for tf in request.timeframes],
        anomalies=sorted(request.anomalies),
        include_regime=request.include_regime,
        instruments={plan.market.value: plan.selected for plan in request.plans},
        overrides=request.overrides,
        checkpoint={
            market.value: {"day": c.day, "state": c.state, "written": c.written}
            for market, c in checkpoints.items()
        },
    )
    report.manifest = (commit_extension if extending else write_manifest)(root, manifest)
    if not extending:
        warn_about_empty(pair for writer in writers.values() for pair in writer.empty)
    return report
