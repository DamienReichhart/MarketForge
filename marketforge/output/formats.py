# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

"""On-disk formats."""

from __future__ import annotations

from enum import StrEnum


class OutputFormat(StrEnum):
    """On-disk format of generated candles."""

    CSV = "csv"
    PARQUET = "parquet"
    FEATHER = "feather"  # Arrow IPC, uncompressed: memory-mapped, zero-copy reads


class TimestampFormat(StrEnum):
    """How files store a candle's start time."""

    UNIX = "unix"  # 1704205800, any format
    ISO = "iso"  # 2024-01-02T14:30:00Z, CSV
    DATETIME = "datetime"  # a native UTC timestamp column, Parquet and Feather


class Layout(StrEnum):
    """How a dataset's candles are split into files."""

    SPLIT = "split"  # {market}/{SYMBOL}_{tf}: one file per instrument and timeframe
    LONG = "long"  # {market}/{tf}: one file per market and timeframe, a symbol column


def check_formats(
    fmt: OutputFormat, timestamps: TimestampFormat, layout: Layout = Layout.SPLIT
) -> None:
    """Refuse a combination of file format, timestamps and layout that cannot be written."""
    if layout == Layout.LONG and fmt == OutputFormat.CSV:
        raise ValueError(
            "The long layout is for Parquet and Feather files, which keep the symbol column "
            "small; CSV takes the split layout"
        )
    if timestamps == TimestampFormat.ISO and fmt != OutputFormat.CSV:
        raise ValueError(
            f"ISO timestamps are for CSV files; {fmt.value} stores Unix seconds, or a native "
            "time column with datetime timestamps"
        )
    if timestamps == TimestampFormat.DATETIME and fmt == OutputFormat.CSV:
        raise ValueError(
            "datetime timestamps are for Parquet and Feather files; CSV takes unix or iso"
        )
