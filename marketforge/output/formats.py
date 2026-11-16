# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the MIT License. See the LICENSE file in the project
# root for full license information.

"""On-disk formats."""

from __future__ import annotations

from enum import StrEnum


class OutputFormat(StrEnum):
    """On-disk format of generated candles."""

    CSV = "csv"
    PARQUET = "parquet"
