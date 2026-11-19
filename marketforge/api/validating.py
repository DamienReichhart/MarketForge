# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

"""Checking m1 candles, generated or real, against a market's validation bands."""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd

from marketforge.config.loader import load_catalog
from marketforge.domain.markets import MarketType
from marketforge.domain.regimes import RegimeType
from marketforge.validation.report import ValidationReport, validate_ohlcv

_PRICES = ("open", "high", "low", "close")
# Below a week of stock sessions (5 x 390 minutes) the statistics are noise:
# a 30-minute file failed on kurtosis alone.
MIN_CANDLES = 1950


def validate(
    data: pd.DataFrame | str | os.PathLike[str], market: str | MarketType | None = None
) -> ValidationReport:
    """
    Check m1 candles against the stylized facts of a market.

    Args:
        data: A DataFrame with ``open``, ``high``, ``low`` and ``close`` columns
            (as returned by :func:`generate`), or the path of a CSV or Parquet
            candle file. A ``spread`` column, when present, is checked too.
        market: ``crypto``, ``forex`` or ``stocks``. May be omitted for a file
            written by MarketForge, whose path names the market or the instrument.

    Returns:
        A :class:`~marketforge.validation.report.ValidationReport`; ``report.passed``
        says whether every statistic is inside its band and ``report.summary()``
        explains it.

    Raises:
        ValueError: if the candles are not m1 (the bands only describe minute
            returns), fewer than :data:`MIN_CANDLES` (a week of stock
            sessions), a price column is missing, or the market is unknown.
    """
    if isinstance(data, pd.DataFrame):
        frame, source = data, "the DataFrame"
        if market is None:
            raise ValueError("market is required to validate a DataFrame")
    else:
        path = Path(data)
        if path.suffix == ".parquet":
            frame = pd.read_parquet(path)
        elif path.suffix in (".feather", ".arrow"):
            frame = pd.read_feather(path)
        else:
            frame = pd.read_csv(path)
        source = str(path)
        market = market or _market_of(path)
    try:
        market_type = MarketType(str(market).strip().lower())
    except ValueError:
        raise ValueError(
            f"Unknown market {market!r}; choose from {', '.join(m.value for m in MarketType)}"
        ) from None
    missing = [c for c in _PRICES if c not in frame.columns]
    if missing:
        raise ValueError(f"{source} lacks column(s): {', '.join(missing)}")
    if len(frame) < 2:
        raise ValueError(f"{source} holds {len(frame)} candle(s); nothing to validate")
    spacing = _minutes_between_candles(frame)
    if spacing is not None and spacing != 1:
        raise ValueError(
            f"{source} holds {spacing:g}-minute candles; the validation bands describe m1 "
            "candles only"
        )
    if len(frame) < MIN_CANDLES:
        raise ValueError(
            f"{source} holds {len(frame):,} candle(s); validation needs at least "
            f"{MIN_CANDLES:,} m1 candles (a week of stock sessions) for its statistics to mean "
            "anything"
        )
    open_, high, low, close = (frame[c].to_numpy() for c in _PRICES)
    spread = frame["spread"].to_numpy() if "spread" in frame.columns else None
    volume = frame["volume"].to_numpy(dtype=float) if "volume" in frame.columns else None
    return validate_ohlcv(
        open_,
        high,
        low,
        close,
        market_type,
        spread,
        volume=volume,
        gaps=_gaps(frame),
        regime=_regime_codes(frame),
    )


def _seconds(frame: pd.DataFrame) -> np.ndarray | None:
    if isinstance(frame.index, pd.DatetimeIndex):
        return np.asarray(frame.index.to_numpy("datetime64[s]").astype(np.int64))
    if "timestamp" not in frame.columns:
        return None
    if pd.api.types.is_numeric_dtype(frame["timestamp"]):
        return np.asarray(frame["timestamp"].to_numpy(dtype=np.int64))
    times = pd.to_datetime(frame["timestamp"], utc=True)
    return np.asarray(times.to_numpy("datetime64[s]").astype(np.int64))


def _gaps(frame: pd.DataFrame) -> np.ndarray | None:
    """The log moves from each close to the next open across a closure."""
    seconds = _seconds(frame)
    if seconds is None:
        return None
    after = np.flatnonzero(np.diff(seconds) > 60) + 1
    opens, closes = frame["open"].to_numpy(dtype=float), frame["close"].to_numpy(dtype=float)
    return np.asarray(np.log(opens[after] / closes[after - 1]))


def _regime_codes(frame: pd.DataFrame) -> np.ndarray | None:
    if "regime" not in frame.columns:
        return None
    labels = frame["regime"].astype(str)
    return np.asarray(pd.Categorical(labels, categories=[r.value for r in RegimeType]).codes)


def _market_of(path: Path) -> MarketType:
    """The market a MarketForge output path belongs to: ``{market}/{SYMBOL}_{timeframe}``."""
    folder = path.resolve().parent.name.lower()
    if folder in set(MarketType):
        return MarketType(folder)
    symbol = path.stem.split("_")[0].upper()
    for market, config in load_catalog().items():
        if symbol in config.symbols:
            return market
    raise ValueError(
        f"Cannot tell which market {path} belongs to; pass the market "
        f"({', '.join(m.value for m in MarketType)})"
    )


def _minutes_between_candles(frame: pd.DataFrame) -> float | None:
    """Smallest gap between consecutive candles, in minutes; None when times are unknown."""
    seconds = _seconds(frame)
    return None if seconds is None else float(np.diff(seconds).min()) / 60.0
