# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

"""Candles in memory: what :func:`generate` and :func:`read` return."""

from __future__ import annotations

import difflib
import os
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any, overload

import numpy as np
import pandas as pd

from marketforge.api.parsing import Names, TimeLike, as_names, parse_time
from marketforge.domain.markets import MarketType
from marketforge.domain.regimes import RegimeType
from marketforge.domain.timeframes import Timeframe

if TYPE_CHECKING:
    from marketforge.api.disk import DiskReport

_REGIMES = [r.value for r in RegimeType]


@dataclass(frozen=True)
class Origin:
    """How a :class:`GeneratedData` was produced, enough to write it as a dataset.

    ``checkpoint`` is where each market's simulation resumes; a result cut in
    time by :meth:`GeneratedData.between` has none and cannot be saved.
    """

    version: str
    model_revision: int
    start: int  # Unix seconds, inclusive
    end: int  # Unix seconds, exclusive
    anomalies: tuple[str, ...] = ()
    overrides: dict[str, dict[str, Any]] = field(default_factory=dict)
    checkpoint: dict[str, dict[str, Any]] | None = None


def _timeframe_name(key: str) -> str:
    try:
        return Timeframe.from_string(str(key)).name
    except ValueError:
        raise KeyError(
            f"{key!r} is not a timeframe; valid: {', '.join(t.name for t in Timeframe)}"
        ) from None


def _missing(kind: str, key: str, available: Sequence[str]) -> KeyError:
    close = difflib.get_close_matches(key, list(available), n=1, cutoff=0.6)
    hint = f" (did you mean {close[0]}?)" if close else ""
    return KeyError(f"No {kind} {key}{hint}; this data holds {', '.join(available) or 'none'}")


class InstrumentData(Mapping[str, pd.DataFrame]):
    """One instrument's candles: ``{timeframe: DataFrame}``, read-only.

    Timeframe keys ignore letter case (``data["EURUSD"]["h1"]``).
    """

    __slots__ = ("_frames", "market", "symbol")

    def __init__(self, symbol: str, market: str, frames: Mapping[str, pd.DataFrame]) -> None:
        self.symbol = symbol
        self.market = market
        self._frames = dict(frames)

    @property
    def timeframes(self) -> tuple[str, ...]:
        """The timeframes held, shortest first."""
        return tuple(self._frames)

    def frame(self, timeframe: str) -> pd.DataFrame:
        """The candles of one timeframe."""
        return self[timeframe]

    def __getitem__(self, timeframe: str) -> pd.DataFrame:
        name = _timeframe_name(timeframe)
        try:
            return self._frames[name]
        except KeyError:
            raise _missing("timeframe", f"{name} for {self.symbol}", self.timeframes) from None

    def __iter__(self) -> Iterator[str]:
        return iter(self._frames)

    def __len__(self) -> int:
        return len(self._frames)

    def __contains__(self, timeframe: object) -> bool:
        try:
            return _timeframe_name(str(timeframe)) in self._frames
        except KeyError:
            return False

    __hash__ = None  # type: ignore[assignment]

    def __eq__(self, other: object) -> bool:
        return self is other

    def __repr__(self) -> str:
        rows = ", ".join(f"{tf}: {len(f):,}" for tf, f in self._frames.items())
        return f"<InstrumentData {self.symbol} ({self.market}) {rows}>"


