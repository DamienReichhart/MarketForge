# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the MIT License. See the LICENSE file in the project
# root for full license information.

"""
Volume generation via a log-AR(1) process.

Model: log V_t = log(base) + phi*(log V_{t-1} - log(base)) + lam*|z_t| + log s(t) + eta_t

where |z_t| is the standardized absolute return (MDH volume–|return| coupling),
s(t) is the intraday seasonality multiplier, and eta_t ~ N(0, noise_sigma).
The AR(1) persistence phi produces volume clustering; the level is re-centred to
base_volume after generation.
"""

from __future__ import annotations

from typing import Optional
import numpy as np

from marketforge.config.settings import GeneratorConfig, MarketType, VolumeParams
from marketforge.utils.random import RandomState


class VolumeGenerator:
    """
    Generator for realistic trading volumes using a log-AR(1) process.

    The model is:
        log V_t = log(base) + phi*(log V_{t-1} - log(base)) + lam*|z_t| + log s(t) + eta_t

    - AR(1) persistence (phi) produces volume clustering.
    - MDH coupling (lam) links volume to absolute standardized returns.
    - Intraday seasonality (s(t)) captures time-of-day patterns.
    - Level is re-centred to base_volume after generation.

    Attributes:
        config: Generator configuration.

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

        from marketforge.core.seasonality import SeasonalityModel
        self._volume_params = getattr(config, "volume_params", None) or VolumeParams()
        self._seasonality = SeasonalityModel(config.market_type)
        self._seasonality_enabled = getattr(config, "seasonality_enabled", True)
    
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
            volatilities: Accepted for API compatibility but NOT used by the model.
            timestamps: Optional timestamps for time-of-day patterns.
            
        Returns:
            Array of shape (n_steps, n_assets) with volumes.
        """
        volumes = np.zeros((n_steps, self._n_assets))

        if self._seasonality_enabled and timestamps is not None:
            log_seasonal = np.log(self._seasonality.multiplier_series(timestamps))
        else:
            log_seasonal = np.zeros(n_steps)

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
                log_seasonal=log_seasonal,
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
        log_seasonal: Optional[np.ndarray] = None,
    ) -> np.ndarray:
        """log V_t = mu + phi*(log V_{t-1}-mu) + lam*|z_t| + log s(t) + eta_t."""
        from scipy.signal import lfilter
        phi = self._volume_params.phi
        lam = self._volume_params.lam
        noise_sigma = self._volume_params.noise_sigma

        # Standardized absolute returns (MDH driver); 0 if not provided
        if abs_returns is not None:
            mean_abs = abs_returns.mean()
            if mean_abs > 0:
                z = np.clip(abs_returns / mean_abs, 0.0, 20.0)
            else:
                z = np.zeros(n_steps)
        else:
            z = np.zeros(n_steps)

        # Seasonal log-multiplier (variance-neutral, positive)
        log_s = log_seasonal if log_seasonal is not None else np.zeros(n_steps)

        eta = rng.normal(0.0, noise_sigma, n_steps)
        # Driver u_t for the AR(1): everything except the autoregressive memory.
        u = lam * z + log_s + eta
        # Stationary AR(1): y_t = phi*y_{t-1} + u_t  (zero-mean fluctuation of log-vol)
        y = lfilter([1.0], [1.0, -phi], u)

        log_v = np.log(base_volume) + y
        volumes = np.exp(log_v)
        # Re-center the level to base_volume (AR + |z| inject a positive mean shift)
        volumes *= base_volume / (volumes.mean() + 1e-12)
        return np.maximum(volumes, 1.0)


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

