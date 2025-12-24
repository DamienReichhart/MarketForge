# MarketForge
# Copyright (C) 2026 REICHHART Damien
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

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

