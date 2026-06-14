# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the MIT License. See the LICENSE file in the project
# root for full license information.

"""
Configuration module for market-specific asset definitions.

Provides pre-configured assets for forex, crypto, and stocks markets
with realistic prices, volatilities, drifts, and correlation matrices.
"""

from marketforge.configs.base import (
    AssetParams,
    MarketConfig,
    MarketType,
)
from marketforge.configs.loader import (
    ConfigRegistry,
    load_market_config,
    get_available_markets,
)

__all__ = [
    "AssetParams",
    "MarketConfig",
    "MarketType",
    "ConfigRegistry",
    "load_market_config",
    "get_available_markets",
]

