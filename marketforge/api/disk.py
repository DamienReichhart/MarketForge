# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

"""Datasets: candles streamed to CSV or Parquet files, and extended later."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from marketforge._version import MODEL_REVISION, __version__
from marketforge.api.data import GeneratedData
from marketforge.api.execution import NothingGenerated, execute, warn_about_empty
from marketforge.api.memory import checkpoint_doc
from marketforge.api.parsing import (
    Names,
    TimeLike,
    parse_format,
    parse_time,
    parse_timestamps,
    range_end,
)
from marketforge.api.planning import (
    Checkpoint,
    MarketPlan,
    Request,
    plan_request,
)
from marketforge.api.renamed import renamed_arguments
from marketforge.config.overrides import Overrides
from marketforge.domain.bars import Bars
from marketforge.domain.markets import MarketType
from marketforge.domain.timeframes import Timeframe
from marketforge.output.file_limits import ensure_open_file_capacity
from marketforge.output.formats import OutputFormat, TimestampFormat, check_formats
from marketforge.output.manifest import (
    Manifest,
    begin_extension,
    clear_dataset,
    commit_extension,
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


@renamed_arguments
def generate_to_disk(
    output_dir: str | Path,
    instruments: Names | None = None,
    *,
    start: TimeLike,
    end: TimeLike | None = None,
    days: int | None = None,
    markets: Names | None = None,
    seed: int | None = None,
    timeframes: Names | None = None,
    anomalies: Names = (),
    with_regime: bool = False,
    with_spread: bool = False,
    with_bid_ask: bool = False,
    overrides: Overrides | None = None,
    format: str | OutputFormat = OutputFormat.CSV,
    timestamps: str | TimestampFormat = TimestampFormat.UNIX,
    jobs: int | None = None,
    on_day: Callable[[MarketType], None] | None = None,
    overwrite: bool = False,
) -> DiskReport:
    """
    Generate a dataset: ``{output_dir}/{market}/{SYMBOL}_{tf}.{format}`` and a manifest.

    Takes the same arguments as :func:`generate` plus ``format`` (``csv``,
    ``parquet`` or ``feather``), ``timestamps`` (``unix`` seconds; ``iso`` 8601
    in CSV files; ``datetime``, a native UTC time column, in Parquet and
    Feather files) and ``jobs`` (markets simulated in parallel; default one
    per market, up to the CPU count, as on the command line). Memory use does
    not grow with the length of the range. The manifest (``marketforge.json``)
    records how the dataset was produced, so that it can be reproduced, and
    continued later with :func:`extend`.

    A directory that already holds a dataset (a manifest, or candle files left
    by an interrupted run) is refused, so two datasets never mix, unless
    ``overwrite`` is true: then the old dataset's files are deleted first.
    Files MarketForge did not write are left alone.

    Raises:
        FileExistsError: if ``output_dir`` holds a dataset and ``overwrite`` is false.
    """
    fmt, stamps = parse_format(format), parse_timestamps(timestamps)
    check_formats(fmt, stamps)
    request = plan_request(
        instruments,
        markets,
        start=start,
        end=end,
        days=days,
        seed=seed,
        timeframes=timeframes,
        anomalies=anomalies,
        include_regime=with_regime,
        include_spread=with_spread,
        include_bid_ask=with_bid_ask,
        overrides=overrides,
    )
    return write_request(
        request,
        output_dir,
        fmt=fmt,
        timestamps=stamps,
        jobs=default_jobs(request, jobs),
        on_day=on_day,
        overwrite=overwrite,
    )


def default_jobs(request: Request, jobs: int | None) -> int:
    """The markets to simulate in parallel: ``jobs``, or one per market up to the CPU count."""
    return jobs or min(len(request.plans), os.cpu_count() or 1)


def extend(
    dataset: str | os.PathLike[str],
    end: TimeLike | None = None,
    *,
    days: int | None = None,
    jobs: int | None = None,
    on_day: Callable[[MarketType], None] | None = None,
) -> DiskReport:
    """
    Continue a dataset up to ``end``, or by ``days`` days.

    The seed, instruments, timeframes, format and overrides are those of the
    dataset's manifest. Afterwards the dataset holds exactly the candles a
    single generation up to the new end would have produced.

    Raises:
        ValueError: if the directory is not a dataset, the new end is not after
            the dataset's end, or the dataset was written by another model revision.
    """
    new_end = range_end(read_manifest(dataset).end, end, days)
    request, fmt, timestamps = plan_extension(dataset, new_end)
    return write_request(
        request,
        dataset,
        fmt=fmt,
        timestamps=timestamps,
        jobs=default_jobs(request, jobs),
        on_day=on_day,
    )


def plan_extension(
    dataset: str | os.PathLike[str], end: TimeLike
) -> tuple[Request, OutputFormat, TimestampFormat]:
    """Resolve the extension of a dataset into a request and the dataset's file formats."""
    recover(dataset)
    manifest = read_manifest(dataset)
    if manifest.model_revision != MODEL_REVISION:
        raise ValueError(
            f"{Path(dataset)} was written by MarketForge {manifest.version} (model revision "
            f"{manifest.model_revision}); {__version__} has model revision {MODEL_REVISION} and "
            "produces different candles, so it cannot extend it. Generate the dataset again, "
            f"or install marketforge=={manifest.version}"
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
        include_spread=manifest.include_spread,
        include_bid_ask=manifest.include_bid_ask,
        overrides=manifest.overrides,
        allow_closed=True,
    )
    request.extends_from = manifest.end
    for plan in request.plans:
        plan.resume = Checkpoint(**manifest.checkpoint[plan.market.value])
    return request, OutputFormat(manifest.format), TimestampFormat(manifest.timestamps)


