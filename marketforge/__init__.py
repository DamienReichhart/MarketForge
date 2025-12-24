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
MarketForge

A professional-grade synthetic OHLCV data generator for backtesting,
stress testing, and development purposes. Supports multi-asset generation
with correlations, realistic market behavior, and multiple timeframes.
"""

__version__ = "1.0.0"
__author__ = "REICHHART Damien"

from marketforge.config.settings import GeneratorConfig
from marketforge.core.returns import ReturnGenerator
from marketforge.generators.ohlcv import OHLCVBuilder

__all__ = [
    "GeneratorConfig",
    "ReturnGenerator",
    "OHLCVBuilder",
    "__version__",
]

