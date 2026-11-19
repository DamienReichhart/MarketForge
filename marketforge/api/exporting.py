# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

"""Datasets in the native file layouts of backtesting engines (:func:`export`)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from marketforge.api.reading import read
from marketforge.domain.markets import MarketType
from marketforge.domain.timeframes import Timeframe
from marketforge.output.engines import (
    ENGINES,
    FREQTRADE_TIMEFRAMES,
    freqtrade_name,
    write_freqtrade,
    write_lean,
)
from marketforge.output.manifest import read_manifest


@dataclass(frozen=True)
class ExportReport:
    """What :func:`export` wrote, and what the engine has no place for."""

    engine: str
    files: list[Path] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)  # "SYMBOL TIMEFRAME: why"


def export(
    engine: str,
    dataset: str | os.PathLike[str],
    dest: str | os.PathLike[str],
    *,
    quote: str | None = None,
) -> ExportReport:
    """
    Write a dataset in the file layout a backtesting engine reads.

    - ``"freqtrade"``: ``dest`` is freqtrade's data directory (pass it as
      ``--datadir``); every timeframe freqtrade has becomes
      ``{BASE}_{QUOTE}-{timeframe}.feather`` (``BTC_USD-5m.feather``), and
      ``quote`` renames the dollar coins are quoted in (``"USDT"`` for an
      exchange that lists them against it).
    - ``"lean"``: ``dest`` is LEAN's data folder; the dataset's m1 candles
      become LEAN's minute, hour and daily files: stocks under
      ``equity/usa``, coins under ``crypto/coinbase``, currency pairs under
      ``forex/oanda`` and the other forex instruments (gold, index and oil
      CFDs) under ``cfd/oanda``. Forex and CFDs have quote bars, built from
      the candles' bid and ask (or spread) when the dataset has them.

    The dataset is read one instrument at a time, so it need not fit in memory.

    Raises:
        ValueError: if the engine is unknown, the directory is not a dataset,
            or LEAN is asked for a dataset without m1 candles.
    """
    name = str(engine).lower()
    if name not in ENGINES:
        raise ValueError(f"unknown engine {engine!r}; choose one of {', '.join(ENGINES)}")
    manifest = read_manifest(Path(dataset))
    root = Path(dest)
    report = ExportReport(name)
    timeframes = [Timeframe[t] for t in manifest.timeframes]
    if name == "lean" and Timeframe.m1 not in timeframes:
        raise ValueError(
            f"{dataset} has no m1 candles, which LEAN's minute, hour and daily files are built from"
        )
    for market_name, symbols in manifest.instruments.items():
        market = MarketType(market_name)
        for symbol in symbols:
            if name == "lean":
                data = read(dataset, [symbol], timeframes=["m1"])
                report.files.extend(write_lean(symbol, market, data[symbol]["m1"], root))
                continue
            kept = [t for t in timeframes if t in FREQTRADE_TIMEFRAMES]
            report.skipped.extend(
                f"{symbol} {t.name}: freqtrade has no such timeframe"
                for t in timeframes
                if t not in FREQTRADE_TIMEFRAMES
            )
            if not kept:
                continue
            data = read(dataset, [symbol], timeframes=[t.name for t in kept])
            for timeframe in kept:
                path = root / freqtrade_name(symbol, market, timeframe, quote)
                write_freqtrade(data[symbol][timeframe.name], path)
                report.files.append(path)
    return report
