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
Configuration dataclasses for MarketForge.

Defines all configuration parameters using dataclasses for type safety,
validation, and easy serialization.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import numpy as np


class MarketType(str, Enum):
    """Supported market types with different session behaviors."""
    CRYPTO = "crypto"
    FOREX = "forex"
    STOCKS = "stocks"


class AnomalyType(str, Enum):
    """Types of market anomalies that can be injected."""
    GAPS = "gaps"
    SPIKES = "spikes"
    FLASH_CRASH = "flash_crash"


class RegimeType(str, Enum):
    """Market regime states for regime-switching model."""
    TREND_UP = "trend_up"
    TREND_DOWN = "trend_down"
    RANGE = "range"
    HIGH_VOLATILITY = "high_volatility"
    CRASH = "crash"


@dataclass(frozen=True)
class GARCHParams:
    """
    GARCH(1,1) model parameters for conditional volatility.
    
    The GARCH(1,1) model is: σ²_t = ω + α·ε²_{t-1} + β·σ²_{t-1}
    
    Constraints:
        - ω > 0 (ensures positive variance)
        - α ≥ 0, β ≥ 0
        - α + β < 1 (stationarity condition)
    
    Attributes:
        omega: Long-term variance weight (constant term).
        alpha: Weight of lagged squared shock (ARCH term).
        beta: Weight of lagged variance (GARCH term).
    """
    omega: float = 0.00001
    alpha: float = 0.05
    beta: float = 0.90
    
    def __post_init__(self) -> None:
        """Validate GARCH parameters."""
        if self.omega <= 0:
            raise ValueError(f"omega must be positive, got {self.omega}")
        if self.alpha < 0:
            raise ValueError(f"alpha must be non-negative, got {self.alpha}")
        if self.beta < 0:
            raise ValueError(f"beta must be non-negative, got {self.beta}")
        if self.alpha + self.beta >= 1:
            raise ValueError(
                f"alpha + beta must be < 1 for stationarity, got {self.alpha + self.beta}"
            )
    
    @property
    def persistence(self) -> float:
        """Return volatility persistence (α + β)."""
        return self.alpha + self.beta
    
    @property
    def long_run_variance(self) -> float:
        """Return unconditional (long-run) variance."""
        return self.omega / (1 - self.persistence)


@dataclass(frozen=True)
class RegimeParams:
    """
    Regime-switching model parameters.
    
    Controls transition probabilities between market regimes and
    the drift/volatility multipliers for each regime state.
    
    Attributes:
        transition_matrix: Markov transition probabilities between regimes.
        drift_multipliers: Drift adjustment per regime.
        volatility_multipliers: Volatility scaling per regime.
        initial_regime: Starting regime state.
    """
    # Transition probabilities: rows are current state, cols are next state
    # Order: trend_up, trend_down, range, high_vol, crash
    transition_matrix: tuple[tuple[float, ...], ...] = (
        (0.85, 0.03, 0.08, 0.03, 0.01),  # from trend_up
        (0.03, 0.85, 0.08, 0.03, 0.01),  # from trend_down
        (0.10, 0.10, 0.70, 0.08, 0.02),  # from range
        (0.05, 0.10, 0.15, 0.65, 0.05),  # from high_vol
        (0.05, 0.05, 0.10, 0.30, 0.50),  # from crash
    )
    
    # Drift multipliers per regime
    drift_multipliers: tuple[float, ...] = (2.0, -2.0, 0.0, 0.0, -5.0)
    
    # Volatility multipliers per regime
    volatility_multipliers: tuple[float, ...] = (0.8, 0.8, 0.6, 2.0, 4.0)
    
    # Initial regime
    initial_regime: RegimeType = RegimeType.RANGE
    
    def get_regime_index(self, regime: RegimeType) -> int:
        """Get numeric index for a regime type."""
        regime_order = [
            RegimeType.TREND_UP,
            RegimeType.TREND_DOWN,
            RegimeType.RANGE,
            RegimeType.HIGH_VOLATILITY,
            RegimeType.CRASH,
        ]
        return regime_order.index(regime)


