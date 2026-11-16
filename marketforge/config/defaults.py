# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the MIT License. See the LICENSE file in the project
# root for full license information.

"""
Per-market model parameters.

Calibrated so that generated m1 data passes the stylized-fact bands of
:mod:`marketforge.validation.report` across every instrument and seeds; run
``python scripts/benchmark_realism.py`` after changing anything here.
"""

from __future__ import annotations

from dataclasses import dataclass

from marketforge.config.settings import AnomalyConfig, GARCHParams, RegimeParams, VolumeParams
from marketforge.domain.markets import MarketType
from marketforge.domain.regimes import RegimeType


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
        drift_multipliers=(2.5, -2.5, 0.0, 0.0, -6.0),
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
    # The Student-t mixing variable is shared by every crypto asset (tail
    # dependence), so a rare draw hits the whole market at once. With nu=5 that
    # produced 20-80 sigma minutes and sample kurtosis in the thousands on some
    # seeds; nu=6 keeps median m1 excess kurtosis ~10 without the blow-ups.
    innovation_nu=6.0,
    volume_params=VolumeParams(phi=0.45, lam=0.35, kappa=0.4),
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
        drift_multipliers=(1.5, -1.5, 0.0, 0.0, -3.0),
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
        drift_multipliers=(2.0, -2.0, 0.0, 0.0, -5.0),
        volatility_multipliers=(0.8, 0.8, 0.6, 1.8, 1.5),
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
