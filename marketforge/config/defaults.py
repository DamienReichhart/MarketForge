# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

"""
Per-market model parameters.

Calibrated so that generated m1 data passes the stylized-fact bands of
:mod:`marketforge.validation.report` across every instrument and seeds; run
``python scripts/benchmark_realism.py`` after changing anything here.
"""

from __future__ import annotations

from dataclasses import dataclass

from marketforge.config.model_params import (
    AnomalyConfig,
    GARCHParams,
    RegimeParams,
    SpreadParams,
    VolumeParams,
)
from marketforge.domain.markets import MarketType
from marketforge.domain.regimes import RegimeType

# Trend of a spell of each regime, in units of its volatility (see RegimeParams).
# Trends are centred so the catalog drift is the long-run drift; offsetting
# the crashes lifts every regime by ~0.3-0.4, so trend_down is set stronger
# than trend_up: after centering, a spell of either ends in its direction
# about 70-90% of the time, and a crash spell falls ~1.5 of its own (large)
# standard deviations.
TREND_STRENGTH = (1.0, -1.4, 0.0, -0.3, -1.5)


@dataclass(frozen=True)
class MarketDefaults:
    """
    Model parameters for one market.

    Attributes:
        market_type: Market these parameters apply to.
        garch_params: Volatility clustering and leverage.
        regime_params: Market-wide regime chain.
        anomaly_config: Anomaly magnitudes (which ones run is chosen per request).
        innovation_nu: Student-t degrees of freedom of shocks (None = Gaussian).
        volume_params: Volume dynamics shared by the market's instruments.
        spread_params: Quoted spread levels and dynamics (estimates).
        closure_variance_scale, closure_variance_exponent: Price variance
            accumulated over a closure of C minutes, in open-minute variances:
            scale * C ** exponent. Produces overnight and weekend gaps.
        intrabar_volatility_ratio: Fraction of the bar's volatility used for
            the high/low excursion around the open-to-close path.
    """

    market_type: MarketType
    garch_params: GARCHParams
    regime_params: RegimeParams
    anomaly_config: AnomalyConfig
    innovation_nu: float
    volume_params: VolumeParams
    spread_params: SpreadParams
    closure_variance_scale: float = 0.0
    closure_variance_exponent: float = 0.5
    # Intrabar diffusion relative to the bar's volatility. Real minutes wander
    # less inside the bar than a Brownian path would (range/body ~1.5-1.7
    # instead of 2.0), so high/low are drawn with this fraction of sigma.
    intrabar_volatility_ratio: float = 1.0
    # Volume is a count (forex tick volume): emit whole numbers, at least 1.
    integer_volume: bool = False


CRYPTO_DEFAULTS = MarketDefaults(
    market_type=MarketType.CRYPTO,
    garch_params=GARCHParams(alpha=0.03, beta=0.84, gamma=0.16),
    regime_params=RegimeParams(
        transition_matrix=(
            (0.80, 0.05, 0.10, 0.04, 0.01),
            (0.05, 0.80, 0.10, 0.04, 0.01),
            (0.12, 0.12, 0.65, 0.09, 0.02),
            (0.06, 0.10, 0.14, 0.62, 0.08),
            (0.08, 0.08, 0.12, 0.32, 0.40),
        ),
        trend_strength=TREND_STRENGTH,
        volatility_multipliers=(0.9, 0.9, 0.7, 1.8, 3.0),
        initial_regime=RegimeType.RANGE,
        # Calibrated on Binance BTC/ETH/SOL m1 (Feb 2024): trends last ~1.7
        # days and crashes ~13 h, reproducing |r| autocorrelation out to a day.
        minutes_per_step=480,
    ),
    anomaly_config=AnomalyConfig(
        spike_probability=0.001,
        spike_magnitude_range=(0.03, 0.15),
        flash_crash_probability=0.002,
        flash_crash_magnitude=0.20,
        flash_crash_recovery_candles=20,
    ),
    # The Student-t mixing variable is shared by every crypto instrument (tail
    # dependence), so a rare draw hits the whole market at once. With nu=5 that
    # produced 20-80 sigma minutes and sample kurtosis in the thousands on some
    # seeds; nu=6 keeps median m1 excess kurtosis ~10 without the blow-ups.
    innovation_nu=6.0,
    volume_params=VolumeParams(phi=0.45, lam=0.35, kappa=0.4),
    # Fitted to Binance USDT-futures best bid/ask, Feb 2024 (see
    # validation/reference.py): spreads sit on the tick, which is 0.02 bp of
    # the price for BTC and 1-2 bp for coins under a dollar, and barely move
    # with volatility (the most turbulent minutes are 0-35% wider) or with the
    # price (a tick is a fixed price increment).
    spread_params=SpreadParams(
        reference_bps=0.6,
        reference_volatility=1.0,
        volatility_exponent=0.0,
        price_exponent=-0.30,
        minimum_bps=0.015,
        fixed_scale=True,
        turbulence_exponent=0.1,
        liquidity_exponent=0.05,
        noise=0.05,
    ),
    intrabar_volatility_ratio=0.62,
)


