# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

"""Instrument parameters fitted to real m1 candles, as an override file."""

from __future__ import annotations

import os
import warnings
from functools import cache
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from marketforge.api.catalog import instruments
from marketforge.config.loader import load_catalog
from marketforge.domain.markets import MarketType

_SECONDS_PER_YEAR = 365.25 * 86_400
_TIME_COLUMNS = ("timestamp", "time", "datetime", "date")
# Override files take correlations strictly between -1 and 1; near-identical
# series (GOOG and GOOGL) would otherwise write 1.0 and be refused.
_MAX_CORRELATION = 0.99


def calibrate(
    files: list[str | os.PathLike[str]], market: str | MarketType
) -> dict[str, dict[str, Any]]:
    """
    Fit instrument parameters to m1 candle files: an override for each one.

    Each file is named ``SYMBOL_m1.csv`` (or ``.parquet``, ``.feather``); the
    symbol comes from the name. For each one:

    - ``start_price``: the last close, so a generation continues from there;
    - ``volatility``: the annualised volatility of its log returns, overnight
      and weekend gaps included, as the catalog defines it;
    - ``tick_size``: the price step the closes are on (a power of ten), so
      the generated prices keep the data's decimals;
    - ``volume_base``: the mean volume per minute;
    - ``correlations``: the correlation of hourly returns with every file
      before it, on the hours both trade, kept within +/-0.99 as an override
      file requires.

    Drift is not estimated: below several years of data it is noise. The
    result is the ``[instruments]`` table of an override file (see
    :func:`write_overrides`) and can be passed as ``overrides=``; it is
    checked as generation would check it, so an error shows here, not later.

    Raises:
        ValueError: a file is not named ``SYMBOL_m1``, two files name the same
            symbol, a file has fewer than 1000 candles, or the fitted
            instruments are not valid for the market (e.g. a forex symbol that
            is not six characters).
    """
    market = MarketType(str(market).lower())
    out: dict[str, dict[str, Any]] = {}
    hourly: dict[str, pd.Series] = {}
    for file in files:
        path = Path(file)
        symbol = _symbol_of(path)
        if symbol in out:
            raise ValueError(f"{path}: {symbol} is already calibrated from another file")
        candles = _read_candles(path)
        if len(candles) < 1000:
            raise ValueError(f"{path} has {len(candles)} candles; calibration needs at least 1000")
        log_close = np.log(candles["close"].to_numpy(dtype=float))
        returns = np.diff(log_close)
        stamps = pd.DatetimeIndex(candles.index).as_unit("s").asi8
        span = float(stamps[-1] - stamps[0]) + 60.0
        volatility = float(np.sqrt(np.sum(returns**2) * _SECONDS_PER_YEAR / span))
        body: dict[str, Any] = {
            "market": market.value,
            "start_price": float(candles["close"].iloc[-1]),
            "volatility": round(volatility, 6),
        }
        tick = _tick_size(candles["close"].to_numpy(dtype=float))
        if tick is not None and tick <= body["start_price"]:
            body["tick_size"] = tick
        if "volume" in candles.columns and candles["volume"].sum() > 0:
            observed = float(candles["volume"].mean())
            body["volume_base"] = round(observed / _volume_scale(market, symbol), 4)
        series = pd.Series(log_close, index=candles.index).resample("1h").last().diff().dropna()
        correlations = {}
        for other, theirs in hourly.items():
            both = pd.concat([series, theirs], axis=1, join="inner").dropna()
            if len(both) >= 100:
                value = round(float(both.corr().iloc[0, 1]), 4)
                correlations[other] = min(max(value, -_MAX_CORRELATION), _MAX_CORRELATION)
        if correlations:
            body["correlations"] = correlations
        hourly[symbol] = series
        out[symbol] = body
    try:
        with warnings.catch_warnings():  # generation repeats any warning
            warnings.simplefilter("ignore")
            load_catalog(out)
    except ValueError as e:
        raise ValueError(
            f"The fitted instruments are not valid {market.value} instruments: {e}"
        ) from None
    return out


