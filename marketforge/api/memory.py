# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

"""Candles in memory, as pandas DataFrames."""

from __future__ import annotations

import multiprocessing
import os
from collections.abc import Iterable, Iterator, Mapping
from concurrent.futures import ProcessPoolExecutor
from functools import partial
from typing import Any

import numpy as np
import pandas as pd

from marketforge._version import MODEL_REVISION, __version__
from marketforge.api.data import GeneratedData, Origin
from marketforge.api.execution import execute, warn_about_empty
from marketforge.api.parsing import Names, TimeLike
from marketforge.api.planning import Checkpoint, MarketPlan, Request, plan_request
from marketforge.api.renamed import renamed_arguments
from marketforge.config.overrides import Overrides
from marketforge.domain.bars import Bars
from marketforge.domain.markets import MarketType
from marketforge.domain.regimes import RegimeType
from marketforge.domain.timeframes import Timeframe


@renamed_arguments
def generate(
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
            H6, H8, H12, D1, W1, or ``"all"`` of them. Default: the eight
            standard ones, m1, m5, m15, m30, H1, H4, D1 and W1.
        anomalies: Optional ``spikes`` and/or ``flash_crash``.
        with_regime: Add a ``regime`` column (market regime name at candle close).
        with_spread: Add a ``spread`` column: the mean quoted bid-ask spread
            over the candle, in price units. ``open``, ``high``, ``low`` and
            ``close`` are mid prices, so bid = price - spread / 2.
        with_bid_ask: Add ``bid`` and ``ask`` columns: the quotes around the
            close, ``close -+ spread / 2``.
        overrides: Path to a TOML override file, or the same content as
            ``{SYMBOL: {key: value}}`` (custom prices, new instruments).

    Returns:
        :class:`GeneratedData`: symbol -> timeframe -> DataFrame with a UTC
        ``DatetimeIndex`` named ``time`` and columns open, high, low, close,
        volume (and spread, bid, ask, regime).

    Raises:
        ValueError: on unknown names, an invalid range, or a range in which
            nothing can be generated.
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
        include_regime=with_regime,
        include_spread=with_spread,
        include_bid_ask=with_bid_ask,
        overrides=overrides,
    )
    parts: dict[tuple[MarketType, Timeframe], list[Bars]] = {}

    def collect(plan: MarketPlan, tf: Timeframe, bars: Bars) -> None:
        parts.setdefault((plan.market, tf), []).append(bars)

    checkpoints = execute(request, collect)
    frames: dict[str, dict[str, pd.DataFrame]] = {}
    owners: dict[str, str] = {}
    for plan in request.plans:
        for tf in request.timeframes:
            chunks = parts.get((plan.market, tf))
            built = _frames(
                chunks or [],
                len(plan.selected),
                request.include_regime,
                request.include_spread,
                request.include_bid_ask,
            )
            for symbol, frame in zip(plan.selected, built, strict=True):
                frames.setdefault(symbol, {})[tf.name] = frame
                owners[symbol] = plan.market.value
    warn_about_empty(
        ((s, tf) for s, tfs in frames.items() for tf, f in tfs.items() if f.empty),
        total=sum(len(tfs) for tfs in frames.values()),
        named=request.timeframes_named,
    )
    return GeneratedData(frames, owners, request.seed, origin_of(request, checkpoints))


def origin_of(request: Request, checkpoints: Mapping[MarketType, Checkpoint]) -> Origin:
    """What a generation's result records about how it was made."""
    return Origin(
        version=__version__,
        model_revision=MODEL_REVISION,
        start=request.start,
        end=request.end,
        anomalies=tuple(sorted(request.anomalies)),
        overrides=request.overrides,
        checkpoint=checkpoint_doc(checkpoints),
    )


def checkpoint_doc(checkpoints: Mapping[MarketType, Checkpoint]) -> dict[str, dict[str, Any]]:
    """Checkpoints as the manifest stores them."""
    return {
        market.value: {"day": c.day, "state": c.state, "written": c.written}
        for market, c in checkpoints.items()
    }


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
        jobs: Processes to use. Default: one, when the whole run is estimated
            to take under ten seconds (starting processes would cost more than
            it saves), else the CPU count. Each process compiles the kernels
            once (a couple of seconds on a cold cache).
        **kwargs: Every other argument of :func:`generate` except ``seed``.

    In a script, call it under ``if __name__ == "__main__":``: worker
    processes import the script again, as with any Python multiprocessing.
    Notebooks and the REPL need nothing.
    """
    if "seed" in kwargs:
        raise TypeError("generate_many() takes seeds=, not seed=")
    seeds = [int(s) for s in seeds]
    if jobs is None:
        jobs = _default_jobs(instruments, kwargs, len(seeds))
    workers = max(1, min(jobs, len(seeds)))
    run = partial(_generate_seed, instruments, kwargs)
    if workers == 1:
        yield from map(run, seeds)
        return
    with ProcessPoolExecutor(workers, mp_context=multiprocessing.get_context("spawn")) as pool:
        yield from pool.map(run, seeds)


# Below this estimated total, one process beats a pool: each worker spends a
# second or more starting up and importing (or compiling) the kernels.
_SERIAL_SECONDS = 10.0


def _default_jobs(instruments: Names | None, kwargs: dict[str, Any], n_seeds: int) -> int:
    from marketforge.api.estimating import estimate  # estimating imports planning only

    keys = (
        "start",
        "end",
        "days",
        "markets",
        "timeframes",
        "with_regime",
        "with_spread",
        "with_bid_ask",
        "overrides",
        "anomalies",
    )
    per_seed = estimate(instruments, **{k: v for k, v in kwargs.items() if k in keys}).seconds
    if per_seed * n_seeds < _SERIAL_SECONDS:
        return 1
    return os.cpu_count() or 1


def _generate_seed(instruments: Names | None, kwargs: dict[str, Any], seed: int) -> GeneratedData:
    data = generate(instruments, seed=seed, **kwargs)
    return data


_FRAME_COLUMNS = ("open", "high", "low", "close", "volume")


def time_index(seconds: np.ndarray) -> pd.DatetimeIndex:
    """The candle index MarketForge returns: UTC, named ``time``, from Unix seconds.

    Every frame MarketForge builds (generated, read back or resampled) uses it,
    so their indexes always have the same dtype, whatever unit pandas picks.
    """
    stamps = np.asarray(seconds, dtype=np.int64)
    return pd.DatetimeIndex(pd.to_datetime(stamps, unit="s", utc=True), name="time")


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
    index = time_index(ts)
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
