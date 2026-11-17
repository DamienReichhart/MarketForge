# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

"""Datasets read back into memory, as :func:`generate` would have returned them."""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

from marketforge.api.memory import GeneratedData
from marketforge.api.parsing import Names, as_names, parse_timeframes
from marketforge.domain.regimes import RegimeType
from marketforge.output.manifest import read_manifest

_COLUMNS = ("open", "high", "low", "close", "volume", "spread", "regime")
_REGIMES = pd.CategoricalDtype([r.value for r in RegimeType])


def read(
    dataset: str | os.PathLike[str],
    instruments: Names | None = None,
    *,
    timeframes: Names | None = None,
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
    out = GeneratedData()
    out.seed = manifest.seed
    for symbol in wanted:
        for tf in tfs:
            path = root / owner[symbol] / f"{symbol}_{tf}.{manifest.format}"
            out.setdefault(symbol, {})[tf] = _frame(path, manifest.format)
    return out


def _frame(path: Path, fmt: str) -> pd.DataFrame:
    if fmt == "parquet":
        raw = pd.read_parquet(path)
    elif fmt == "feather":
        raw = pd.read_feather(path)
    else:
        raw = pd.read_csv(path)
    stamps = raw.pop("timestamp")
    if isinstance(stamps.dtype, pd.DatetimeTZDtype):
        index = pd.DatetimeIndex(stamps)
    elif pd.api.types.is_numeric_dtype(stamps):
        index = pd.to_datetime(stamps.to_numpy(), unit="s", utc=True)
    else:
        index = pd.to_datetime(stamps.to_numpy(), utc=True)
    frame = raw[[c for c in _COLUMNS if c in raw.columns]].copy()
    for column in frame.columns:
        if column == "regime":
            frame[column] = frame[column].astype(str).astype(_REGIMES)
        else:
            frame[column] = frame[column].astype("float64")
    frame.index = pd.DatetimeIndex(index.as_unit("s"), name="time")
    return frame
