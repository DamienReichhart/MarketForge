# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

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

from dataclasses import dataclass, replace

from marketforge.domain.markets import MarketType


@dataclass(frozen=True)
class Reference:
    """Measured [min, max] of each statistic for one market."""

    source: str
    excess_kurtosis: tuple[float, float]
    vol_clustering: tuple[float, float]
    leverage: tuple[float, float]
    range_efficiency: tuple[float, float]
    abs_acf_60: tuple[float, float]
    # Quoted spread, where best bid/ask data has been measured.
    spread_source: str = ""
    spread_bps: tuple[float, float] | None = None
    spread_widening: tuple[float, float] | None = None
    # Measured since 5.0 (scripts/measure_real_data.py, same files).
    return_autocorrelation: tuple[float, float] | None = None
    hourly_kurtosis: tuple[float, float] | None = None
    volume_volatility: tuple[float, float] | None = None


REFERENCES: dict[MarketType, Reference] = {
    MarketType.CRYPTO: Reference(
        source=(
            "Binance spot 1m klines BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT, DOGEUSDT, TRXUSDT, "
            "LINKUSDT, 2024-02-01..2024-02-28 (data.binance.vision), two 14-day windows each"
        ),
        # The three majors alone span 7.0-649.3; a fortnight of XRP reaches 1331.
        excess_kurtosis=(7.0, 1331.0),
        vol_clustering=(0.128, 0.404),
        leverage=(-0.189, 0.057),
        range_efficiency=(1.504, 1.746),
        abs_acf_60=(0.064, 0.335),
        spread_source=(
            "Binance USDT-futures best bid/ask (bookTicker), mean spread per minute: "
            "XRPUSDT, DOGEUSDT, TRXUSDT, LINKUSDT 2024-02-01..2024-02-28 (two 14-day windows "
            "each); BTCUSDT, ETHUSDT, SOLUSDT 2024-02-01 only (one day each)"
        ),
        spread_bps=(0.024, 1.946),
        spread_widening=(1.004, 1.347),
        # Spot klines are trade prices, which bounce off the bid and ask
        # (ETHUSDT -0.118 for a fortnight); MarketForge's are quoted mids.
        return_autocorrelation=(-0.118, 0.050),
        hourly_kurtosis=(0.251, 93.296),
        volume_volatility=(0.397, 0.554),
    ),
}


@dataclass(frozen=True)
class Bands:
    """Validation bands for one market; None = unbounded on that side."""

    excess_kurtosis: tuple[float | None, float | None]
    vol_clustering_min: float
    leverage_max: float
    range_efficiency: tuple[float, float]
    long_memory_min: float
    anchored: bool
    # Spread bands. Without measured quotes they are provisional and only rule
    # out the absurd (docs/adr/0008): a median outside 0.05-40 basis points, or
    # spreads that clearly narrow in the most turbulent minutes. A holiday's
    # thin hours are quiet and wide, which pulls the ratio a little below 1.
    spread_bps: tuple[float, float] = (0.05, 40.0)
    spread_widening: tuple[float, float | None] = (0.85, None)
    spread_anchored: bool = False
    # Since 5.0. Provisional unless measured: minute returns barely
    # autocorrelate, hourly returns keep heavier tails than a normal's (but
    # lighter than minutes'), big moves trade more, gaps hold a share of the
    # variance where markets close, and regime spells last a typical length.
    return_autocorrelation: tuple[float, float] = (-0.25, 0.1)
    hourly_kurtosis: tuple[float, float] = (0.0, 200.0)
    volume_volatility_min: float = 0.1
    gap_variance_share: tuple[float, float] = (0.03, 0.6)
    spell_variation: tuple[float, float] = (0.3, 0.95)
    extra_anchored: bool = False


def _from_reference(ref: Reference) -> Bands:
    """
    Bands with a margin around the real range: generated data must be at least
    half as fat-tailed and clustered as the least extreme real window, at most
    1.5x as fat-tailed as the most extreme, and within 0.25 of the measured
    range efficiency. Where quotes were measured, the median spread must be
    within a factor two of the measured range, and spreads must widen in
    turbulence no less than 0.1 below and no more than 0.25 above it.
    """
    bands = Bands(
        excess_kurtosis=(0.5 * ref.excess_kurtosis[0], 1.5 * ref.excess_kurtosis[1]),
        vol_clustering_min=0.5 * ref.vol_clustering[0],
        leverage_max=max(0.02, ref.leverage[1]),
        range_efficiency=(ref.range_efficiency[0] - 0.25, ref.range_efficiency[1] + 0.25),
        long_memory_min=0.5 * ref.abs_acf_60[0],
        anchored=True,
    )
    if ref.return_autocorrelation and ref.hourly_kurtosis and ref.volume_volatility:
        bands = replace(
            bands,
            return_autocorrelation=(
                ref.return_autocorrelation[0] - 0.05,
                ref.return_autocorrelation[1] + 0.03,
            ),
            hourly_kurtosis=(0.5 * ref.hourly_kurtosis[0], 1.5 * ref.hourly_kurtosis[1]),
            volume_volatility_min=0.5 * ref.volume_volatility[0],
            extra_anchored=True,
        )
    if ref.spread_bps is None or ref.spread_widening is None:
        return bands
    return replace(
        bands,
        spread_bps=(0.5 * ref.spread_bps[0], 2.0 * ref.spread_bps[1]),
        spread_widening=(ref.spread_widening[0] - 0.1, ref.spread_widening[1] + 0.25),
        spread_anchored=True,
    )


# Provisional bands for markets without a measured reference. They encode
# qualitative facts (fat tails, clustering, no strong positive leverage) with
# generous margins; FX gets a looser leverage ceiling because crosses have no
# natural "down" (EURAUD rises when AUD sells off).
_PROVISIONAL: dict[MarketType, Bands] = {
    # Forex closes only at the weekend: its gaps hold a sliver of the variance.
    # Its spreads are tightest in its busiest hours (London and New York), which
    # are most of the turbulent tenth of a calm fortnight's minutes: the ratio
    # may sit a little below 1 without anything being wrong.
    MarketType.FOREX: Bands(
        (1.0, 200.0),
        0.02,
        0.08,
        (1.2, 2.5),
        0.01,
        anchored=False,
        spread_widening=(0.7, None),
        gap_variance_share=(0.0, 0.1),
    ),
    MarketType.STOCKS: Bands((1.5, 200.0), 0.02, 0.02, (1.2, 2.5), 0.01, anchored=False),
}


def bands_for(market: MarketType) -> Bands:
    """Validation bands for a market: anchored to real data when available."""
    ref = REFERENCES.get(MarketType(market))
    return _from_reference(ref) if ref is not None else _PROVISIONAL[MarketType(market)]
