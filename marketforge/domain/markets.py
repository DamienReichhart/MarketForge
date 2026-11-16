# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the MIT License. See the LICENSE file in the project
# root for full license information.

"""Markets."""

from __future__ import annotations

from enum import StrEnum


class MarketType(StrEnum):
    """A market: a family of instruments sharing one calendar and one regime path."""

    CRYPTO = "crypto"
    FOREX = "forex"
    STOCKS = "stocks"
