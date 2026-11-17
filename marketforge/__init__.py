# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
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
from marketforge.api.estimating import Estimate, estimate
from marketforge.api.memory import GeneratedData, generate, generate_many
from marketforge.api.parsing import parse_time
from marketforge.api.reading import read
from marketforge.api.validating import validate

__author__ = "REICHHART Damien"

__all__ = [
    "MODEL_REVISION",
    "Estimate",
    "GeneratedData",
    "__version__",
    "estimate",
    "extend",
    "generate",
    "generate_many",
    "generate_to_disk",
    "instruments",
    "parse_time",
    "read",
    "validate",
]