FOREX_DEFAULTS = MarketDefaults(
    market_type=MarketType.FOREX,
    garch_params=GARCHParams(alpha=0.03, beta=0.91, gamma=0.08),
    regime_params=RegimeParams(
        transition_matrix=(
            (0.88, 0.02, 0.08, 0.02, 0.00),
            (0.02, 0.88, 0.08, 0.02, 0.00),
            (0.08, 0.08, 0.78, 0.06, 0.00),
            (0.04, 0.08, 0.18, 0.68, 0.02),
            (0.10, 0.10, 0.20, 0.40, 0.20),
        ),
        trend_strength=TREND_STRENGTH,
        volatility_multipliers=(0.7, 0.7, 0.5, 1.8, 3.0),
        initial_regime=RegimeType.RANGE,
        # Provisional (no real FX m1 reference yet): trends last ~2.8 days.
        minutes_per_step=480,
    ),
    anomaly_config=AnomalyConfig(
        spike_probability=0.0003,
        spike_magnitude_range=(0.01, 0.05),
        flash_crash_probability=0.0002,
        flash_crash_magnitude=0.08,
        flash_crash_recovery_candles=60,
    ),
    innovation_nu=10.0,
    volume_params=VolumeParams(phi=0.45, lam=0.25, kappa=0.4),
    # Estimate: ~0.6 pip on EURUSD, several bp on exotics, metals and CFDs;
    # five times wider when the week opens, back to normal within the hour.
    spread_params=SpreadParams(
        reference_bps=0.55,
        reference_volatility=0.065,
        volatility_exponent=2.5,
        minimum_bps=0.2,
        reopen_widening=4.0,
        reopen_minutes=15.0,
    ),
    intrabar_volatility_ratio=0.7,  # provisional
    integer_volume=True,  # tick volume
    # Weekend (2880 min) gap ~ sqrt(80) ~ 9 open-minute stds: ~10 pips std
    # on EURUSD, with Student-t tails for the occasional 50-pip gap.
    closure_variance_scale=1.5,
    closure_variance_exponent=0.5,
)


STOCKS_DEFAULTS = MarketDefaults(
    market_type=MarketType.STOCKS,
    # v2 used alpha=0.04, gamma=0.16: on minute data a run of negative
    # Student-t shocks compounded variance to ~260x its mean (37-sigma
    # minutes, excess kurtosis in the hundreds). gamma=0.08 keeps a clearly
    # negative leverage correlation without the blow-ups.
    garch_params=GARCHParams(alpha=0.05, beta=0.88, gamma=0.08),
    regime_params=RegimeParams(
        transition_matrix=(
            (0.85, 0.03, 0.08, 0.03, 0.01),
            (0.03, 0.85, 0.08, 0.03, 0.01),
            (0.10, 0.10, 0.70, 0.08, 0.02),
            (0.05, 0.10, 0.15, 0.65, 0.05),
            (0.05, 0.05, 0.10, 0.30, 0.50),
        ),
        trend_strength=TREND_STRENGTH,
        # A crash is the most volatile regime, as in every market (3.x had it
        # calmer than high_volatility, 1.5 against 1.8).
        volatility_multipliers=(0.8, 0.8, 0.6, 1.8, 2.6),
        initial_regime=RegimeType.RANGE,
        # Provisional (no real equity m1 reference yet): trends last ~4
        # sessions, crashes ~1 session.
        minutes_per_step=240,
    ),
    anomaly_config=AnomalyConfig(
        spike_probability=0.0004,
        spike_magnitude_range=(0.02, 0.08),
        flash_crash_probability=0.0005,
        flash_crash_magnitude=0.10,
        flash_crash_recovery_candles=45,
    ),
    innovation_nu=10.0,
    volume_params=VolumeParams(phi=0.45, lam=0.3, kappa=0.4),
    # Estimate: large caps quote one cent wide most of the day, and several
    # cents for the first minutes after the open.
    spread_params=SpreadParams(
        reference_bps=0.5,
        reference_volatility=0.25,
        volatility_exponent=1.0,
        minimum_bps=0.2,
        tick=0.01,
        reopen_widening=3.0,
        reopen_minutes=5.0,
    ),
    intrabar_volatility_ratio=0.7,  # provisional
    # Overnight (1050 min) variance ~ 0.3 of a 390-minute session; a weekend
    # adds ~40% more, in line with empirical overnight/weekend ratios.
    closure_variance_scale=20.0,
    closure_variance_exponent=0.25,
)


_MARKET_DEFAULTS: dict[MarketType, MarketDefaults] = {
    MarketType.CRYPTO: CRYPTO_DEFAULTS,
    MarketType.FOREX: FOREX_DEFAULTS,
    MarketType.STOCKS: STOCKS_DEFAULTS,
}


def get_market_defaults(market_type: MarketType) -> MarketDefaults:
    """Model parameters for a market."""
    return _MARKET_DEFAULTS[MarketType(market_type)]