def _tick_size(closes: np.ndarray) -> float | None:
    """The coarsest step, from 1 down to 1e-8 (a power of ten), every close is on."""
    for decimals in range(9):
        scaled = closes * 10.0**decimals
        if np.all(np.abs(scaled - np.rint(scaled)) <= 1e-6 + 1e-12 * np.abs(scaled)):
            return float(f"1e-{decimals}")
    return None


def _symbol_of(path: Path) -> str:
    stem = path.stem
    if not stem.lower().endswith("_m1") or len(stem) <= 3:
        raise ValueError(
            f"{path.name}: name calibration files SYMBOL_m1{path.suffix} "
            "(e.g. EURUSD_m1.csv); the symbol comes from the file name"
        )
    return stem[:-3].upper()


# The seeds and days _volume_scale averages over: one seed's 90 days were
# off by 10% or more, as the regimes and the world move the mean volume.
_SCALE_SEEDS = (0, 1, 2, 3)
_SCALE_DAYS = 45


@cache
def _volume_scale(market: MarketType, symbol: str) -> float:
    """Mean generated volume per unit of ``volume_base`` for an instrument, measured once.

    Turbulence, seasonality and the regimes all scale volume, and by how much
    depends on the instrument (its volume volatility, its turbulence), so a
    catalog ``volume_base`` is not the mean volume it produces; dividing an
    observed mean by this gives the ``volume_base`` that reproduces it. An
    instrument the catalog does not have is measured as the market's first.
    """
    from marketforge.api.memory import generate  # the simulator, only when calibrating

    catalog = instruments(market.value)
    known = symbol if symbol in catalog.index else str(catalog.index[0])
    ratios = [
        float(
            generate(known, start="2023-01-02", days=_SCALE_DAYS, seed=seed)[known]["m1"][
                "volume"
            ].mean()
        )
        for seed in _SCALE_SEEDS
    ]
    return float(np.mean(ratios)) / float(catalog.loc[known, "volume_base"])


def write_overrides(overrides: dict[str, dict[str, Any]], path: str | os.PathLike[str]) -> Path:
    """Write the ``[instruments]`` tables of an override file."""
    lines = [
        "# Fitted by `marketforge calibrate`: pass with --overrides or overrides=.",
        "# Drift is not estimated (it is noise below several years of data).",
        "",
    ]
    for symbol, body in overrides.items():
        lines.append(f"[instruments.{symbol}]")
        for key, value in body.items():
            if key == "correlations":
                pairs = ", ".join(f"{k} = {v!r}" for k, v in value.items())
                lines.append(f"correlations = {{ {pairs} }}")
            elif isinstance(value, str):
                lines.append(f'{key} = "{value}"')
            else:
                lines.append(f"{key} = {value!r}")
        lines.append("")
    target = Path(path)
    target.write_text("\n".join(lines), encoding="utf-8")
    return target


def _read_candles(path: Path) -> pd.DataFrame:
    if path.suffix == ".parquet":
        raw = pd.read_parquet(path)
    elif path.suffix in (".feather", ".arrow"):
        raw = pd.read_feather(path)
    else:
        raw = pd.read_csv(path)
    raw.columns = [str(c).lower() for c in raw.columns]
    time = next((c for c in _TIME_COLUMNS if c in raw.columns), None)
    if time is None or "close" not in raw.columns:
        raise ValueError(f"{path} needs a close column and one of {', '.join(_TIME_COLUMNS)}")
    stamps = raw[time]
    if pd.api.types.is_numeric_dtype(stamps):
        index = pd.to_datetime(stamps.to_numpy(), unit="s", utc=True)
    else:
        index = pd.to_datetime(stamps.to_numpy(), utc=True)
    frame = raw.drop(columns=time)
    frame.index = pd.DatetimeIndex(index, name="time")
    return frame.sort_index()
