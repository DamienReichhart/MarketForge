# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the MIT License. See the LICENSE file in the project
# root for full license information.

"""Candles in memory, as pandas DataFrames."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from marketforge.api.execution import execute, warn_about_empty
from marketforge.api.parsing import Names, TimeLike
from marketforge.api.planning import MarketPlan, plan_request
from marketforge.domain.bars import Bars
from marketforge.domain.markets import MarketType
from marketforge.domain.regimes import RegimeType
from marketforge.domain.timeframes import Timeframe


class GeneratedData(dict):
    """``{symbol: {timeframe: DataFrame}}`` plus the seed that produced it."""

    seed: int


def generate(
    instruments: Names | None = None,
    *,
    start: TimeLike,
    end: TimeLike,
    markets: Names | None = None,
    seed: int | None = None,
    timeframes: Names = ("m1",),
    anomalies: Names = (),
    include_regime: bool = False,
    overrides: str | Path | None = None,
) -> GeneratedData:
    """
    Generate candles in memory.

    Args:
        instruments: Instruments to return (e.g. ``["EURUSD", "AAPL"]``). If omitted,
            every instrument of ``markets`` (default: all markets).
        start, end: Range ``[start, end)`` as Unix seconds, ISO 8601 strings or
            date/datetime objects (naive = UTC).
        markets: Restrict to these markets (``crypto``, ``forex``, ``stocks``).
        seed: Non-negative integer; the same seed returns identical candles.
            If omitted a random seed is chosen and exposed as ``result.seed``.
        timeframes: Any of m1, m5, m15, m30, H1, H4, D1, W1.
        anomalies: Optional ``spikes`` and/or ``flash_crash``.
        include_regime: Add a ``regime`` column (market regime name at candle close).
        overrides: Path to a TOML override file (custom prices, new instruments).

    Returns:
        :class:`GeneratedData` mapping symbol -> timeframe -> DataFrame with a
        UTC ``DatetimeIndex`` named ``time`` and columns open, high, low, close,
        volume (and regime).
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
    parts: dict[tuple[MarketType, Timeframe], list[Bars]] = {}

    def collect(plan: MarketPlan, tf: Timeframe, bars: Bars | None) -> None:
        if bars is not None and len(bars):
            parts.setdefault((plan.market, tf), []).append(bars)

    execute(request, collect)
    out = GeneratedData()
    out.seed = request.seed
    for plan in request.plans:
        for tf in request.timeframes:
            chunks = parts.get((plan.market, tf))
            frames = _frames(chunks or [], len(plan.selected), request.include_regime)
            for symbol, frame in zip(plan.selected, frames, strict=True):
                out.setdefault(symbol, {})[tf.name] = frame
    warn_about_empty(
        (symbol, name) for symbol, frames in out.items() for name, f in frames.items() if f.empty
    )
    return out


_FRAME_COLUMNS = ("open", "high", "low", "close", "volume")


def _frames(chunks: list[Bars], n_instruments: int, include_regime: bool) -> list[pd.DataFrame]:
    """
    One DataFrame per instrument from a market's candle chunks.

    The values are copied once, straight from the chunks into an
    (instrument, column, row) block; each frame then wraps its own slice
    without another copy, and all frames share one (immutable) time index.
    """
    n = sum(len(c) for c in chunks)
    block = np.empty((n_instruments, len(_FRAME_COLUMNS), n))
    ts = np.empty(n, dtype=np.int64)
    regime = np.empty(n, dtype=np.int8)
    row = 0
    for c in chunks:
        k = len(c)
        for i, name in enumerate(_FRAME_COLUMNS):
            block[:, i, row : row + k] = getattr(c, name).T
        ts[row : row + k] = c.timestamps
        regime[row : row + k] = c.regime
        row += k
    index = pd.DatetimeIndex(pd.to_datetime(ts, unit="s", utc=True), name="time")
    codes = regime.astype(int)
    frames = []
    for j in range(n_instruments):
        df = pd.DataFrame(block[j].T, index=index, columns=list(_FRAME_COLUMNS), copy=False)
        if include_regime:
            df["regime"] = pd.Categorical.from_codes(
                codes, categories=[r.value for r in RegimeType]
            )
        frames.append(df)
    return frames
