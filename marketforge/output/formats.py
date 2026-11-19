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
    FEATHER = "feather"  # Arrow IPC: memory-mapped, zero-copy reads


class TimestampFormat(StrEnum):
    """How files store a candle's start time."""

    UNIX = "unix"  # 1704205800, any format
    ISO = "iso"  # 2024-01-02T14:30:00Z, CSV
    DATETIME = "datetime"  # a native UTC timestamp column, Parquet and Feather


def check_formats(fmt: OutputFormat, timestamps: TimestampFormat) -> None:
    """Refuse a combination of file format and timestamps that cannot be written."""
    if timestamps == TimestampFormat.ISO and fmt != OutputFormat.CSV:
        raise ValueError(
            f"ISO timestamps are for CSV files; {fmt.value} stores Unix seconds, or a native "
            "time column with datetime timestamps"
        )
    if timestamps == TimestampFormat.DATETIME and fmt == OutputFormat.CSV:
        raise ValueError(
            "datetime timestamps are for Parquet and Feather files; CSV takes unix or iso"
        )
