# MarketForge
# Copyright (C) 2026 REICHHART Damien
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""
Default parameters for different market types.

Provides sensible defaults based on historical market characteristics
for crypto, forex, and stock markets.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from marketforge.config.settings import (
    MarketType,
    GARCHParams,
    RegimeParams,
    AnomalyConfig,
    AnomalyType,
    RegimeType,
)


@dataclass(frozen=True)
class MarketDefaults:
    """
    Default parameters for a specific market type.
    
    Contains calibrated parameters based on typical market behavior.
    
    Attributes:
        market_type: The market type these defaults apply to.
        base_volatility: Typical annualized volatility.
        base_drift: Typical annualized drift.
        garch_params: Calibrated GARCH parameters.
        regime_params: Calibrated regime transition parameters.
        anomaly_config: Typical anomaly configuration.
        volume_base: Typical base volume.
        volume_volatility: Typical volume volatility.
        session_gaps: Whether this market has session gaps.
        weekend_gaps: Whether this market closes on weekends.
    """
    market_type: MarketType
    base_volatility: float
    base_drift: float
    garch_params: GARCHParams
    regime_params: RegimeParams
    anomaly_config: AnomalyConfig
    volume_base: float
    volume_volatility: float
    session_gaps: bool
    weekend_gaps: bool


# Crypto market defaults - 24/7 trading, high volatility
CRYPTO_DEFAULTS = MarketDefaults(
    market_type=MarketType.CRYPTO,
    base_volatility=0.03,  # Higher volatility for crypto
    base_drift=0.0001,
    garch_params=GARCHParams(
        omega=0.00002,  # Higher baseline volatility
        alpha=0.08,     # Stronger reaction to shocks
        beta=0.88,      # High persistence
    ),
    regime_params=RegimeParams(
        transition_matrix=(
            (0.80, 0.05, 0.10, 0.04, 0.01),  # More volatile transitions
            (0.05, 0.80, 0.10, 0.04, 0.01),
            (0.12, 0.12, 0.65, 0.09, 0.02),
            (0.06, 0.10, 0.14, 0.62, 0.08),
            (0.08, 0.08, 0.12, 0.32, 0.40),
        ),
        drift_multipliers=(2.5, -2.5, 0.0, 0.0, -6.0),
        volatility_multipliers=(0.9, 0.9, 0.7, 2.5, 5.0),
        initial_regime=RegimeType.RANGE,
    ),
    anomaly_config=AnomalyConfig(
        types=frozenset({AnomalyType.SPIKES, AnomalyType.FLASH_CRASH}),
        gap_probability=0.0,  # No gaps in 24/7 market
        spike_probability=0.001,  # More frequent spikes
        spike_magnitude_range=(0.03, 0.15),
        flash_crash_probability=0.002,
        flash_crash_magnitude=0.20,
        flash_crash_recovery_candles=20,
    ),
    volume_base=1000.0,
    volume_volatility=0.6,
    session_gaps=False,
    weekend_gaps=False,
)


# Forex market defaults - session-based with weekend gaps
FOREX_DEFAULTS = MarketDefaults(
    market_type=MarketType.FOREX,
    base_volatility=0.008,  # Lower volatility for forex
    base_drift=0.00001,
    garch_params=GARCHParams(
        omega=0.000005,
        alpha=0.04,
        beta=0.92,  # Very high persistence
    ),
    regime_params=RegimeParams(
        transition_matrix=(
            (0.88, 0.02, 0.08, 0.02, 0.00),  # More stable regimes
            (0.02, 0.88, 0.08, 0.02, 0.00),
            (0.08, 0.08, 0.78, 0.06, 0.00),
            (0.04, 0.08, 0.18, 0.68, 0.02),
            (0.10, 0.10, 0.20, 0.40, 0.20),
        ),
        drift_multipliers=(1.5, -1.5, 0.0, 0.0, -3.0),
        volatility_multipliers=(0.7, 0.7, 0.5, 1.8, 3.0),
        initial_regime=RegimeType.RANGE,
    ),
    anomaly_config=AnomalyConfig(
        types=frozenset({AnomalyType.GAPS, AnomalyType.SPIKES}),
        gap_probability=0.002,  # Session and weekend gaps
        gap_magnitude_range=(0.0005, 0.008),
        spike_probability=0.0003,
        spike_magnitude_range=(0.01, 0.05),
        flash_crash_probability=0.0002,
        flash_crash_magnitude=0.08,
        flash_crash_recovery_candles=60,
    ),
    volume_base=10000.0,
    volume_volatility=0.4,
    session_gaps=True,
    weekend_gaps=True,
)


# Stock market defaults - market hours with gaps
STOCKS_DEFAULTS = MarketDefaults(
    market_type=MarketType.STOCKS,
    base_volatility=0.015,  # Moderate volatility
    base_drift=0.0002,  # Slight upward bias
    garch_params=GARCHParams(
        omega=0.00001,
        alpha=0.05,
        beta=0.90,
    ),
    regime_params=RegimeParams(
        transition_matrix=(
            (0.85, 0.03, 0.08, 0.03, 0.01),
            (0.03, 0.85, 0.08, 0.03, 0.01),
            (0.10, 0.10, 0.70, 0.08, 0.02),
            (0.05, 0.10, 0.15, 0.65, 0.05),
            (0.05, 0.05, 0.10, 0.30, 0.50),
        ),
        drift_multipliers=(2.0, -2.0, 0.0, 0.0, -5.0),
        volatility_multipliers=(0.8, 0.8, 0.6, 2.0, 4.0),
        initial_regime=RegimeType.RANGE,
    ),
    anomaly_config=AnomalyConfig(
        types=frozenset({AnomalyType.GAPS, AnomalyType.SPIKES}),
        gap_probability=0.005,  # Overnight and weekend gaps
        gap_magnitude_range=(0.002, 0.03),
        spike_probability=0.0004,
        spike_magnitude_range=(0.02, 0.08),
        flash_crash_probability=0.0005,
        flash_crash_magnitude=0.10,
        flash_crash_recovery_candles=45,
    ),
    volume_base=100000.0,
    volume_volatility=0.5,
    session_gaps=True,
    weekend_gaps=True,
)


# Registry of market defaults
_MARKET_DEFAULTS: dict[MarketType, MarketDefaults] = {
    MarketType.CRYPTO: CRYPTO_DEFAULTS,
    MarketType.FOREX: FOREX_DEFAULTS,
    MarketType.STOCKS: STOCKS_DEFAULTS,
}


def get_market_defaults(market_type: MarketType) -> MarketDefaults:
    """
    Get default parameters for a market type.
    
    Args:
        market_type: The market type to get defaults for.
        
    Returns:
        MarketDefaults instance with calibrated parameters.
        
    Raises:
        KeyError: If market type is not recognized.
    """
    if market_type not in _MARKET_DEFAULTS:
        raise KeyError(f"Unknown market type: {market_type}")
    return _MARKET_DEFAULTS[market_type]


def get_default_volatility(market_type: MarketType) -> float:
    """Get default volatility for a market type."""
    return get_market_defaults(market_type).base_volatility


def get_default_drift(market_type: MarketType) -> float:
    """Get default drift for a market type."""
    return get_market_defaults(market_type).base_drift


def get_default_volume_base(market_type: MarketType) -> float:
    """Get default volume base for a market type."""
    return get_market_defaults(market_type).volume_base


def list_market_types() -> list[str]:
    """Return list of supported market type names."""
    return [mt.value for mt in MarketType]

