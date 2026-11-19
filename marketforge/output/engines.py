# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

"""
Candles in the file layouts backtesting engines read from disk.

- **freqtrade** reads ``{BASE}_{QUOTE}-{timeframe}.feather`` from its data
  directory, with the columns ``date`` (UTC), ``open``, ``high``, ``low``,
  ``close`` and ``volume`` (``freqtrade/candle_columns.py``,
  ``misc.pair_to_filename``).
- **LEAN** (QuantConnect) reads zipped CSV files under
  ``{security type}/{market}/{resolution}/``, as in the sample data of its
  repository (``Data/readme.md``, ``TradeBar.cs``, ``QuoteBar.cs``): one zip
  per day for minute data, holding ``{date}_{ticker}_minute_{trade|quote}.csv``
  whose first column is milliseconds since midnight; one zip per ticker for
  hour and daily data, whose first column is ``yyyyMMdd HH:mm``. Equity
  prices are integers in ten-thousandths, in New York time; forex, CFD and
  crypto prices are plain, in UTC (the data time zones of LEAN's market-hours
  database). Forex and CFDs have quote bars only.

These functions take frames as :func:`marketforge.generate` returns them (a
UTC ``DatetimeIndex``) and write files; reading a dataset is the caller's.
"""

from __future__ import annotations

import io
import zipfile
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pandas as pd

from marketforge.config.catalog.forex.risk import STOCK_INDICES
from marketforge.domain.markets import MarketType
from marketforge.domain.timeframes import Timeframe

ENGINES = ("freqtrade", "lean")

# freqtrade's timeframe names; the others (m2, m10, m20, H3) it does not have.
FREQTRADE_TIMEFRAMES = {
    Timeframe.m1: "1m",
    Timeframe.m3: "3m",
    Timeframe.m5: "5m",
    Timeframe.m15: "15m",
    Timeframe.m30: "30m",
    Timeframe.H1: "1h",
    Timeframe.H2: "2h",
    Timeframe.H4: "4h",
    Timeframe.H6: "6h",
    Timeframe.H8: "8h",
    Timeframe.H12: "12h",
    Timeframe.D1: "1d",
    Timeframe.W1: "1w",
}

# Codes of the forex catalog that are not currencies: LEAN trades them as
# CFDs (Oanda's XAUUSD, SPX500USD...), not as forex pairs.
_NOT_CURRENCIES = frozenset(STOCK_INDICES | {"XAU", "XAG", "XPT", "XPD", "BCO", "WTI", "UDX"})
_EQUITY_SCALE = 10_000
_NEW_YORK = "America/New_York"


def pair(symbol: str, market: MarketType, quote: str | None = None) -> tuple[str, str]:
    """(base, quote) of an instrument: BTCUSD is BTC/USD, AAPL is AAPL/USD.

    ``quote`` renames the dollar a coin is quoted in, e.g. to USDT for an
    exchange that lists coins against it.
    """
    if market == MarketType.STOCKS:
        base, theirs = symbol, "USD"
    elif market == MarketType.FOREX:
        base, theirs = symbol[:3], symbol[3:]
    else:
        base, theirs = (symbol[:-3], "USD") if symbol.endswith("USD") else (symbol, "USD")
    if quote is not None and market == MarketType.CRYPTO and theirs == "USD":
        theirs = quote
    return base, theirs


def freqtrade_name(symbol: str, market: MarketType, timeframe: Timeframe, quote: str | None) -> str:
    """The file freqtrade looks for: ``BTC_USDT-5m.feather``."""
    base, theirs = pair(symbol, market, quote)
    return f"{base}_{theirs}-{FREQTRADE_TIMEFRAMES[timeframe]}.feather"


