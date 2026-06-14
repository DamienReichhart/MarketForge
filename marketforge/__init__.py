# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the MIT License. See the LICENSE file in the project
# root for full license information.

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

