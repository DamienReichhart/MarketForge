# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the GNU Affero General Public License v3.0 or later.
# See the LICENSE file in the project root for full license information.

"""Anomaly kinds."""

from __future__ import annotations

from enum import StrEnum


class AnomalyType(StrEnum):
    """Optional, deliberately unrealistic events layered on the simulation."""

    SPIKES = "spikes"
    FLASH_CRASH = "flash_crash"
