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

from importlib import metadata as _metadata

from marketforge.api import GeneratedData, generate, generate_to_disk, parse_time

try:
    # pyproject.toml is the single source of truth for the version.
    __version__ = _metadata.version("marketforge")
except _metadata.PackageNotFoundError:  # pragma: no cover - uninstalled checkout
    __version__ = "0.0.0+unknown"
__author__ = "REICHHART Damien"

__all__ = [
    "generate",
    "generate_to_disk",
    "parse_time",
    "GeneratedData",
    "__version__",
]