def write_request(
    request: Request,
    output_dir: str | os.PathLike[str],
    *,
    fmt: str | OutputFormat = OutputFormat.CSV,
    timestamps: str | TimestampFormat = TimestampFormat.UNIX,
    jobs: int = 1,
    on_day: Callable[[MarketType], None] | None = None,
    overwrite: bool = False,
) -> DiskReport:
    """Run an already resolved request (a new dataset or an extension) into ``output_dir``."""
    fmt = OutputFormat(fmt)
    timestamps = TimestampFormat(timestamps)
    root = Path(output_dir)
    extending = request.extends_from is not None
    if fmt != OutputFormat.CSV:
        n_files = sum(len(p.selected) for p in request.plans) * len(request.timeframes)
        ensure_open_file_capacity(n_files)
    if not extending:
        root.mkdir(parents=True, exist_ok=True)
        clear_dataset(root, overwrite=overwrite)
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
            include_spread=request.include_spread,
            include_bid_ask=request.include_bid_ask,
            timestamps=timestamps,
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
        model_revision=MODEL_REVISION,
        seed=request.seed,
        start=request.start,
        end=request.end,
        format=fmt.value,
        timestamps=timestamps.value,
        timeframes=[tf.name for tf in request.timeframes],
        anomalies=sorted(request.anomalies),
        include_regime=request.include_regime,
        include_spread=request.include_spread,
        include_bid_ask=request.include_bid_ask,
        instruments={plan.market.value: plan.selected for plan in request.plans},
        overrides=request.overrides,
        checkpoint=checkpoint_doc(checkpoints),
    )
    if not extending:
        try:
            warn_about_empty(
                (pair for writer in writers.values() for pair in writer.empty),
                total=report.n_files,
                named=request.timeframes_named,
            )
        except NothingGenerated:
            clear_dataset(root, overwrite=True)  # header-only files are not a dataset
            raise
    report.manifest = (commit_extension if extending else write_manifest)(root, manifest)
    return report


def save_data(
    data: GeneratedData,
    path: str | os.PathLike[str],
    *,
    format: str | OutputFormat = OutputFormat.CSV,
    timestamps: str | TimestampFormat = TimestampFormat.UNIX,
    overwrite: bool = False,
) -> DiskReport:
    """Write candles held in memory as a dataset (:meth:`GeneratedData.save`)."""
    origin = data.origin
    if origin.checkpoint is None:
        raise ValueError(
            "This data was cut in time with between(), so it is not the output of a generation "
            "and could not be extended: save the whole result, or write its frames yourself"
        )
    fmt, stamps = parse_format(format), parse_timestamps(timestamps)
    check_formats(fmt, stamps)
    columns = set(data.columns)
    with_regime, with_spread = "regime" in columns, "spread" in columns
    with_bid_ask = "bid" in columns
    timeframes = [Timeframe[name] for name in data.timeframes]
    by_market = {m: [s for s in data.symbols if data.market_of(s) == m] for m in data.markets}
    root = Path(path)
    root.mkdir(parents=True, exist_ok=True)
    clear_dataset(root, overwrite=overwrite)
    if fmt != OutputFormat.CSV:
        ensure_open_file_capacity(len(data.symbols) * len(timeframes))
    report = DiskReport(seed=data.seed)
    for market, symbols in by_market.items():
        writer = CandleWriter(
            root,
            market,
            symbols,
            list(range(len(symbols))),
            timeframes,
            fmt,
            with_regime,
            include_spread=with_spread,
            include_bid_ask=with_bid_ask,
            timestamps=stamps,
        )
        for tf in timeframes:
            writer.write(tf, _bars([data.frame(s, tf.name) for s in symbols]))
        report.paths[market] = {s: dict(tfs) for s, tfs in writer.close().items()}
    names = {tf.name for tf in timeframes}
    manifest = Manifest(
        version=origin.version,
        model_revision=origin.model_revision,
        seed=data.seed,
        start=origin.start,
        end=origin.end,
        format=fmt.value,
        timestamps=stamps.value,
        timeframes=[tf.name for tf in timeframes],
        anomalies=list(origin.anomalies),
        include_regime=with_regime,
        include_spread=with_spread,
        include_bid_ask=with_bid_ask,
        instruments=by_market,
        overrides=origin.overrides,
        checkpoint={
            market: {
                **origin.checkpoint[market],
                "written": {
                    tf: ts for tf, ts in origin.checkpoint[market]["written"].items() if tf in names
                },
            }
            for market in by_market
        },
    )
    report.manifest = write_manifest(root, manifest)
    return report


def _bars(frames: list[pd.DataFrame]) -> Bars:
    """One market's frames of one timeframe (same index) as the candles the writer takes."""
    first = frames[0]

    def stacked(column: str) -> np.ndarray:
        return np.column_stack([f[column].to_numpy(dtype=float) for f in frames])

    if "spread" in first.columns:
        spread: np.ndarray | None = stacked("spread")
    elif "bid" in first.columns:
        spread = stacked("ask") - stacked("bid")
    else:
        spread = None
    regime = (
        first["regime"].cat.codes.to_numpy(dtype=np.int8)
        if "regime" in first.columns
        else np.zeros(len(first), dtype=np.int8)
    )
    return Bars(
        timestamps=pd.DatetimeIndex(first.index).as_unit("s").asi8.astype(np.int64),
        open=stacked("open"),
        high=stacked("high"),
        low=stacked("low"),
        close=stacked("close"),
        volume=stacked("volume"),
        regime=regime,
        spread=spread,
    )