def write_freqtrade(frame: pd.DataFrame, path: Path) -> None:
    """One pair and timeframe as freqtrade's feather data handler stores it."""
    candles = pd.DataFrame(
        {
            "date": frame.index.as_unit("ms"),
            "open": frame["open"].to_numpy(float),
            "high": frame["high"].to_numpy(float),
            "low": frame["low"].to_numpy(float),
            "close": frame["close"].to_numpy(float),
            "volume": frame["volume"].to_numpy(float),
        }
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    candles.to_feather(path, compression="lz4")


def lean_kind(symbol: str, market: MarketType) -> tuple[str, str]:
    """(security type, market) folders of an instrument in LEAN's data tree."""
    if market == MarketType.STOCKS:
        return "equity", "usa"
    if market == MarketType.CRYPTO:
        return "crypto", "coinbase"
    if symbol[:3] in _NOT_CURRENCIES or symbol[3:] in _NOT_CURRENCIES:
        return "cfd", "oanda"
    return "forex", "oanda"


def write_lean(symbol: str, market: MarketType, m1: pd.DataFrame, root: Path) -> list[Path]:
    """Minute, hour and daily files of one instrument, from its m1 candles."""
    kind, venue = lean_kind(symbol, market)
    ticker = symbol.lower()
    folder = root / kind / venue
    quotes_only = kind in ("forex", "cfd")
    has_quotes = quotes_only or {"bid", "ask"} <= set(m1.columns)
    zone = _NEW_YORK if kind == "equity" else "UTC"
    local = m1.tz_convert(zone)
    written: list[Path] = []
    # Minute: one zip per local day.
    days = local.index.normalize()
    for day, candles in local.groupby(days, sort=True):
        stamp = pd.Timestamp(day).strftime("%Y%m%d")
        millis = ((candles.index - day) // pd.Timedelta(milliseconds=1)).to_numpy(np.int64)
        for tick, rows in _bars(candles, kind, quotes_only, has_quotes):
            path = folder / "minute" / ticker / f"{stamp}_{tick}.zip"
            name = f"{stamp}_{ticker}_minute_{tick}.csv"
            _zip(path, name, _csv([millis.astype(str), *rows]))
            written.append(path)
    # Hour and daily: one zip per ticker, bars on the clock hour and local day.
    for resolution, rule in (("hour", "h"), ("daily", "D")):
        bars = _resample(local, rule)
        stamps = bars.index.strftime("%Y%m%d %H:%M").to_numpy()
        # Crypto's hour and daily files say which bars they hold; the
        # others hold trades (equity) or quotes (forex, CFD) only.
        for tick, rows in _bars(bars, kind, quotes_only, has_quotes and kind != "equity"):
            suffix = f"_{tick}" if kind == "crypto" else ""
            path = folder / resolution / f"{ticker}{suffix}.zip"
            _zip(path, f"{ticker}.csv", _csv([stamps, *rows]))
            written.append(path)
    if kind == "equity":
        # LEAN looks a stock up in its map file (its ticker over time) and
        # scales its prices by its factor file: one ticker, no splits, no
        # dividends ("Q": listed on Nasdaq).
        first = local.index[0].strftime("%Y%m%d")
        for name, text in (
            ("map_files", f"{first},{ticker},Q\n20501231,{ticker},Q\n"),
            ("factor_files", f"{first},1,1,1\n20501231,1,1,0\n"),
        ):
            path = folder / name / f"{ticker}.csv"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="ascii")
            written.append(path)
    return written


def _resample(local: pd.DataFrame, rule: str) -> pd.DataFrame:
    how = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    how.update({c: "last" for c in ("bid", "ask", "spread") if c in local.columns})
    bars = local.resample(rule, label="left", closed="left").agg(how)
    return bars.dropna(subset=["open"])


def _bars(
    candles: pd.DataFrame, kind: str, quotes_only: bool, has_quotes: bool
) -> Iterator[tuple[str, list[np.ndarray]]]:
    """('trade' or 'quote', the columns after the time) of some candles."""
    prices = {c: candles[c].to_numpy(float) for c in ("open", "high", "low", "close")}
    if not quotes_only:
        yield "trade", [*(_price(prices[c], kind) for c in prices), _volume(candles, kind)]
    if has_quotes:
        # The candles are mids; the quote bars take the closing spread over
        # the whole candle, half each way (no spread at all without one).
        close = prices["close"]
        if {"bid", "ask"} <= set(candles.columns):
            below, above = (
                close - candles["bid"].to_numpy(float),
                candles["ask"].to_numpy(float) - close,
            )
        elif "spread" in candles.columns:
            below = above = candles["spread"].to_numpy(float) / 2
        else:
            below = above = np.zeros_like(close)
        size = np.zeros(close.size, dtype=np.int64).astype(str)
        bid = [_price(prices[c] - below, kind) for c in prices]
        ask = [_price(prices[c] + above, kind) for c in prices]
        yield "quote", [*bid, size, *ask, size]


def _price(values: np.ndarray, kind: str) -> np.ndarray:
    if kind == "equity":
        return np.asarray(np.rint(values * _EQUITY_SCALE).astype(np.int64).astype(str))
    return _plain(values)


def _volume(candles: pd.DataFrame, kind: str) -> np.ndarray:
    volume = candles["volume"].to_numpy(float)
    if kind == "equity":
        return np.asarray(np.rint(volume).astype(np.int64).astype(str))
    return _plain(volume)


def _plain(values: np.ndarray) -> np.ndarray:
    """Decimals as the dataset's files write them: at most 8, no exponent."""
    return np.asarray(np.char.mod("%.15g", np.round(values, 8)))


def _csv(columns: list[np.ndarray]) -> bytes:
    lines = [",".join(row) for row in zip(*columns, strict=True)]
    return ("\n".join(lines) + "\n").encode()


def _zip(path: Path, name: str, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))  # reproducible bytes
        archive.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED)
    path.write_bytes(buffer.getvalue())
