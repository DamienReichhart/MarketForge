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
from marketforge.domain.ticks import TickGrid

PRICE_DECIMALS = 8
VOLUME_DECIMALS = 4

_PRICE_FIELDS = ("open", "high", "low", "close")

# The regime is written as its name ("trend_up"), dictionary-encoded on the
# regime codes, so files read back as the same categorical as in memory.
REGIME_NAMES = pa.array([r.value for r in RegimeType], pa.string())
REGIME_TYPE = pa.dictionary(pa.int8(), pa.string())


# A native time column (timestamps="datetime"): what Spark, DuckDB and polars read as time.
DATETIME_TYPE = pa.timestamp("s", tz="UTC")


# The long layout's symbol and market columns, dictionary-encoded.
SYMBOL_TYPE = pa.dictionary(pa.int16(), pa.string())
MARKET_TYPE = pa.dictionary(pa.int8(), pa.string())


def candle_schema(
    include_regime: bool,
    include_spread: bool = False,
    datetime: bool = False,
    include_bid_ask: bool = False,
    long: bool = False,
    metadata: dict[str, str] | None = None,
) -> pa.Schema:
    """Arrow schema of written candles; ``long`` adds the symbol and market columns."""
    fields = [pa.field("timestamp", DATETIME_TYPE if datetime else pa.int64())]
    if long:
        fields += [pa.field("symbol", SYMBOL_TYPE), pa.field("market", MARKET_TYPE)]
    fields += [pa.field(c, pa.float64()) for c in (*_PRICE_FIELDS, "volume")]
    if include_spread:
        fields.append(pa.field("spread", pa.float64()))
    if include_bid_ask:
        fields += [pa.field("bid", pa.float64()), pa.field("ask", pa.float64())]
    if include_regime:
        fields.append(pa.field("regime", REGIME_TYPE))
    return pa.schema(fields, metadata=metadata)


def rounded_columns(
    bars: Bars,
    columns: Sequence[int],
    include_spread: bool = True,
    include_bid_ask: bool = False,
    ticks: TickGrid | None = None,
) -> tuple[np.ndarray, list[np.ndarray]]:
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
    if bars.spread is not None and include_spread:
        fields.append(rounded(bars.spread, PRICE_DECIMALS))
    if include_bid_ask:
        if bars.spread is None:
            raise ValueError("bid and ask need the spread to be simulated")
        bid, ask = quotes(bars.close, bars.spread, ticks)
        fields.append(rounded(bid, PRICE_DECIMALS))
        fields.append(rounded(ask, PRICE_DECIMALS))
    return np.ascontiguousarray(bars.timestamps, dtype=np.int64), fields


def quotes(
    close: np.ndarray, spread: np.ndarray, ticks: TickGrid | None
) -> tuple[np.ndarray, np.ndarray]:
    """Bid and ask around the close: half the spread each way, outwards onto the tick grid."""
    half = spread / 2
    if ticks is None:
        return close - half, close + half
    return ticks.floor(close - half), ticks.ceil(close + half)


def record_batch(
    parts: list[tuple[np.ndarray, ...]],
    schema: pa.Schema,
    dictionaries: dict[str, pa.Array] | None = None,
) -> pa.RecordBatch:
    """
    One record batch from buffered chunks, one array per schema field in order.

    A dictionary-encoded field holds codes into ``dictionaries[name]`` (the
    regime's names are built in).
    """
    names = {"regime": REGIME_NAMES, **(dictionaries or {})}
    arrays = []
    for k, field in enumerate(schema):
        chunk = [p[k] for p in parts]
        values = chunk[0] if len(chunk) == 1 else np.concatenate(chunk)
        if pa.types.is_dictionary(field.type):
            index_type = field.type.index_type
            codes = pa.array(np.asarray(values, dtype=index_type.to_pandas_dtype()), index_type)
            arrays.append(pa.DictionaryArray.from_arrays(codes, names[field.name]))
        else:
            arrays.append(pa.array(values, field.type))
    return pa.RecordBatch.from_arrays(arrays, schema=schema)
