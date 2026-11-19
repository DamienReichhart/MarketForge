# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

"""Datasets read back into memory, as :func:`generate` would have returned them."""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.feather as feather
import pyarrow.parquet as pq

from marketforge.api.data import GeneratedData, Origin
from marketforge.api.memory import time_index
from marketforge.api.parsing import Names, TimeLike, as_names, parse_time, parse_timeframes
from marketforge.domain.regimes import RegimeType
from marketforge.output.manifest import Manifest, read_manifest

_COLUMNS = ("open", "high", "low", "close", "volume", "spread", "bid", "ask", "regime")
_REGIMES = pd.CategoricalDtype([r.value for r in RegimeType])


def read(
    dataset: str | os.PathLike[str],
    instruments: Names | None = None,
    *,
    timeframes: Names | None = None,
    start: TimeLike | None = None,
    end: TimeLike | None = None,
) -> GeneratedData:
    """
    Load a dataset written by :func:`generate_to_disk` into memory.

    Returns the same :class:`GeneratedData` that :func:`generate` returns for
    the dataset's settings: a UTC ``DatetimeIndex`` named ``time``, float
    columns, and the regime as a categorical. Values are those of the files,
    which round prices to 8 decimals and volumes to 4.

    Args:
        dataset: The dataset directory (it holds ``marketforge.json``).
        instruments: Only these instruments (default: all of the dataset's).
        timeframes: Only these timeframes (default: all of the dataset's).
        start, end: Only the candles that start in ``[start, end)``; Parquet
            and Feather files are filtered as they are read. A result read with
            either cannot be saved again (see :meth:`GeneratedData.between`).

    Raises:
        ValueError: if the directory is not a dataset, or holds no such
            instrument or timeframe.
    """
    root = Path(dataset)
    manifest = read_manifest(root)
    owner = {s: m for m, symbols in manifest.instruments.items() for s in symbols}
    wanted = [s.upper() for s in as_names(instruments)] or list(owner)
    missing = [s for s in wanted if s not in owner]
    if missing:
        raise ValueError(f"{', '.join(missing)} not in the dataset; it holds {', '.join(owner)}")
    if timeframes is None:
        tfs = list(manifest.timeframes)
    else:
        tfs = [tf.name for tf in parse_timeframes(timeframes)]
        absent = [tf for tf in tfs if tf not in manifest.timeframes]
        if absent:
            raise ValueError(
                f"Timeframe(s) {', '.join(absent)} not in the dataset; "
                f"it holds {', '.join(manifest.timeframes)}"
            )
    lo = None if start is None else parse_time(start)
    hi = None if end is None else parse_time(end)
    frames = {
        symbol: {
            tf: _frame(root / owner[symbol] / f"{symbol}_{tf}.{manifest.format}", manifest, lo, hi)
            for tf in tfs
        }
        for symbol in wanted
    }
    origin = Origin(
        version=manifest.version,
        model_revision=manifest.model_revision,
        start=manifest.start,
        end=manifest.end,
        anomalies=tuple(manifest.anomalies),
        overrides=manifest.overrides,
        checkpoint=manifest.checkpoint,
    )
    data = GeneratedData(frames, {s: owner[s] for s in wanted}, manifest.seed, origin)
    # Cut like between(), so a partial read cannot be saved as a whole dataset.
    return data if lo is None and hi is None else data.between(lo, hi)


def _frame(path: Path, manifest: Manifest, lo: int | None, hi: int | None) -> pd.DataFrame:
    fmt = manifest.format
    if fmt in ("parquet", "feather"):
        table = pq.read_table(path) if fmt == "parquet" else feather.read_table(path)
        if lo is not None or hi is not None:
            table = table.filter(_time_filter(table, lo, hi))
        raw = table.to_pandas()
    else:
        raw = pd.read_csv(path)
    stamps = raw.pop("timestamp")
    if pd.api.types.is_numeric_dtype(stamps):
        seconds = stamps.to_numpy(dtype=np.int64)
    else:  # an ISO string, or a native time column
        seconds = pd.DatetimeIndex(pd.to_datetime(stamps, utc=True)).as_unit("s").asi8
    frame = raw[[c for c in _COLUMNS if c in raw.columns]].copy()
    for column in frame.columns:
        if column == "regime":
            frame[column] = frame[column].astype(str).astype(_REGIMES)
        else:
            frame[column] = frame[column].astype("float64")
    frame.index = time_index(seconds)
    if fmt == "csv" and (lo is not None or hi is not None):
        keep = np.ones(len(frame), dtype=bool)
        if lo is not None:
            keep &= seconds >= lo
        if hi is not None:
            keep &= seconds < hi
        frame = frame[keep]
    return frame


def _time_filter(table: pa.Table, lo: int | None, hi: int | None) -> pc.Expression:
    column = pc.field("timestamp")
    native = pa.types.is_timestamp(table.schema.field("timestamp").type)

    def bound(seconds: int) -> pa.Scalar:
        return pa.scalar(seconds, pa.timestamp("s", tz="UTC")) if native else pa.scalar(seconds)

    condition = pc.scalar(True)
    if lo is not None:
        condition = condition & (column >= bound(lo))
    if hi is not None:
        condition = condition & (column < bound(hi))
    return condition
