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
Return generator combining GBM, GARCH, and regime-switching models.

This is the core price simulation engine that generates realistic
log-returns for multiple correlated assets.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import numpy as np

from marketforge.config.settings import (
    GeneratorConfig,
    AssetConfig,
    GARCHParams,
    RegimeParams,
)
from marketforge.core.correlation import CorrelationEngine, create_correlation_engine
from marketforge.core.garch import GARCHModel, MultiAssetGARCH
from marketforge.core.regimes import RegimeModel, SmoothRegimeModel
from marketforge.utils.random import RandomState


@dataclass
class ReturnSeriesResult:
    """
    Result of return series generation.
    
    Contains all generated data including returns, prices, volatilities,
    and regime information.
    
    Attributes:
        returns: Log returns array of shape (n_steps, n_assets).
        prices: Price series array of shape (n_steps, n_assets).
        volatilities: Conditional volatilities of shape (n_steps, n_assets).
        regime_indices: Regime states of shape (n_steps,).
        timestamps: Unix timestamps for each step.
        asset_symbols: List of asset symbols.
    """
    returns: np.ndarray
    prices: np.ndarray
    volatilities: np.ndarray
    regime_indices: np.ndarray
    timestamps: np.ndarray
    asset_symbols: list[str]
    
    @property
    def n_steps(self) -> int:
        """Return number of time steps."""
        return len(self.timestamps)
    
    @property
    def n_assets(self) -> int:
        """Return number of assets."""
        return len(self.asset_symbols)
    
    def get_asset_data(self, symbol: str) -> dict:
        """
        Get data for a specific asset.
        
        Args:
            symbol: Asset symbol.
            
        Returns:
            Dictionary with asset-specific data.
        """
        idx = self.asset_symbols.index(symbol)
        return {
            "symbol": symbol,
            "returns": self.returns[:, idx],
            "prices": self.prices[:, idx],
            "volatilities": self.volatilities[:, idx],
            "timestamps": self.timestamps,
        }


