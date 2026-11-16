# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the MIT License. See the LICENSE file in the project
# root for full license information.

"""
Reference statistics measured on real m1 data, and the validation bands
derived from them (docs/adr/0006).

Each entry is the [min, max] over instruments and non-overlapping 14-day
windows, produced by ``scripts/measure_real_data.py``. Only these derived
numbers are stored; the raw data is not redistributed.

Markets without a measured reference use explicitly *provisional* bands.
Replace them by measuring real data for that market and adding it here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from marketforge.config.settings import MarketType


@dataclass(frozen=True)
class Reference:
    """Measured [min, max] of each statistic for one market."""

    source: str
    excess_kurtosis: tuple[float, float]
    vol_clustering: tuple[float, float]
    leverage: tuple[float, float]
    range_efficiency: tuple[float, float]
    abs_acf_60: tuple[float, float]


REFERENCES: dict[MarketType, Reference] = {
    MarketType.CRYPTO: Reference(
        source=(
            "Binance spot 1m klines BTCUSDT, ETHUSDT, SOLUSDT, 2024-02-01..2024-02-29 "
            "(data.binance.vision), two 14-day windows each"
        ),
        excess_kurtosis=(7.0, 649.3),
        vol_clustering=(0.131, 0.357),
        leverage=(-0.189, 0.001),
        range_efficiency=(1.504, 1.746),
        abs_acf_60=(0.065, 0.249),
    ),
}


@dataclass(frozen=True)
class Bands:
    """Validation bands for one market; None = unbounded on that side."""

    excess_kurtosis: tuple[Optional[float], Optional[float]]
    vol_clustering_min: float
    leverage_max: float
    range_efficiency: tuple[float, float]
    long_memory_min: float
    anchored: bool


def _from_reference(ref: Reference) -> Bands:
    """
    Bands with a margin around the real range: generated data must be at least
    half as fat-tailed and clustered as the least extreme real window, at most
    1.5x as fat-tailed as the most extreme, and within 0.25 of the measured
    range efficiency.
    """
    return Bands(
        excess_kurtosis=(0.5 * ref.excess_kurtosis[0], 1.5 * ref.excess_kurtosis[1]),
        vol_clustering_min=0.5 * ref.vol_clustering[0],
        leverage_max=max(0.02, ref.leverage[1]),
        range_efficiency=(ref.range_efficiency[0] - 0.25, ref.range_efficiency[1] + 0.25),
        long_memory_min=0.5 * ref.abs_acf_60[0],
        anchored=True,
    )


# Provisional bands for markets without a measured reference. They encode
# qualitative facts (fat tails, clustering, no strong positive leverage) with
# generous margins; FX gets a looser leverage ceiling because crosses have no
# natural "down" (EURAUD rises when AUD sells off).
_PROVISIONAL: dict[MarketType, Bands] = {
    MarketType.FOREX: Bands((1.0, 200.0), 0.02, 0.08, (1.2, 2.5), 0.01, anchored=False),
    MarketType.STOCKS: Bands((1.5, 200.0), 0.02, 0.02, (1.2, 2.5), 0.01, anchored=False),
}


def bands_for(market: MarketType) -> Bands:
    """Validation bands for a market: anchored to real data when available."""
    ref = REFERENCES.get(MarketType(market))
    return _from_reference(ref) if ref is not None else _PROVISIONAL[MarketType(market)]
