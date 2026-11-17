# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

"""Candles as Arrow data: schema, rounding and record batches."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pyarrow as pa

from marketforge.domain.bars import Bars
from marketforge.domain.regimes import RegimeType

PRICE_DECIMALS = 8
VOLUME_DECIMALS = 4

_PRICE_FIELDS = ("open", "high", "low", "close")

# The regime is written as its name ("trend_up"), dictionary-encoded on the
# regime codes, so files read back as the same categorical as in memory.
REGIME_NAMES = pa.array([r.value for r in RegimeType], pa.string())
REGIME_TYPE = pa.dictionary(pa.int8(), pa.string())


# A native time column (timestamps="datetime"): what Spark, DuckDB and polars read as time.
DATETIME_TYPE = pa.timestamp("s", tz="UTC")


def candle_schema(
    include_regime: bool, include_spread: bool = False, datetime: bool = False
) -> pa.Schema:
    """Arrow schema of written candles."""
    fields = [pa.field("timestamp", DATETIME_TYPE if datetime else pa.int64())]
    fields += [pa.field(c, pa.float64()) for c in (*_PRICE_FIELDS, "volume")]
    if include_spread:
        fields.append(pa.field("spread", pa.float64()))
    if include_regime:
        fields.append(pa.field("regime", REGIME_TYPE))
    return pa.schema(fields)


def rounded_columns(bars: Bars, columns: Sequence[int]) -> tuple[np.ndarray, list[np.ndarray]]:
    """
    Timestamps, and open/high/low/close/volume (and spread, when the candles
    have one) rounded for every requested column at once, transposed to (columns, rows) so that each instrument's
    values are contiguous.
    """
    cols = list(columns)
    every = cols == list(range(bars.open.shape[1]))

    def rounded(values: np.ndarray, decimals: int) -> np.ndarray:
        picked = values if every else values[:, cols]
        return np.ascontiguousarray(np.round(picked, decimals).T)

    fields = [rounded(getattr(bars, f), PRICE_DECIMALS) for f in _PRICE_FIELDS]
    fields.append(rounded(bars.volume, VOLUME_DECIMALS))
    if bars.spread is not None:
        fields.append(rounded(bars.spread, PRICE_DECIMALS))
    return np.ascontiguousarray(bars.timestamps, dtype=np.int64), fields


def record_batch(parts: list[tuple[np.ndarray, ...]], schema: pa.Schema) -> pa.RecordBatch:
    """One record batch from buffered (timestamps, o, h, l, c, v[, spread][, regime]) chunks."""
    arrays = []
    for k, field in enumerate(schema):
        chunk = [p[k] for p in parts]
        values = chunk[0] if len(chunk) == 1 else np.concatenate(chunk)
        if field.type == REGIME_TYPE:
            codes = pa.array(np.asarray(values, dtype=np.int8), pa.int8())
            arrays.append(pa.DictionaryArray.from_arrays(codes, REGIME_NAMES))
        else:
            arrays.append(pa.array(values, field.type))
    return pa.RecordBatch.from_arrays(arrays, schema=schema)
