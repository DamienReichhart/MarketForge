# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

"""
MarketForge: synthetic OHLCV market data for training trading models,
testing backtesters and stress-testing strategies.

Crypto, forex and US stock instruments simulated minute by minute on their
real trading calendars, every candle labelled with its market regime, and
every dataset reproducible from its seed. The supported API is what this
module exports; module paths below it can change between releases.
"""

from marketforge._version import MODEL_REVISION, __version__
from marketforge.api.calibrating import calibrate
from marketforge.api.catalog import instruments
from marketforge.api.data import GeneratedData, InstrumentData, Windows
from marketforge.api.disk import DiskReport, extend, generate_to_disk
from marketforge.api.estimating import Estimate, estimate
from marketforge.api.inspecting import DatasetInfo, VerifyReport, info, verify
from marketforge.api.memory import concat, generate, generate_many
from marketforge.api.parsing import parse_time
from marketforge.api.reading import read
from marketforge.api.resampling import resample
from marketforge.api.validating import validate
from marketforge.config.overrides import OverrideError
from marketforge.validation.report import MetricResult, ValidationReport

__author__ = "REICHHART Damien"

__all__ = [
    "MODEL_REVISION",
    "DatasetInfo",
    "DiskReport",
    "Estimate",
    "GeneratedData",
    "InstrumentData",
    "MetricResult",
    "OverrideError",
    "ValidationReport",
    "VerifyReport",
    "Windows",
    "__version__",
    "calibrate",
    "concat",
    "estimate",
    "extend",
    "generate",
    "generate_many",
    "generate_to_disk",
    "info",
    "instruments",
    "parse_time",
    "read",
    "resample",
    "validate",
    "verify",
]
