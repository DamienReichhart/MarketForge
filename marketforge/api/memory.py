# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

"""Candles in memory, as pandas DataFrames."""

from __future__ import annotations

import multiprocessing
import os
from collections.abc import Iterable, Iterator, Sequence
from concurrent.futures import ProcessPoolExecutor
from functools import partial
from typing import Any

import numpy as np
import pandas as pd

from marketforge.api.execution import execute, warn_about_empty
from marketforge.api.parsing import Names, TimeLike
from marketforge.api.planning import MarketPlan, plan_request
from marketforge.config.overrides import Overrides
from marketforge.domain.bars import Bars
from marketforge.domain.markets import MarketType
from marketforge.domain.regimes import RegimeType
from marketforge.domain.timeframes import Timeframe


class GeneratedData(dict):
    """``{symbol: {timeframe: DataFrame}}`` plus the seed that produced it."""

    seed: int

    def panel(self, column: str = "close", timeframe: str | None = None) -> pd.DataFrame:
        """
        One column of every instrument side by side, for one timeframe.

        Args:
            column: ``open``, ``high``, ``low``, ``close``, ``volume`` or any other
                column the frames have.
            timeframe: Which timeframe; may be omitted when only one was generated.

        Returns:
            A DataFrame with one column per instrument. Its index is the union of
            the instruments' candle times, so a value is NaN where that
            instrument's market was closed; nothing is forward-filled.
        """
        name = self._timeframe(timeframe)
        return pd.concat(
            {symbol: frames[name][column] for symbol, frames in self.items()}, axis=1, sort=True
        )

    def to_long(self, timeframe: str | None = None) -> pd.DataFrame:
        """
        Every instrument of one timeframe in one frame, indexed by (symbol, time).

        The long format most data and ML tooling expects; ``.loc[symbol]`` gives
        back that instrument's frame. ``timeframe`` may be omitted when only one
        was generated.
        """
        name = self._timeframe(timeframe)
        return pd.concat(
            {symbol: frames[name] for symbol, frames in self.items()}, names=["symbol", "time"]
        )

    def to_numpy(
        self,
        timeframe: str | None = None,
        columns: Sequence[str] = ("open", "high", "low", "close", "volume"),
    ) -> tuple[np.ndarray, pd.DatetimeIndex, list[str]]:
        """
        One timeframe as a (time, instrument, column) float array, for tensors.

        The time axis is the union of every instrument's candle times; a value
        is NaN where that instrument's market was closed. The regime column
        gives its codes (0 trend_up ... 4 crash).

        Returns:
            (array, index, symbols): the array, its time axis and its instrument axis.
        """
        name = self._timeframe(timeframe)
        symbols = list(self)
        index = pd.DatetimeIndex(
            sorted(set().union(*(self[s][name].index for s in symbols))), name="time"
        )
        out = np.full((len(index), len(symbols), len(columns)), np.nan)
        for j, symbol in enumerate(symbols):
            frame = self[symbol][name]
            rows = index.get_indexer(frame.index)
            for k, column in enumerate(columns):
                values = frame[column]
                if isinstance(values.dtype, pd.CategoricalDtype):
                    values = values.cat.codes
                out[rows, j, k] = values.to_numpy(dtype=float)
        return out, index, symbols

    def _timeframe(self, timeframe: str | None) -> str:
        available = list(dict.fromkeys(tf for frames in self.values() for tf in frames))
        if timeframe is None:
            if len(available) != 1:
                raise ValueError(f"Choose a timeframe: {', '.join(available)}")
            return str(available[0])
        name = Timeframe.from_string(timeframe).name
        if name not in available:
            raise ValueError(
                f"Timeframe {name} was not generated; available: {', '.join(available)}"
            )
        return name