@dataclass(frozen=True)
class AnomalyConfig:
    """
    Configuration for anomaly injection.
    
    Attributes:
        types: Set of anomaly types to inject.
        gap_probability: Probability of a gap per candle (for non-crypto).
        gap_magnitude_range: Range of gap size as fraction of price.
        spike_probability: Probability of a spike per candle.
        spike_magnitude_range: Range of spike size as fraction of price.
        flash_crash_probability: Probability of flash crash per day.
        flash_crash_magnitude: Typical flash crash drop percentage.
        flash_crash_recovery_candles: Candles for V-shaped recovery.
    """
    types: frozenset[AnomalyType] = field(
        default_factory=lambda: frozenset({AnomalyType.GAPS, AnomalyType.SPIKES})
    )
    gap_probability: float = 0.001
    gap_magnitude_range: tuple[float, float] = (0.001, 0.02)
    spike_probability: float = 0.0005
    spike_magnitude_range: tuple[float, float] = (0.02, 0.10)
    flash_crash_probability: float = 0.001
    flash_crash_magnitude: float = 0.15
    flash_crash_recovery_candles: int = 30


@dataclass
class AssetConfig:
    """
    Configuration for a single asset.
    
    Attributes:
        symbol: Asset symbol (e.g., 'BTC', 'ETH').
        start_price: Initial price for the asset.
        volatility: Base annualized volatility (e.g., 0.02 for 2%).
        drift: Annualized drift/trend (e.g., 0.0001).
        volume_base: Base volume level.
        volume_volatility: Volatility of volume (log-normal sigma).
    """
    symbol: str
    start_price: float
    volatility: float = 0.02
    drift: float = 0.0001
    volume_base: float = 1000.0
    volume_volatility: float = 0.5
    
    def __post_init__(self) -> None:
        """Validate asset configuration."""
        if self.start_price <= 0:
            raise ValueError(f"start_price must be positive, got {self.start_price}")
        if self.volatility <= 0:
            raise ValueError(f"volatility must be positive, got {self.volatility}")


@dataclass
class GeneratorConfig:
    """
    Master configuration for MarketForge.
    
    Combines all sub-configurations and provides the complete
    specification for data generation.
    
    Attributes:
        assets: List of asset configurations.
        market_type: Type of market (crypto, forex, stocks).
        start_timestamp: Start of generation period (Unix timestamp).
        end_timestamp: End of generation period (Unix timestamp).
        correlation_matrix: Correlation matrix for multi-asset generation.
        garch_params: GARCH model parameters.
        regime_params: Regime-switching model parameters.
        anomaly_config: Anomaly injection configuration.
        output_dir: Directory for output files.
        seed: Random seed for reproducibility.
        timeframes: List of timeframes to generate.
        show_progress: Whether to show progress bar.
    """
    assets: list[AssetConfig]
    market_type: MarketType
    start_timestamp: int
    end_timestamp: int
    correlation_matrix: Optional[np.ndarray] = None
    garch_params: GARCHParams = field(default_factory=GARCHParams)
    regime_params: RegimeParams = field(default_factory=RegimeParams)
    anomaly_config: AnomalyConfig = field(default_factory=AnomalyConfig)
    output_dir: str = "./output"
    seed: Optional[int] = None
    timeframes: tuple[str, ...] = ("m1", "m5", "m15", "m30", "H1", "H4", "D1", "W1")
    show_progress: bool = True
    
    def __post_init__(self) -> None:
        """Validate configuration."""
        if not self.assets:
            raise ValueError("At least one asset must be configured")
        
        if self.start_timestamp >= self.end_timestamp:
            raise ValueError(
                f"start_timestamp ({self.start_timestamp}) must be less than "
                f"end_timestamp ({self.end_timestamp})"
            )
        
        n_assets = len(self.assets)
        
        if self.correlation_matrix is not None:
            if self.correlation_matrix.shape != (n_assets, n_assets):
                raise ValueError(
                    f"correlation_matrix shape {self.correlation_matrix.shape} "
                    f"doesn't match number of assets ({n_assets})"
                )
            # Verify positive semi-definite
            eigenvalues = np.linalg.eigvalsh(self.correlation_matrix)
            if np.any(eigenvalues < -1e-10):
                raise ValueError("correlation_matrix must be positive semi-definite")
    
    @property
    def n_assets(self) -> int:
        """Return number of assets."""
        return len(self.assets)
    
    @property
    def asset_symbols(self) -> list[str]:
        """Return list of asset symbols."""
        return [a.symbol for a in self.assets]
    
    @property
    def duration_minutes(self) -> int:
        """Return total duration in minutes."""
        return (self.end_timestamp - self.start_timestamp) // 60
    
    def get_correlation_matrix(self) -> np.ndarray:
        """
        Get the correlation matrix, creating identity if not specified.
        
        Returns:
            Correlation matrix as numpy array.
        """
        if self.correlation_matrix is not None:
            return self.correlation_matrix
        return np.eye(self.n_assets)

