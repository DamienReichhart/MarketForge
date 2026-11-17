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


class TimestampFormat(StrEnum):
    """How CSV files write a candle's start time (Parquet always stores Unix seconds)."""

    UNIX = "unix"  # 1704205800
    ISO = "iso"  # 2024-01-02T14:30:00Z
