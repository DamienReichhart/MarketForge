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

Candles are buffered per file and written in large chunks (one Parquet row
group per flush): tiny per-day writes made the writer, not the simulation,
the bottleneck. A per-writer cap on buffered rows keeps memory bounded however
many files are written and however long the range is.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from enum import StrEnum
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.csv as pacsv
import pyarrow.parquet as pq

from marketforge.domain.bars import Bars
from marketforge.domain.timeframes import Timeframe

PRICE_DECIMALS = 8
VOLUME_DECIMALS = 4
# Rows buffered per file before it is written: one Parquet row group. Day-sized
# row groups (1440 rows) made Parquet files larger than CSV.
ROW_GROUP_ROWS = 32_768
# Cap on rows buffered across all files of one writer (~50 bytes per row,
# so ~100 MB). Past it, the largest buffers are written early.
MAX_BUFFERED_ROWS = 2_000_000
# File descriptors kept free for everything else when Parquet writers are open.
_FD_HEADROOM = 64

_PRICE_FIELDS = ("open", "high", "low", "close")


class OutputFormat(StrEnum):
    """On-disk format of generated candles."""

    CSV = "csv"
    PARQUET = "parquet"


def candle_schema(include_regime: bool) -> pa.Schema:
    """Arrow schema of written candles."""
    fields = [pa.field("timestamp", pa.int64())]
    fields += [pa.field(c, pa.float64()) for c in (*_PRICE_FIELDS, "volume")]
    if include_regime:
        fields.append(pa.field("regime", pa.int8()))
    return pa.schema(fields)


def _rounded_columns(bars: Bars, columns: Sequence[int]) -> tuple[np.ndarray, list[np.ndarray]]:
    """
    Timestamps, and open/high/low/close/volume rounded for every requested
    column at once, transposed to (columns, rows) so that each instrument's
    values are contiguous.
    """
    cols = list(columns)
    every = cols == list(range(bars.open.shape[1]))

    def rounded(values: np.ndarray, decimals: int) -> np.ndarray:
        picked = values if every else values[:, cols]
        return np.ascontiguousarray(np.round(picked, decimals).T)

    fields = [rounded(getattr(bars, f), PRICE_DECIMALS) for f in _PRICE_FIELDS]
    fields.append(rounded(bars.volume, VOLUME_DECIMALS))
    return np.ascontiguousarray(bars.timestamps, dtype=np.int64), fields


def _batch(parts: list[tuple[np.ndarray, ...]], schema: pa.Schema) -> pa.RecordBatch:
    """One record batch from buffered (timestamps, o, h, l, c, v[, regime]) chunks."""
    arrays = []
    for k, field in enumerate(schema):
        chunk = [p[k] for p in parts]
        values = chunk[0] if len(chunk) == 1 else np.concatenate(chunk)
        arrays.append(pa.array(values, field.type))
    return pa.RecordBatch.from_arrays(arrays, schema=schema)


