# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the MIT License. See the LICENSE file in the project
# root for full license information.

"""
GARCH(1,1) volatility model implementation.

Implements the Generalized Autoregressive Conditional Heteroskedasticity
model for realistic volatility clustering in financial time series.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import numpy as np

from marketforge.config.settings import GARCHParams
from marketforge.utils.random import RandomState


@dataclass
class GARCHState:
    """
    Current state of the GARCH model.
    
    Tracks the evolving variance and shock for the recursive
    GARCH computation.
    
    Attributes:
        variance: Current conditional variance σ²_t.
        shock: Last shock/innovation ε_{t-1}.
        volatility: Current conditional volatility σ_t = √σ²_t.
    """
    variance: float
    shock: float
    
    @property
    def volatility(self) -> float:
        """Return conditional volatility (standard deviation)."""
        return np.sqrt(self.variance)


class GARCHModel:
    """
    GARCH(1,1) model for conditional volatility simulation.
    
    The GARCH(1,1) model captures volatility clustering, a key feature
    of financial time series where large changes tend to follow large
    changes and small changes tend to follow small changes.
    
    Model Specification:
        σ²_t = ω + (α + γ·1[ε_{t-1}<0])·ε²_{t-1} + β·σ²_{t-1}

    where:
        - σ²_t is the conditional variance at time t
        - ω is the constant term (omega)
        - α is the ARCH coefficient (reaction to shocks)
        - γ is the leverage coefficient: negative shocks (ε_{t-1} < 0) raise
          volatility more than positive shocks of the same magnitude
        - β is the GARCH coefficient (persistence)
        - ε_{t-1} is the previous shock

    Properties:
        - Stationarity requires: α + β + γ/2 < 1
        - Unconditional variance: ω / (1 - α - β - γ/2)
        - Half-life of volatility shocks: log(0.5) / log(α + β + γ/2)
    
    Attributes:
        params: GARCH parameters (omega, alpha, beta).
        base_volatility: Base volatility level for scaling.
        
    Example:
        >>> params = GARCHParams(omega=0.00001, alpha=0.05, beta=0.90)
        >>> model = GARCHModel(params, base_volatility=0.02)
        >>> rng = RandomState(42)
        >>> volatilities = model.generate_volatility_series(rng, 1000)
    """
    
    def __init__(
        self,
        params: GARCHParams,
        base_volatility: float = 0.02
    ) -> None:
        """
        Initialize the GARCH model.
        
        Args:
            params: GARCH(1,1) parameters.
            base_volatility: Base volatility level (annualized) for scaling.
        """
        self._params = params
        self._base_volatility = base_volatility
        
        # Scale omega to match base volatility
        # We want long-run volatility = base_volatility
        # Long-run variance = omega / (1 - alpha - beta - gamma/2)
        # So omega = target_variance * (1 - persistence)
        target_variance = (base_volatility ** 2) / (252 * 24 * 60)  # Per-minute
        persistence = params.persistence  # alpha + beta + gamma/2
        self._scaled_omega = target_variance * (1 - persistence)
        self._initial_variance = self._scaled_omega / (1 - persistence)
        self._state: Optional[GARCHState] = None
    
    @property
    def params(self) -> GARCHParams:
        """Return GARCH parameters."""
        return self._params
    
    @property
    def base_volatility(self) -> float:
        """Return base volatility level."""
        return self._base_volatility
    
    @property
    def unconditional_variance(self) -> float:
        """Return the unconditional (long-run) variance."""
        return self._initial_variance
    
    @property
    def unconditional_volatility(self) -> float:
        """Return the unconditional (long-run) volatility."""
        return np.sqrt(self._initial_variance)
    
    @property
    def half_life(self) -> float:
        """
        Return the half-life of volatility shocks in periods.
        
        This indicates how long it takes for a volatility shock
        to decay to half its initial impact.
        """
        persistence = self._params.persistence
        if persistence >= 1 or persistence <= 0:
            return float('inf')
        return np.log(0.5) / np.log(persistence)
    
    @property
    def current_state(self) -> Optional[GARCHState]:
        """Return current GARCH state if initialized."""
        return self._state
    
    def reset(self) -> None:
        """Reset the model state to initial conditions."""
        self._state = None
    
    def initialize_state(
        self,
        initial_variance: Optional[float] = None,
        initial_shock: float = 0.0
    ) -> GARCHState:
        """
        Initialize the GARCH state.
        
        Args:
            initial_variance: Starting variance. Uses unconditional if None.
            initial_shock: Starting shock value.
            
        Returns:
            The initialized GARCHState.
        """
        variance = initial_variance if initial_variance is not None else self._initial_variance
        self._state = GARCHState(variance=variance, shock=initial_shock)
        return self._state
    
    def step(self, innovation: float) -> GARCHState:
        """
        Advance the GJR-GARCH model by one step.

        Implements the asymmetric GJR-GARCH(1,1) update:
            σ²_t = ω + (α + γ·1[ε_{t-1}<0])·ε²_{t-1} + β·σ²_{t-1}

        The leverage indicator keys off the sign of the previous shock ε_{t-1}.
        When γ=0 this reduces to the classic symmetric GARCH(1,1) update.

        Args:
            innovation: Standard normal innovation z_t.

        Returns:
            Updated GARCHState with new variance.

        Raises:
            RuntimeError: If model not initialized.
        """
        if self._state is None:
            self.initialize_state()

        prev_shock = self._state.shock
        # Leverage indicator on the sign of the previous shock ε_{t-1}
        leverage = self._params.gamma if prev_shock < 0 else 0.0

        new_variance = (
            self._scaled_omega
            + (self._params.alpha + leverage) * (prev_shock ** 2)
            + self._params.beta * self._state.variance
        )

        new_volatility = np.sqrt(new_variance)
        new_shock = new_volatility * innovation

        self._state = GARCHState(variance=new_variance, shock=new_shock)
        return self._state
    
    def generate_volatility_series(
        self,
        rng: RandomState,
        n_steps: int,
        innovations: Optional[np.ndarray] = None
    ) -> np.ndarray:
        """
        Generate a series of conditional volatilities.
        
        Args:
            rng: Random state for reproducibility.
            n_steps: Number of time steps to generate.
            innovations: Optional pre-generated standard normal innovations.
                        If None, generates new ones.
                        
        Returns:
            Array of shape (n_steps,) with conditional volatilities.
        """
        if innovations is None:
            innovations = rng.standard_normal(n_steps)
        
        if len(innovations) != n_steps:
            raise ValueError(
                f"innovations length {len(innovations)} != n_steps {n_steps}"
            )
        
        # Initialize if needed
        if self._state is None:
            self.initialize_state()
        
        volatilities = np.zeros(n_steps)
        
        for i in range(n_steps):
            state = self.step(innovations[i])
            volatilities[i] = state.volatility
        
        return volatilities
    
    def generate_returns(
        self,
        rng: RandomState,
        n_steps: int,
        drift: float = 0.0,
        innovations: Optional[np.ndarray] = None
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        Generate returns with GARCH volatility.
        
        Args:
            rng: Random state for reproducibility.
            n_steps: Number of time steps.
            drift: Drift term (per-minute).
            innovations: Optional pre-generated innovations.
            
        Returns:
            Tuple of (returns, volatilities) arrays.
        """
        if innovations is None:
            innovations = rng.standard_normal(n_steps)
        
        volatilities = self.generate_volatility_series(rng, n_steps, innovations)
        
        # Returns: r_t = μ + σ_t · z_t
        returns = drift + volatilities * innovations
        
        return returns, volatilities


