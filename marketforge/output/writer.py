# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

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

from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as pacsv
import pyarrow.parquet as pq

from marketforge.domain.bars import Bars
from marketforge.domain.timeframes import Timeframe
from marketforge.output.encoding import candle_schema, record_batch, rounded_columns
from marketforge.output.formats import OutputFormat, TimestampFormat, check_formats
from marketforge.output.manifest import REWRITE_SUFFIX

# Rows buffered per file before it is written: one Parquet row group. Day-sized
# row groups (1440 rows) made Parquet files larger than CSV.
ROW_GROUP_ROWS = 32_768
# Cap on rows buffered across all files of one writer (~50 bytes per row,
# so ~100 MB). Past it, the largest buffers are written early.
MAX_BUFFERED_ROWS = 2_000_000


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
        extend: bool = False,
        include_spread: bool = False,
        timestamps: TimestampFormat = TimestampFormat.UNIX,
        include_bid_ask: bool = False,
    ) -> None:
        """
        With ``extend``, candles are added to the files a dataset already has:
        CSV files are appended to in place, and a Parquet file that receives
        candles is written whole (its rows, then the new ones) beside the
        original under ``REWRITE_SUFFIX``, for the caller to swap in.
        """
        self.directory = Path(output_dir) / market
        self.directory.mkdir(parents=True, exist_ok=True)
        self.fmt = OutputFormat(fmt)
        self._iso = TimestampFormat(timestamps) == TimestampFormat.ISO
        check_formats(self.fmt, TimestampFormat(timestamps))
        self.include_regime = include_regime
        self.schema = candle_schema(
            include_regime,
            include_spread,
            TimestampFormat(timestamps) == TimestampFormat.DATETIME,
            include_bid_ask,
        )
        self._spread = include_spread
        self._bid_ask = include_bid_ask
        self._symbols = list(symbols)
        self._columns = list(columns)
        if len(self._symbols) != len(self._columns):
            raise ValueError("symbols and columns must have the same length")
        self.paths: dict[str, dict[str, Path]] = {
            s: {tf.name: self.directory / f"{s}_{tf.name}.{self.fmt.value}" for tf in timeframes}
            for s in symbols
        }
        self._max_buffered = max(ROW_GROUP_ROWS, int(max_buffered_rows))
        self._binary: dict[Path, pq.ParquetWriter | pa.ipc.RecordBatchFileWriter] = {}
        self._started: set[Path] = set()
        self._rows = dict.fromkeys((p for files in self.paths.values() for p in files.values()), 0)
        self._buffers: dict[Path, list[tuple[np.ndarray, ...]]] = {}
        self._buffered: dict[Path, int] = {}
        self._total_buffered = 0
        self._csv_options = pacsv.WriteOptions(include_header=False, quoting_style="none")
        self._csv_header = (",".join(self.schema.names) + "\n").encode("ascii")
        self._extend = extend
        every = [path for files in self.paths.values() for path in files.values()]
        if extend:
            missing = [path for path in every if not path.exists()]
            if missing:
                raise FileNotFoundError(f"the dataset has lost {missing[0]}")
            self._started.update(every)
            return
        # Never leave a stale file from an earlier run behind: every output is
        # rewritten from scratch (on first flush, or empty at close).
        for path in every:
            if path.exists():
                path.unlink()

    @property
    def n_files(self) -> int:
        return sum(len(files) for files in self.paths.values())

    @property
    def empty(self) -> list[tuple[str, str]]:
        """The (symbol, timeframe) files that have received no candle from this writer."""
        return [
            (symbol, timeframe)
            for symbol, files in self.paths.items()
            for timeframe, path in files.items()
            if not self._rows[path]
        ]

    def write(self, timeframe: Timeframe, bars: Bars | None) -> None:
        if bars is None or len(bars) == 0:
            return
        ts, fields = rounded_columns(bars, self._columns, self._spread, self._bid_ask)
        regime = (bars.regime.astype(np.int8),) if self.include_regime else ()
        rows = len(bars)
        for j, symbol in enumerate(self._symbols):
            path = self.paths[symbol][timeframe.name]
            self._buffers.setdefault(path, []).append((ts, *(f[j] for f in fields), *regime))
            n = self._buffered.get(path, 0) + rows
            self._buffered[path] = n
            self._rows[path] += rows
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
        table = pa.Table.from_batches([record_batch(buf, self.schema)])
        if self.fmt == OutputFormat.CSV:
            first = path not in self._started
            self._started.add(path)
            if self._iso:
                # Zone-less on purpose: formatting a zoned timestamp needs a time
                # zone database, which Windows does not ship. The "Z" is literal.
                moments = table["timestamp"].cast(pa.timestamp("s"))
                table = table.set_column(
                    0, "timestamp", pc.strftime(moments, format="%Y-%m-%dT%H:%M:%SZ")
                )
            with open(path, "wb" if first else "ab") as fh:
                if first:
                    fh.write(self._csv_header)
                pacsv.write_csv(table, fh, self._csv_options)
            return
        writer = self._binary.get(path)
        target = path.with_name(path.name + REWRITE_SUFFIX) if self._extend else path
        if writer is None and self.fmt == OutputFormat.FEATHER:
            writer = pa.ipc.new_file(
                str(target), self.schema, options=pa.ipc.IpcWriteOptions(compression="zstd")
            )
            self._binary[path] = writer
            if self._extend:
                with pa.memory_map(str(path)) as source:
                    existing = pa.ipc.open_file(source).read_all()
                writer.write_table(existing.cast(self.schema))
        elif writer is None:
            # Random-walk doubles barely compress as-is; byte-stream-split
            # encoding makes files ~40% of the CSV size instead of ~60%.
            writer = pq.ParquetWriter(
                target,
                self.schema,
                compression="zstd",
                use_dictionary=["timestamp", "regime"],
                use_byte_stream_split=[f.name for f in self.schema if f.type == pa.float64()],
            )
            self._binary[path] = writer
            if self._extend:
                # Closed before the rewritten file replaces it (Windows cannot
                # replace a file that is still open).
                with pq.ParquetFile(path) as existing:
                    for group in range(existing.num_row_groups):
                        # Older pyarrow reads the regime dictionary back with
                        # int32 indices; the file's schema has int8.
                        writer.write_table(existing.read_row_group(group).cast(self.schema))
        if isinstance(writer, pq.ParquetWriter):
            writer.write_table(table, row_group_size=table.num_rows)
        else:
            writer.write_table(table)

    def close(self) -> dict[str, dict[str, Path]]:
        """Finish all files and return {symbol: {timeframe: path}}."""
        try:
            for path in list(self._buffers):
                self._flush(path)
        finally:
            for writer in self._binary.values():
                writer.close()
            self._binary.clear()
        if self._extend:
            return self.paths
        # Files that received no candle are still valid, empty files.
        empty = self.schema.empty_table()
        for files in self.paths.values():
            for path in files.values():
                if path.exists():
                    continue
                if self.fmt == OutputFormat.CSV:
                    path.write_bytes(self._csv_header)
                elif self.fmt == OutputFormat.FEATHER:
                    with pa.ipc.new_file(str(path), self.schema) as sink:
                        sink.write_table(empty)
                else:
                    pq.write_table(empty, path)
        return self.paths