class GeneratedData(Mapping[str, InstrumentData]):
    """
    Candles of several instruments: ``{symbol: {timeframe: DataFrame}}``, read-only.

    ``data["BTCUSD"]["m1"]``, ``data["BTCUSD", "m1"]`` and
    ``data.frame("BTCUSD", "m1")`` are the same DataFrame: a UTC
    ``DatetimeIndex`` named ``time`` and columns open, high, low, close,
    volume (and spread, bid, ask, regime when asked for). Symbols and
    timeframes ignore letter case. Iterating gives the symbols.
    """

    def __init__(
        self,
        frames: Mapping[str, Mapping[str, pd.DataFrame]],
        markets: Mapping[str, str],
        seed: int,
        origin: Origin,
    ) -> None:
        self._instruments = {
            symbol: InstrumentData(symbol, markets[symbol], tfs) for symbol, tfs in frames.items()
        }
        self._seed = int(seed)
        self._origin = origin

    # ------------------------------------------------------------ what it is
    @property
    def seed(self) -> int:
        """The seed that produced the candles."""
        return self._seed

    @property
    def start(self) -> pd.Timestamp:
        """Start of the range (inclusive), UTC."""
        return pd.Timestamp(self._origin.start, unit="s", tz="UTC")

    @property
    def end(self) -> pd.Timestamp:
        """End of the range (exclusive), UTC."""
        return pd.Timestamp(self._origin.end, unit="s", tz="UTC")

    @property
    def version(self) -> str:
        """The MarketForge version that produced the candles."""
        return self._origin.version

    @property
    def model_revision(self) -> int:
        """The model revision that produced the candles (``marketforge.MODEL_REVISION``)."""
        return self._origin.model_revision

    @property
    def symbols(self) -> tuple[str, ...]:
        """The instruments held, sorted."""
        return tuple(sorted(self._instruments))

    @property
    def markets(self) -> tuple[str, ...]:
        """The markets of the instruments held, in market order."""
        held = {i.market for i in self._instruments.values()}
        return tuple(m.value for m in MarketType if m.value in held)

    @property
    def timeframes(self) -> tuple[str, ...]:
        """Every timeframe held, shortest first."""
        held = {tf for i in self._instruments.values() for tf in i}
        return tuple(tf.name for tf in Timeframe if tf.name in held)

    @property
    def columns(self) -> tuple[str, ...]:
        """The candle columns (the same in every frame)."""
        for instrument in self._instruments.values():
            for frame in instrument.values():
                return tuple(frame.columns)
        return ()

    def market_of(self, symbol: str) -> str:
        """The market an instrument belongs to (``crypto``, ``forex`` or ``stocks``)."""
        return self.instrument(symbol).market

    # ---------------------------------------------------------------- getters
    def instrument(self, symbol: str) -> InstrumentData:
        """One instrument's candles, every timeframe."""
        key = str(symbol).strip().upper()
        try:
            return self._instruments[key]
        except KeyError:
            raise _missing("instrument", key, self.symbols) from None

    def frame(self, symbol: str, timeframe: str) -> pd.DataFrame:
        """The candles of one instrument and timeframe."""
        return self.instrument(symbol)[timeframe]

    def regime(self, market: str, timeframe: str) -> pd.Series:
        """The regime of a market at every candle of a timeframe (shared by its instruments)."""
        frame = self.frame(self._first_of(market), timeframe)
        if "regime" not in frame.columns:
            raise ValueError("The data has no regime column: generate it with with_regime=True")
        return frame["regime"]

    def spells(self, market: str) -> pd.DataFrame:
        """
        The regime spells of a market, as its candles show them.

        A spell is one uninterrupted stay in a regime. Read from the shortest
        timeframe held (m1 when it was generated): one row per spell with its
        ``start`` (first candle), ``end`` (end of the last candle), ``regime``,
        ``candles`` and ``duration`` (``end - start``, closures included).
        """
        timeframe = next(
            tf for tf in self.timeframes if tf in self.instrument(self._first_of(market))
        )
        labels = self.regime(market, timeframe)
        columns = ["start", "end", "regime", "candles", "duration"]
        if labels.empty:
            return pd.DataFrame(columns=columns)
        codes = labels.cat.codes.to_numpy()
        starts = np.flatnonzero(np.r_[True, codes[1:] != codes[:-1]])
        ends = np.r_[starts[1:], codes.size]
        step = pd.Timedelta(minutes=Timeframe[timeframe].minutes)
        index = labels.index
        out = pd.DataFrame(
            {
                "start": index[starts],
                "end": index[ends - 1] + step,
                "regime": pd.Categorical.from_codes(codes[starts], categories=_REGIMES),
                "candles": ends - starts,
            }
        )
        out["duration"] = out["end"] - out["start"]
        return out

    def _first_of(self, market: str) -> str:
        name = MarketType(str(market).strip().lower()).value
        for symbol in self.symbols:
            if self._instruments[symbol].market == name:
                return symbol
        raise _missing("market", name, self.markets)

    # -------------------------------------------------------------- narrowing
    def select(
        self,
        symbols: Names | None = None,
        *,
        markets: Names | None = None,
        timeframes: Names | None = None,
    ) -> GeneratedData:
        """A subset: only these instruments, markets and/or timeframes."""
        keep = [self.instrument(s).symbol for s in as_names(symbols)] or list(self.symbols)
        if markets is not None:
            wanted = {MarketType(m.lower()).value for m in as_names(markets)}
            keep = [s for s in keep if self._instruments[s].market in wanted]
        tfs = [_timeframe_name(t) for t in as_names(timeframes)] if timeframes is not None else None
        for tf in tfs or ():
            if tf not in self.timeframes:
                raise _missing("timeframe", tf, self.timeframes)
        frames = {
            s: {tf: f for tf, f in self._instruments[s].items() if tfs is None or tf in tfs}
            for s in keep
        }
        return GeneratedData(frames, self._market_map(), self._seed, self._origin)

    def between(self, start: TimeLike | None = None, end: TimeLike | None = None) -> GeneratedData:
        """
        The candles that start in ``[start, end)``; either bound may be omitted.

        The result cannot be :meth:`save`-d: it is no longer the output of a
        generation, so it could not be extended.
        """
        lo = self._origin.start if start is None else parse_time(start)
        hi = self._origin.end if end is None else parse_time(end)
        lo_ts, hi_ts = (pd.Timestamp(t, unit="s", tz="UTC") for t in (lo, hi))
        frames = {
            s: {tf: f[(f.index >= lo_ts) & (f.index < hi_ts)] for tf, f in i.items()}
            for s, i in self._instruments.items()
        }
        origin = replace(
            self._origin,
            start=max(lo, self._origin.start),
            end=min(hi, self._origin.end),
            checkpoint=None,
        )
        return GeneratedData(frames, self._market_map(), self._seed, origin)

    def copy(self) -> GeneratedData:
        """A new container over the same frames (copy a frame to change it)."""
        return GeneratedData(
            {s: dict(i.items()) for s, i in self._instruments.items()},
            self._market_map(),
            self._seed,
            self._origin,
        )

    # ------------------------------------------------------------------ views
    def panel(self, column: str = "close", timeframe: str | None = None) -> pd.DataFrame:
        """
        One column of every instrument side by side, for one timeframe.

        Args:
            column: ``open``, ``high``, ``low``, ``close``, ``volume`` or any other
                column the frames have.
            timeframe: Which timeframe; may be omitted when only one is held.

        Returns:
            A DataFrame with one column per instrument. Its index is the union of
            the instruments' candle times, so a value is NaN where that
            instrument's market was closed; nothing is forward-filled.
        """
        name = self._timeframe(timeframe)
        return pd.concat(
            {s: self.frame(s, name)[column] for s in self.symbols}, axis=1, sort=True
        ).rename_axis(columns="symbol")

    def to_long(self, timeframe: str | None = None) -> pd.DataFrame:
        """
        Every instrument of one timeframe in one frame, indexed by (symbol, time).

        The long format most data and ML tooling expects; ``.loc[symbol]`` gives
        back that instrument's frame. ``timeframe`` may be omitted when only one
        is held.
        """
        name = self._timeframe(timeframe)
        return pd.concat({s: self.frame(s, name) for s in self.symbols}, names=["symbol", "time"])

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
        symbols = list(self.symbols)
        index = pd.DatetimeIndex(
            sorted(set().union(*(self.frame(s, name).index for s in symbols))), name="time"
        )
        out = np.full((len(index), len(symbols), len(columns)), np.nan)
        for j, symbol in enumerate(symbols):
            frame = self.frame(symbol, name)
            rows = index.get_indexer(frame.index)
            for k, column in enumerate(columns):
                values = frame[column]
                if isinstance(values.dtype, pd.CategoricalDtype):
                    values = values.cat.codes
                out[rows, j, k] = values.to_numpy(dtype=float)
        return out, index, symbols

    def summary(self) -> pd.DataFrame:
        """One row per instrument and timeframe: market, candles, first and last candle."""
        rows = [
            {
                "symbol": s,
                "timeframe": tf,
                "market": i.market,
                "candles": len(f),
                "first": f.index[0] if len(f) else pd.NaT,
                "last": f.index[-1] if len(f) else pd.NaT,
            }
            for s in self.symbols
            for i in (self._instruments[s],)
            for tf, f in i.items()
        ]
        return pd.DataFrame(rows).set_index(["symbol", "timeframe"])

    # -------------------------------------------------------------------- out
    def save(
        self,
        path: str | os.PathLike[str],
        *,
        format: str = "csv",
        timestamps: str = "unix",
        overwrite: bool = False,
    ) -> DiskReport:
        """
        Write the candles as a dataset, with a manifest, as :func:`generate_to_disk` would.

        The files are those ``generate_to_disk`` writes for the same settings,
        so the dataset can be continued with :func:`extend` and checked with
        :func:`verify`. A result of :func:`read` can be saved in another
        format this way.

        Raises:
            ValueError: if the data was cut with :meth:`between`.
            FileExistsError: if ``path`` holds a dataset and ``overwrite`` is false.
        """
        from marketforge.api.disk import save_data  # disk imports this module

        return save_data(self, path, format=format, timestamps=timestamps, overwrite=overwrite)

    @property
    def origin(self) -> Origin:
        """How the data was produced (for writing it as a dataset)."""
        return self._origin

    # ------------------------------------------------------------- internals
    def _market_map(self) -> dict[str, str]:
        return {s: i.market for s, i in self._instruments.items()}

    def _timeframe(self, timeframe: str | None) -> str:
        available = self.timeframes
        if timeframe is None:
            if len(available) != 1:
                raise ValueError(f"Choose a timeframe: {', '.join(available)}")
            return available[0]
        name = _timeframe_name(timeframe)
        if name not in available:
            raise ValueError(f"Timeframe {name} is not held; available: {', '.join(available)}")
        return name

    @overload
    def __getitem__(self, key: str) -> InstrumentData: ...
    @overload
    def __getitem__(self, key: tuple[str, str]) -> pd.DataFrame: ...  # type: ignore[overload-overlap]
    def __getitem__(self, key: str | tuple[str, str]) -> InstrumentData | pd.DataFrame:  # type: ignore[override]
        if isinstance(key, tuple):
            symbol, timeframe = key
            return self.frame(symbol, timeframe)
        return self.instrument(key)

    def __iter__(self) -> Iterator[str]:
        return iter(self.symbols)

    def __len__(self) -> int:
        return len(self._instruments)

    def __contains__(self, symbol: object) -> bool:
        return isinstance(symbol, str) and symbol.strip().upper() in self._instruments

    __hash__ = None  # type: ignore[assignment]

    def __eq__(self, other: object) -> bool:
        return self is other

    def __repr__(self) -> str:
        span = f"{self.start:%Y-%m-%d %H:%M} -> {self.end:%Y-%m-%d %H:%M} UTC"
        lines = [
            f"<GeneratedData seed={self.seed}, {span}, MarketForge {self.version}",
            f"  timeframes {', '.join(self.timeframes)}",
            f"  columns    {', '.join(self.columns)}",
        ]
        for market in self.markets:
            held = [s for s in self.symbols if self._instruments[s].market == market]
            shown = ", ".join(held[:8]) + (f" and {len(held) - 8} more" if len(held) > 8 else "")
            first = self._instruments[held[0]]
            m1 = next(iter(first.values()), None)
            rows = f", {len(m1):,} {first.timeframes[0]} candles each" if m1 is not None else ""
            lines.append(f"  {market:<10} {len(held)} instrument(s){rows}: {shown}")
        return "\n".join(lines) + ">"
