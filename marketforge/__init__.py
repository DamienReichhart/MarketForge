# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the GNU Affero General Public License v3.0 or later.
# See the LICENSE file in the project root for full license information.

"""
MarketForge

A professional-grade synthetic OHLCV data generator for backtesting,
stress testing, and development purposes. Supports multi-instrument generation
with correlations, realistic market behavior, and multiple timeframes.
"""

from marketforge._version import MODEL_REVISION, __version__
from marketforge.api.catalog import instruments
from marketforge.api.disk import extend, generate_to_disk
from marketforge.api.memory import GeneratedData, generate
from marketforge.api.parsing import parse_time
from marketforge.api.validating import validate

__author__ = "REICHHART Damien"

__all__ = [
    "MODEL_REVISION",
    "GeneratedData",
    "__version__",
    "extend",
    "generate",
    "generate_to_disk",
    "instruments",
    "parse_time",
    "validate",
]