class ReturnGenerator:
    """
    Multi-asset return generator with realistic dynamics.
    
    Combines three key components:
    1. Correlated innovations via Cholesky decomposition
    2. GARCH(1,1) for volatility clustering
    3. Regime-switching for market state dynamics
    
    The resulting returns follow:
        r_t = μ_t * Δt + σ_t * √Δt * z_t
        
    where:
        - μ_t is the regime-adjusted drift
        - σ_t is the GARCH conditional volatility
        - z_t is the correlated standard normal innovation
    
    Attributes:
        config: Generator configuration.
        correlation_engine: Engine for correlated innovations.
        garch_models: GARCH models per asset.
        regime_model: Regime-switching model.
        
    Example:
        >>> config = GeneratorConfig(...)
        >>> generator = ReturnGenerator(config)
        >>> rng = RandomState(42)
        >>> result = generator.generate(rng, n_steps=10000)
    """
    
    # Time scaling: per-minute to annualized
    MINUTES_PER_YEAR = 252 * 24 * 60  # Trading days * hours * minutes
    DT = 1.0 / MINUTES_PER_YEAR  # Time step in years
    SQRT_DT = np.sqrt(DT)
    
    def __init__(self, config: GeneratorConfig) -> None:
        """
        Initialize the return generator.
        
        Args:
            config: Complete generator configuration.
        """
        self._config = config
        self._n_assets = config.n_assets
        self._asset_configs = config.assets
        
        # Initialize correlation engine
        self._correlation_engine = CorrelationEngine(config.get_correlation_matrix())
        
        # Initialize GARCH models for each asset
        self._garch_models = [
            GARCHModel(config.garch_params, asset.volatility)
            for asset in config.assets
        ]
        
        # Initialize regime model (using smooth transitions)
        self._regime_model = SmoothRegimeModel(
            config.regime_params,
            transition_window=30
        )
    
    @property
    def config(self) -> GeneratorConfig:
        """Return generator configuration."""
        return self._config
    
    @property
    def n_assets(self) -> int:
        """Return number of assets."""
        return self._n_assets
    
    @property
    def asset_symbols(self) -> list[str]:
        """Return list of asset symbols."""
        return [a.symbol for a in self._asset_configs]
    
    def reset(self) -> None:
        """Reset all internal models to initial state."""
        for model in self._garch_models:
            model.reset()
        self._regime_model.reset()
    
    def generate(
        self,
        rng: RandomState,
        timestamps: Optional[np.ndarray] = None,
        n_steps: Optional[int] = None
    ) -> ReturnSeriesResult:
        """
        Generate correlated return series for all assets.
        
        Args:
            rng: Random state for reproducibility.
            timestamps: Optional array of Unix timestamps.
            n_steps: Number of steps if timestamps not provided.
            
        Returns:
            ReturnSeriesResult with all generated data.
        """
        # Determine number of steps
        if timestamps is not None:
            n_steps = len(timestamps)
        elif n_steps is None:
            # Generate timestamps array first, then derive n_steps from its length
            # This ensures consistency (np.arange may produce +1 elements when
            # duration is not evenly divisible by 60)
            timestamps = np.arange(
                self._config.start_timestamp,
                self._config.end_timestamp,
                60,
                dtype=np.int64
            )
            n_steps = len(timestamps)
        else:
            timestamps = np.arange(n_steps, dtype=np.int64) * 60
        
        # Reset models
        self.reset()
        
        # Step 1: Generate correlated standard normal innovations
        innovations = self._correlation_engine.generate_correlated_normals(rng, n_steps)
        
        # Step 2: Generate regime series with multipliers
        regime_indices, drift_mults, vol_mults = self._regime_model.generate_smooth_multiplier_series(
            rng, n_steps
        )
        
        # Step 3: Generate GARCH volatilities for each asset
        volatilities = np.zeros((n_steps, self._n_assets))
        for i, (model, asset) in enumerate(zip(self._garch_models, self._asset_configs)):
            model.initialize_state()
            base_vols = model.generate_volatility_series(rng, n_steps, innovations[:, i])
            # Apply regime volatility multiplier
            volatilities[:, i] = base_vols * vol_mults
        
        # Step 4: Compute returns
        returns = np.zeros((n_steps, self._n_assets))
        for i, asset in enumerate(self._asset_configs):
            # Base drift adjusted by regime
            base_drift = asset.drift * self.DT
            adjusted_drift = base_drift * drift_mults
            
            # Return: r_t = μ_t + σ_t * z_t
            returns[:, i] = adjusted_drift + volatilities[:, i] * innovations[:, i]
        
        # Step 5: Compute price series from returns
        prices = self._compute_prices(returns)
        
        return ReturnSeriesResult(
            returns=returns,
            prices=prices,
            volatilities=volatilities,
            regime_indices=regime_indices,
            timestamps=timestamps,
            asset_symbols=self.asset_symbols,
        )
    
    def _compute_prices(self, returns: np.ndarray) -> np.ndarray:
        """
        Compute price series from log returns.
        
        Uses the formula: P_t = P_0 * exp(sum(r_1:t))
        
        Args:
            returns: Log returns array of shape (n_steps, n_assets).
            
        Returns:
            Price series of shape (n_steps, n_assets).
        """
        n_steps = returns.shape[0]
        prices = np.zeros((n_steps, self._n_assets))
        
        for i, asset in enumerate(self._asset_configs):
            # Cumulative returns
            cumulative_returns = np.cumsum(returns[:, i])
            # Prices from start price
            prices[:, i] = asset.start_price * np.exp(cumulative_returns)
        
        return prices
    
    def generate_single_asset(
        self,
        rng: RandomState,
        asset_index: int,
        n_steps: int
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Generate returns for a single asset (no correlation).
        
        Useful for testing or when generating assets independently.
        
        Args:
            rng: Random state for reproducibility.
            asset_index: Index of asset to generate.
            n_steps: Number of time steps.
            
        Returns:
            Tuple of (returns, prices, volatilities).
        """
        asset = self._asset_configs[asset_index]
        garch_model = self._garch_models[asset_index]
        
        # Generate innovations
        innovations = rng.standard_normal(n_steps)
        
        # Generate regime multipliers
        regime_indices, drift_mults, vol_mults = self._regime_model.generate_smooth_multiplier_series(
            rng, n_steps
        )
        
        # Generate GARCH volatilities
        garch_model.reset()
        garch_model.initialize_state()
        base_vols = garch_model.generate_volatility_series(rng, n_steps, innovations)
        volatilities = base_vols * vol_mults
        
        # Compute returns
        base_drift = asset.drift * self.DT
        adjusted_drift = base_drift * drift_mults
        returns = adjusted_drift + volatilities * innovations
        
        # Compute prices
        cumulative_returns = np.cumsum(returns)
        prices = asset.start_price * np.exp(cumulative_returns)
        
        return returns, prices, volatilities


class SimpleReturnGenerator:
    """
    Simplified return generator using pure GBM without GARCH/regimes.
    
    Useful for quick testing or when complex dynamics aren't needed.
    """
    
    MINUTES_PER_YEAR = 252 * 24 * 60
    DT = 1.0 / MINUTES_PER_YEAR
    SQRT_DT = np.sqrt(DT)
    
    def __init__(
        self,
        start_prices: list[float],
        volatilities: list[float],
        drifts: list[float],
        correlation_matrix: Optional[np.ndarray] = None
    ) -> None:
        """
        Initialize simple return generator.
        
        Args:
            start_prices: Starting prices for each asset.
            volatilities: Annualized volatilities.
            drifts: Annualized drifts.
            correlation_matrix: Optional correlation matrix.
        """
        self._n_assets = len(start_prices)
        self._start_prices = np.array(start_prices)
        self._volatilities = np.array(volatilities)
        self._drifts = np.array(drifts)
        
        if correlation_matrix is None:
            correlation_matrix = np.eye(self._n_assets)
        
        self._correlation_engine = CorrelationEngine(correlation_matrix)
    
    def generate(
        self,
        rng: RandomState,
        n_steps: int
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        Generate simple GBM returns and prices.
        
        Args:
            rng: Random state for reproducibility.
            n_steps: Number of time steps.
            
        Returns:
            Tuple of (prices, returns) arrays.
        """
        # Generate correlated innovations
        innovations = self._correlation_engine.generate_correlated_normals(rng, n_steps)
        
        # Compute returns for each asset
        returns = np.zeros((n_steps, self._n_assets))
        for i in range(self._n_assets):
            drift_term = self._drifts[i] * self.DT
            vol_term = self._volatilities[i] * self.SQRT_DT * innovations[:, i]
            returns[:, i] = drift_term + vol_term
        
        # Compute prices
        prices = np.zeros((n_steps, self._n_assets))
        for i in range(self._n_assets):
            cumulative = np.cumsum(returns[:, i])
            prices[:, i] = self._start_prices[i] * np.exp(cumulative)
        
        return prices, returns

