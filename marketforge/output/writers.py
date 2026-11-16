# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the MIT License. See the LICENSE file in the project
# root for full license information.

"""
Incremental CSV and Parquet writers.

Candles arrive a simulated day at a time; each (instrument, timeframe) file
is appended to as they do, so output size never has to fit in memory.
Files live at ``{output_dir}/{market}/{SYMBOL}_{timeframe}.{csv|parquet}``.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Optional, Sequence

import numpy as np
import pyarrow as pa
import pyarrow.csv as pacsv
import pyarrow.parquet as pq

from marketforge.aggregation.streaming import Bars
from marketforge.aggregation.timeframes import Timeframe

PRICE_DECIMALS = 8
VOLUME_DECIMALS = 4


class OutputFormat(str, Enum):
    """On-disk format of generated candles."""

    CSV = "csv"
    PARQUET = "parquet"


def candle_table(bars: Bars, column: int, include_regime: bool) -> pa.Table:
    """Arrow table of one instrument's candles (prices and volume rounded)."""
    cols = {
        "timestamp": pa.array(bars.timestamps, pa.int64()),
        "open": np.round(bars.open[:, column], PRICE_DECIMALS),
        "high": np.round(bars.high[:, column], PRICE_DECIMALS),
        "low": np.round(bars.low[:, column], PRICE_DECIMALS),
        "close": np.round(bars.close[:, column], PRICE_DECIMALS),
        "volume": np.round(bars.volume[:, column], VOLUME_DECIMALS),
    }
    if include_regime:
        cols["regime"] = pa.array(bars.regime.astype(np.int8), pa.int8())
    return pa.table(cols)


class CandleWriter:
    """Writes the selected instruments of one market, every requested timeframe."""

    def __init__(
        self,
        output_dir: str | Path,
        market: str,
        symbols: Sequence[str],
        columns: Sequence[int],
        timeframes: Sequence[Timeframe],
        fmt: OutputFormat = OutputFormat.CSV,
        include_regime: bool = False,
    ) -> None:
        self.directory = Path(output_dir) / market
        self.directory.mkdir(parents=True, exist_ok=True)
        self.fmt = OutputFormat(fmt)
        self.include_regime = include_regime
        self._targets = list(zip(symbols, columns))
        self.paths: dict[str, dict[str, Path]] = {
            s: {tf.name: self.directory / f"{s}_{tf.name}.{self.fmt.value}" for tf in timeframes}
            for s in symbols
        }
        self._started: set[Path] = set()
        self._parquet: dict[Path, pq.ParquetWriter] = {}
        # Start every file empty, even if no candle ends up being written.
        for files in self.paths.values():
            for path in files.values():
                self._open(path)

    def _open(self, path: Path) -> None:
        if self.fmt == OutputFormat.CSV:
            header = "timestamp,open,high,low,close,volume" + (",regime" if self.include_regime else "")
            path.write_text(header + "\n", encoding="ascii")
        self._started.add(path)

    def write(self, timeframe: Timeframe, bars: Optional[Bars]) -> None:
        if bars is None or len(bars) == 0:
            return
        for symbol, col in self._targets:
            path = self.paths[symbol][timeframe.name]
            table = candle_table(bars, col, self.include_regime)
            if self.fmt == OutputFormat.CSV:
                with open(path, "ab") as fh:
                    pacsv.write_csv(table, fh, pacsv.WriteOptions(include_header=False))
            else:
                writer = self._parquet.get(path)
                if writer is None:
                    writer = pq.ParquetWriter(path, table.schema, compression="zstd")
                    self._parquet[path] = writer
                writer.write_table(table)

    def close(self) -> dict[str, dict[str, Path]]:
        """Finish all files and return {symbol: {timeframe: path}}."""
        for writer in self._parquet.values():
            writer.close()
        self._parquet.clear()
        if self.fmt == OutputFormat.PARQUET:
            # Timeframes that received no candle still get a valid, empty file.
            fields = [pa.field("timestamp", pa.int64())] + [
                pa.field(c, pa.float64()) for c in ("open", "high", "low", "close", "volume")
            ]
            if self.include_regime:
                fields.append(pa.field("regime", pa.int8()))
            empty = pa.schema(fields).empty_table()
            for files in self.paths.values():
                for path in files.values():
                    if not path.exists():
                        pq.write_table(empty, path)
        return self.paths
