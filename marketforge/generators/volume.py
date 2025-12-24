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
Volume generation with price movement correlation.

Generates realistic trading volumes that exhibit:
- Log-normal base distribution
- Correlation with absolute returns (more activity on big moves)
- Time-of-day patterns (for session-based markets)
- Volume clustering similar to volatility clustering
"""

from __future__ import annotations

from typing import Optional
import numpy as np

from marketforge.config.settings import GeneratorConfig, MarketType
from marketforge.utils.random import RandomState
from marketforge.utils.time import get_hour_of_day


class VolumeGenerator:
    """
    Generator for realistic trading volumes.
    
    Volume in financial markets typically exhibits:
    1. Log-normal distribution (positive skew, heavy right tail)
    2. Correlation with price volatility (volume-volatility relationship)
    3. Time-of-day patterns (higher at open/close for stocks)
    4. Autocorrelation (volume clustering)
    
    The model combines these effects to produce realistic volume series.
    
    Attributes:
        config: Generator configuration.
        base_volumes: Base volume levels per asset.
        volume_volatilities: Volume volatility (log-normal sigma) per asset.
        
    Example:
        >>> config = GeneratorConfig(...)
        >>> generator = VolumeGenerator(config)
        >>> rng = RandomState(42)
        >>> volumes = generator.generate(rng, n_steps=10000, abs_returns=abs_returns)
    """
    
    def __init__(self, config: GeneratorConfig) -> None:
        """
        Initialize the volume generator.
        
        Args:
            config: Generator configuration.
        """
        self._config = config
        self._n_assets = config.n_assets
        self._market_type = config.market_type
        
        # Extract base volumes and volatilities from asset configs
        self._base_volumes = np.array([a.volume_base for a in config.assets])
        self._volume_volatilities = np.array([a.volume_volatility for a in config.assets])
    
    @property
    def config(self) -> GeneratorConfig:
        """Return generator configuration."""
        return self._config
    
    @property
    def n_assets(self) -> int:
        """Return number of assets."""
        return self._n_assets
    
    def generate(
        self,
        rng: RandomState,
        n_steps: int,
        abs_returns: Optional[np.ndarray] = None,
        volatilities: Optional[np.ndarray] = None,
        timestamps: Optional[np.ndarray] = None,
    ) -> np.ndarray:
        """
        Generate volume series for all assets.
        
        Args:
            rng: Random state for reproducibility.
            n_steps: Number of time steps.
            abs_returns: Optional absolute returns for correlation.
                        Shape (n_steps, n_assets).
            volatilities: Optional volatilities for additional scaling.
                         Shape (n_steps, n_assets).
            timestamps: Optional timestamps for time-of-day patterns.
            
        Returns:
            Array of shape (n_steps, n_assets) with volumes.
        """
        volumes = np.zeros((n_steps, self._n_assets))
        
        for i in range(self._n_assets):
            asset_abs_returns = abs_returns[:, i] if abs_returns is not None else None
            asset_volatilities = volatilities[:, i] if volatilities is not None else None
            
            volumes[:, i] = self._generate_single_asset(
                rng=rng,
                n_steps=n_steps,
                base_volume=self._base_volumes[i],
                volume_volatility=self._volume_volatilities[i],
                abs_returns=asset_abs_returns,
                volatilities=asset_volatilities,
                timestamps=timestamps,
            )
        
        return volumes
    
    def _generate_single_asset(
        self,
        rng: RandomState,
        n_steps: int,
        base_volume: float,
        volume_volatility: float,
        abs_returns: Optional[np.ndarray] = None,
        volatilities: Optional[np.ndarray] = None,
        timestamps: Optional[np.ndarray] = None,
    ) -> np.ndarray:
        """
        Generate volume series for a single asset.
        
        Args:
            rng: Random state for reproducibility.
            n_steps: Number of time steps.
            base_volume: Base volume level.
            volume_volatility: Log-normal sigma for volume.
            abs_returns: Optional absolute returns.
            volatilities: Optional volatilities.
            timestamps: Optional timestamps.
            
        Returns:
            Array of volumes.
        """
        # Step 1: Generate base log-normal volumes
        log_volume_mean = np.log(base_volume)
        base_volumes = rng.lognormal(log_volume_mean, volume_volatility, n_steps)
        
        # Step 2: Apply volume clustering (autoregressive component)
        volumes = self._apply_volume_clustering(rng, base_volumes)
        
        # Step 3: Apply return-volume correlation
        if abs_returns is not None:
            volumes = self._apply_return_correlation(volumes, abs_returns)
        
        # Step 4: Apply volatility scaling
        if volatilities is not None:
            volumes = self._apply_volatility_scaling(volumes, volatilities)
        
        # Step 5: Apply time-of-day patterns (for non-crypto)
        if timestamps is not None and self._market_type != MarketType.CRYPTO:
            volumes = self._apply_time_patterns(volumes, timestamps)
        
        # Ensure positive volumes
        volumes = np.maximum(volumes, 1.0)
        
        return volumes
    
    def _apply_volume_clustering(
        self,
        rng: RandomState,
        base_volumes: np.ndarray,
        persistence: float = 0.7
    ) -> np.ndarray:
        """
        Apply autoregressive volume clustering.
        
        High volume tends to be followed by high volume (similar to
        volatility clustering but for volume).
        
        Args:
            rng: Random state for reproducibility.
            base_volumes: Base volume series.
            persistence: AR(1) coefficient for clustering.
            
        Returns:
            Volume series with clustering.
        """
        n = len(base_volumes)
        clustered = np.zeros(n)
        
        # Initialize with first value
        clustered[0] = base_volumes[0]
        
        # AR(1) process for volume scaling
        scaling_factor = 1.0
        
        for i in range(1, n):
            # Update scaling factor with persistence
            innovation = base_volumes[i] / np.mean(base_volumes)
            scaling_factor = persistence * scaling_factor + (1 - persistence) * innovation
            
            # Apply to base volume
            clustered[i] = base_volumes[i] * np.sqrt(scaling_factor)
        
        return clustered
    
    def _apply_return_correlation(
        self,
        volumes: np.ndarray,
        abs_returns: np.ndarray,
        correlation_strength: float = 0.5
    ) -> np.ndarray:
        """
        Apply volume-return correlation.
        
        Volume tends to be higher on larger price moves (absolute returns).
        
        Args:
            volumes: Base volume series.
            abs_returns: Absolute returns.
            correlation_strength: How much returns affect volume (0-1).
            
        Returns:
            Adjusted volume series.
        """
        # Normalize absolute returns to scaling factor
        mean_abs_return = np.mean(abs_returns) + 1e-10
        return_multiplier = 1 + correlation_strength * (abs_returns / mean_abs_return - 1)
        
        # Clamp multiplier to reasonable range
        return_multiplier = np.clip(return_multiplier, 0.3, 3.0)
        
        return volumes * return_multiplier
    
    def _apply_volatility_scaling(
        self,
        volumes: np.ndarray,
        volatilities: np.ndarray,
        scaling_strength: float = 0.3
    ) -> np.ndarray:
        """
        Apply volatility-based volume scaling.
        
        Higher volatility periods tend to have higher volume.
        
        Args:
            volumes: Volume series.
            volatilities: Volatility series.
            scaling_strength: How much volatility affects volume (0-1).
            
        Returns:
            Adjusted volume series.
        """
        mean_vol = np.mean(volatilities) + 1e-10
        vol_multiplier = 1 + scaling_strength * (volatilities / mean_vol - 1)
        
        # Clamp multiplier
        vol_multiplier = np.clip(vol_multiplier, 0.5, 2.5)
        
        return volumes * vol_multiplier
    
    def _apply_time_patterns(
        self,
        volumes: np.ndarray,
        timestamps: np.ndarray
    ) -> np.ndarray:
        """
        Apply time-of-day volume patterns.
        
        For stocks: Higher volume at open (9:30) and close (16:00).
        For forex: Volume varies by session (London, NY).
        
        Args:
            volumes: Volume series.
            timestamps: Unix timestamps.
            
        Returns:
            Adjusted volume series.
        """
        hours = np.array([get_hour_of_day(ts) for ts in timestamps])
        
        if self._market_type == MarketType.STOCKS:
            # U-shaped pattern: high at open/close, low midday
            # Peak hours: 9-10 AM and 3-4 PM ET (14-15, 20-21 UTC)
            multipliers = np.ones(len(volumes))
            
            # Morning peak (14-15 UTC ~ 9-10 AM ET)
            morning_mask = (hours >= 14) & (hours < 16)
            multipliers[morning_mask] = 1.5
            
            # Afternoon peak (20-21 UTC ~ 3-4 PM ET)
            afternoon_mask = (hours >= 20) & (hours < 22)
            multipliers[afternoon_mask] = 1.8
            
            # Lunch lull (17-19 UTC ~ 12-2 PM ET)
            lunch_mask = (hours >= 17) & (hours < 20)
            multipliers[lunch_mask] = 0.7
            
        elif self._market_type == MarketType.FOREX:
            # Session-based patterns
            multipliers = np.ones(len(volumes))
            
            # London session (7-16 UTC)
            london_mask = (hours >= 7) & (hours < 16)
            multipliers[london_mask] = 1.3
            
            # NY session overlap (12-16 UTC)
            overlap_mask = (hours >= 12) & (hours < 16)
            multipliers[overlap_mask] = 1.6
            
            # Asian session (23-7 UTC) - lower volume
            asian_mask = (hours >= 23) | (hours < 7)
            multipliers[asian_mask] = 0.8
            
        else:
            multipliers = np.ones(len(volumes))
        
        return volumes * multipliers


class SimpleVolumeGenerator:
    """
    Simplified volume generator using pure log-normal distribution.
    
    Useful for quick testing when complex volume dynamics aren't needed.
    """
    
    def __init__(
        self,
        base_volume: float = 1000.0,
        sigma: float = 0.5
    ) -> None:
        """
        Initialize simple volume generator.
        
        Args:
            base_volume: Mean volume level.
            sigma: Log-normal sigma (volatility of log volume).
        """
        self._base_volume = base_volume
        self._sigma = sigma
        self._log_mean = np.log(base_volume) - sigma**2 / 2
    
    def generate(
        self,
        rng: RandomState,
        n_steps: int
    ) -> np.ndarray:
        """
        Generate simple log-normal volume series.
        
        Args:
            rng: Random state for reproducibility.
            n_steps: Number of time steps.
            
        Returns:
            Array of volumes.
        """
        return rng.lognormal(self._log_mean, self._sigma, n_steps)