class MultiAssetGARCH:
    """
    Multi-asset GARCH model with individual parameters per asset.
    
    Allows each asset to have its own GARCH dynamics while sharing
    correlated innovations.
    
    Attributes:
        models: List of individual GARCH models per asset.
        n_assets: Number of assets.
    """
    
    def __init__(
        self,
        params_list: list[GARCHParams],
        base_volatilities: list[float]
    ) -> None:
        """
        Initialize multi-asset GARCH.
        
        Args:
            params_list: GARCH parameters for each asset.
            base_volatilities: Base volatility for each asset.
        """
        if len(params_list) != len(base_volatilities):
            raise ValueError(
                f"params_list length {len(params_list)} != "
                f"base_volatilities length {len(base_volatilities)}"
            )
        
        self._models = [
            GARCHModel(params, vol)
            for params, vol in zip(params_list, base_volatilities)
        ]
        self._n_assets = len(self._models)
    
    @property
    def n_assets(self) -> int:
        """Return number of assets."""
        return self._n_assets
    
    @property
    def models(self) -> list[GARCHModel]:
        """Return list of individual GARCH models."""
        return self._models
    
    def reset(self) -> None:
        """Reset all models to initial state."""
        for model in self._models:
            model.reset()
    
    def generate_volatility_series(
        self,
        rng: RandomState,
        n_steps: int,
        correlated_innovations: Optional[np.ndarray] = None
    ) -> np.ndarray:
        """
        Generate volatility series for all assets.
        
        Args:
            rng: Random state for reproducibility.
            n_steps: Number of time steps.
            correlated_innovations: Optional pre-generated correlated innovations
                                   of shape (n_steps, n_assets).
                                   
        Returns:
            Array of shape (n_steps, n_assets) with volatilities.
        """
        if correlated_innovations is None:
            correlated_innovations = rng.standard_normal((n_steps, self._n_assets))
        
        volatilities = np.zeros((n_steps, self._n_assets))
        
        for asset_idx, model in enumerate(self._models):
            model.reset()
            model.initialize_state()
            volatilities[:, asset_idx] = model.generate_volatility_series(
                rng, n_steps, correlated_innovations[:, asset_idx]
            )
        
        return volatilities

