# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

"""Anomaly kinds."""

from __future__ import annotations

from enum import StrEnum


class AnomalyType(StrEnum):
    """Optional, deliberately unrealistic events layered on the simulation."""

    SPIKES = "spikes"
    FLASH_CRASH = "flash_crash"