def ensure_open_file_capacity(n_files: int) -> None:
    """
    Make sure this process may keep ``n_files`` files open at once.

    A Parquet file can only be finished, not appended to, so every Parquet
    output stays open until generation ends. Default soft limits (256 on
    macOS, 1024 on Linux) are below what a whole-catalog run needs; the soft
    limit is raised towards the hard limit when necessary.

    Raises:
        OSError: if the hard limit is too low.
    """
    try:
        import resource
    except ImportError:  # Windows: per-process handle limits are far higher.
        return
    needed = n_files + _FD_HEADROOM
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    if soft == resource.RLIM_INFINITY or soft >= needed:
        return
    target = needed if hard == resource.RLIM_INFINITY else min(hard, needed)
    if sys.platform == "darwin":  # setrlimit fails above kern.maxfilesperproc
        target = min(target, 10_240)
    if target > soft:
        try:
            resource.setrlimit(resource.RLIMIT_NOFILE, (target, hard))
            soft = target
        except (ValueError, OSError):
            pass
    if soft < needed:
        raise OSError(
            f"Parquet output keeps every file open until the end: {n_files} files need "
            f"~{needed} file descriptors but this process may open only {soft}. "
            "Raise the limit (ulimit -n), request fewer instruments or timeframes, "
            "or use CSV."
        )


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
        max_buffered_rows: int = MAX_BUFFERED_ROWS,
    ) -> None:
        self.directory = Path(output_dir) / market
        self.directory.mkdir(parents=True, exist_ok=True)
        self.fmt = OutputFormat(fmt)
        self.include_regime = include_regime
        self.schema = candle_schema(include_regime)
        self._symbols = list(symbols)
        self._columns = list(columns)
        if len(self._symbols) != len(self._columns):
            raise ValueError("symbols and columns must have the same length")
        self.paths: dict[str, dict[str, Path]] = {
            s: {tf.name: self.directory / f"{s}_{tf.name}.{self.fmt.value}" for tf in timeframes}
            for s in symbols
        }
        self._max_buffered = max(ROW_GROUP_ROWS, int(max_buffered_rows))
        self._parquet: dict[Path, pq.ParquetWriter] = {}
        self._started: set[Path] = set()
        self._buffers: dict[Path, list[tuple[np.ndarray, ...]]] = {}
        self._buffered: dict[Path, int] = {}
        self._total_buffered = 0
        self._csv_options = pacsv.WriteOptions(include_header=False)
        self._csv_header = (",".join(self.schema.names) + "\n").encode("ascii")
        # Never leave a stale file from an earlier run behind: every output is
        # rewritten from scratch (on first flush, or empty at close).
        for files in self.paths.values():
            for path in files.values():
                if path.exists():
                    path.unlink()

    @property
    def n_files(self) -> int:
        return sum(len(files) for files in self.paths.values())

    def write(self, timeframe: Timeframe, bars: Bars | None) -> None:
        if bars is None or len(bars) == 0:
            return
        ts, fields = _rounded_columns(bars, self._columns)
        regime = (bars.regime.astype(np.int8),) if self.include_regime else ()
        rows = len(bars)
        for j, symbol in enumerate(self._symbols):
            path = self.paths[symbol][timeframe.name]
            self._buffers.setdefault(path, []).append((ts, *(f[j] for f in fields), *regime))
            n = self._buffered.get(path, 0) + rows
            self._buffered[path] = n
            self._total_buffered += rows
            if n >= ROW_GROUP_ROWS:
                self._flush(path)
        if self._total_buffered > self._max_buffered:
            # Memory cap: write the largest buffers early.
            for path in sorted(self._buffered, key=self._buffered.__getitem__, reverse=True):
                if self._total_buffered <= self._max_buffered // 2:
                    break
                self._flush(path)

    def _flush(self, path: Path) -> None:
        buf = self._buffers.pop(path, None)
        self._total_buffered -= self._buffered.pop(path, 0)
        if not buf:
            return
        table = pa.Table.from_batches([_batch(buf, self.schema)])
        if self.fmt == OutputFormat.CSV:
            first = path not in self._started
            self._started.add(path)
            with open(path, "wb" if first else "ab") as fh:
                if first:
                    fh.write(self._csv_header)
                pacsv.write_csv(table, fh, self._csv_options)
            return
        writer = self._parquet.get(path)
        if writer is None:
            # Random-walk doubles barely compress as-is; byte-stream-split
            # encoding makes files ~40% of the CSV size instead of ~60%.
            writer = pq.ParquetWriter(
                path,
                self.schema,
                compression="zstd",
                use_dictionary=["timestamp"],
                use_byte_stream_split=["open", "high", "low", "close", "volume"],
            )
            self._parquet[path] = writer
        writer.write_table(table, row_group_size=table.num_rows)

    def close(self) -> dict[str, dict[str, Path]]:
        """Finish all files and return {symbol: {timeframe: path}}."""
        try:
            for path in list(self._buffers):
                self._flush(path)
        finally:
            for writer in self._parquet.values():
                writer.close()
            self._parquet.clear()
        # Files that received no candle are still valid, empty files.
        empty = self.schema.empty_table()
        for files in self.paths.values():
            for path in files.values():
                if path.exists():
                    continue
                if self.fmt == OutputFormat.CSV:
                    path.write_bytes(self._csv_header)
                else:
                    pq.write_table(empty, path)
        return self.paths