def generate(
    instruments: Names | None = None,
    *,
    start: TimeLike,
    end: TimeLike | None = None,
    days: int | None = None,
    markets: Names | None = None,
    seed: int | None = None,
    timeframes: Names = ("m1",),
    anomalies: Names = (),
    include_regime: bool = False,
    include_spread: bool = False,
    include_bid_ask: bool = False,
    overrides: Overrides | None = None,
) -> GeneratedData:
    """
    Generate candles in memory.

    Args:
        instruments: Instruments to return (e.g. ``["EURUSD", "AAPL"]``). If omitted,
            every instrument of ``markets`` (default: all markets).
        start, end: Range ``[start, end)`` as Unix seconds, ISO 8601 strings or
            date/datetime objects (naive = UTC).
        days: Length of the range in days, instead of ``end``.
        markets: Restrict to these markets (``crypto``, ``forex``, ``stocks``).
        seed: Non-negative integer; the same seed returns identical candles.
            If omitted a random seed is chosen and exposed as ``result.seed``.
        timeframes: Any of m1, m2, m3, m5, m10, m15, m20, m30, H1, H2, H3, H4,
            H6, H8, H12, D1, W1.
        anomalies: Optional ``spikes`` and/or ``flash_crash``.
        include_regime: Add a ``regime`` column (market regime name at candle close).
        include_spread: Add a ``spread`` column: the mean quoted bid-ask spread
            over the candle, in price units. ``open``, ``high``, ``low`` and
            ``close`` are mid prices, so bid = price - spread / 2.
        include_bid_ask: Add ``bid`` and ``ask`` columns: the quotes around the
            close, ``close -+ spread / 2``.
        overrides: Path to a TOML override file, or the same content as
            ``{SYMBOL: {key: value}}`` (custom prices, new instruments).

    Returns:
        :class:`GeneratedData` mapping symbol -> timeframe -> DataFrame with a
        UTC ``DatetimeIndex`` named ``time`` and columns open, high, low, close,
        volume (and spread, regime).
    """
    request = plan_request(
        instruments,
        markets,
        start=start,
        end=end,
        days=days,
        seed=seed,
        timeframes=timeframes,
        anomalies=anomalies,
        include_regime=include_regime,
        include_spread=include_spread,
        include_bid_ask=include_bid_ask,
        overrides=overrides,
    )
    parts: dict[tuple[MarketType, Timeframe], list[Bars]] = {}

    def collect(plan: MarketPlan, tf: Timeframe, bars: Bars) -> None:
        parts.setdefault((plan.market, tf), []).append(bars)

    execute(request, collect)
    out = GeneratedData()
    out.seed = request.seed
    for plan in request.plans:
        for tf in request.timeframes:
            chunks = parts.get((plan.market, tf))
            frames = _frames(
                chunks or [],
                len(plan.selected),
                request.include_regime,
                request.include_spread,
                request.include_bid_ask,
            )
            for symbol, frame in zip(plan.selected, frames, strict=True):
                out.setdefault(symbol, {})[tf.name] = frame
    warn_about_empty(
        (symbol, name) for symbol, frames in out.items() for name, f in frames.items() if f.empty
    )
    return out


def generate_many(
    instruments: Names | None = None,
    *,
    seeds: Iterable[int],
    jobs: int | None = None,
    **kwargs: Any,
) -> Iterator[GeneratedData]:
    """
    :func:`generate` once per seed, in parallel processes, yielding in seed order.

    Disjoint seeds give paths that share nothing: train, validation and test
    sets, or the hundreds of alternative histories of a stress test. Results
    are yielded as they are ready, in the order of ``seeds``, so only a few are
    in memory at once; each is exactly what ``generate(..., seed=s)`` returns.

    Args:
        instruments: As for :func:`generate`.
        seeds: The seeds, one generation each.
        jobs: Processes to use (default: the CPU count). Each process compiles
            the kernels once (a couple of seconds on a cold cache).
        **kwargs: Every other argument of :func:`generate` except ``seed``.
    """
    if "seed" in kwargs:
        raise TypeError("generate_many() takes seeds=, not seed=")
    seeds = [int(s) for s in seeds]
    workers = max(1, min(jobs or os.cpu_count() or 1, len(seeds)))
    run = partial(_generate_seed, instruments, kwargs)
    if workers == 1:
        yield from map(run, seeds)
        return
    with ProcessPoolExecutor(workers, mp_context=multiprocessing.get_context("spawn")) as pool:
        yield from pool.map(run, seeds)


def _generate_seed(instruments: Names | None, kwargs: dict[str, Any], seed: int) -> GeneratedData:
    data = generate(instruments, seed=seed, **kwargs)
    return data


_FRAME_COLUMNS = ("open", "high", "low", "close", "volume")


def _frames(
    chunks: list[Bars],
    n_instruments: int,
    include_regime: bool,
    include_spread: bool,
    include_bid_ask: bool = False,
) -> list[pd.DataFrame]:
    """
    One DataFrame per instrument from a market's candle chunks.

    The values are copied once, straight from the chunks into an
    (instrument, column, row) block; each frame then wraps its own slice
    without another copy, and all frames share one (immutable) time index.
    """
    columns = (*_FRAME_COLUMNS, "spread") if include_spread or include_bid_ask else _FRAME_COLUMNS
    n = sum(len(c) for c in chunks)
    block = np.empty((n_instruments, len(columns), n))
    ts = np.empty(n, dtype=np.int64)
    regime = np.empty(n, dtype=np.int8)
    row = 0
    for c in chunks:
        k = len(c)
        for i, name in enumerate(columns):
            block[:, i, row : row + k] = getattr(c, name).T
        ts[row : row + k] = c.timestamps
        regime[row : row + k] = c.regime
        row += k
    index = pd.DatetimeIndex(pd.to_datetime(ts, unit="s", utc=True), name="time")
    codes = regime.astype(int)
    frames = []
    for j in range(n_instruments):
        df = pd.DataFrame(block[j].T, index=index, columns=list(columns), copy=False)
        if include_bid_ask:
            half = df["spread"] / 2
            df["bid"] = df["close"] - half
            df["ask"] = df["close"] + half
            if not include_spread:
                df = df.drop(columns="spread")
        if include_regime:
            df["regime"] = pd.Categorical.from_codes(
                codes, categories=[r.value for r in RegimeType]
            )
        frames.append(df)
    return frames
