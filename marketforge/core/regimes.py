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
Regime-switching model for market state simulation.

Implements a Markov regime-switching model to capture different market
states (trending, ranging, high volatility, crash) with realistic
transition dynamics.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Optional
import numpy as np

from marketforge.config.settings import RegimeParams, RegimeType
from marketforge.utils.random import RandomState


class RegimeIndex(IntEnum):
    """Numeric indices for regime types."""
    TREND_UP = 0
    TREND_DOWN = 1
    RANGE = 2
    HIGH_VOLATILITY = 3
    CRASH = 4


@dataclass
class RegimeState:
    """
    Current state of the regime model.
    
    Attributes:
        regime: Current regime type.
        regime_index: Numeric index of current regime.
        drift_multiplier: Drift adjustment for current regime.
        volatility_multiplier: Volatility scaling for current regime.
        duration: Number of periods in current regime.
    """
    regime: RegimeType
    regime_index: int
    drift_multiplier: float
    volatility_multiplier: float
    duration: int = 1


class RegimeModel:
    """
    Markov regime-switching model for market dynamics.
    
    This model simulates transitions between different market regimes:
    - TREND_UP: Strong upward trend with moderate volatility
    - TREND_DOWN: Downward trend with moderate volatility
    - RANGE: Sideways/ranging market with low volatility
    - HIGH_VOLATILITY: Choppy market with elevated volatility
    - CRASH: Sharp decline with very high volatility
    
    The transitions follow a Markov chain with configurable transition
    probabilities, allowing realistic regime persistence and switching.
    
    Attributes:
        params: Regime model parameters.
        current_state: Current regime state.
        
    Example:
        >>> params = RegimeParams()  # Use defaults
        >>> model = RegimeModel(params)
        >>> rng = RandomState(42)
        >>> regimes = model.generate_regime_series(rng, 10000)
    """
    
    REGIME_ORDER = [
        RegimeType.TREND_UP,
        RegimeType.TREND_DOWN,
        RegimeType.RANGE,
        RegimeType.HIGH_VOLATILITY,
        RegimeType.CRASH,
    ]
    
    def __init__(self, params: RegimeParams) -> None:
        """
        Initialize the regime model.
        
        Args:
            params: Regime transition and multiplier parameters.
        """
        self._params = params
        self._transition_matrix = np.array(params.transition_matrix)
        self._drift_multipliers = np.array(params.drift_multipliers)
        self._volatility_multipliers = np.array(params.volatility_multipliers)
        
        # Validate transition matrix
        self._validate_transition_matrix()
        
        # Initialize state
        initial_idx = self.REGIME_ORDER.index(params.initial_regime)
        self._state = RegimeState(
            regime=params.initial_regime,
            regime_index=initial_idx,
            drift_multiplier=self._drift_multipliers[initial_idx],
            volatility_multiplier=self._volatility_multipliers[initial_idx],
            duration=1,
        )
    
    def _validate_transition_matrix(self) -> None:
        """Validate that transition matrix rows sum to 1."""
        row_sums = self._transition_matrix.sum(axis=1)
        if not np.allclose(row_sums, 1.0, atol=1e-6):
            raise ValueError(
                f"Transition matrix rows must sum to 1, got {row_sums}"
            )
    
    @property
    def params(self) -> RegimeParams:
        """Return regime parameters."""
        return self._params
    
    @property
    def current_state(self) -> RegimeState:
        """Return current regime state."""
        return self._state
    
    @property
    def n_regimes(self) -> int:
        """Return number of regimes."""
        return len(self.REGIME_ORDER)
    
    def reset(self) -> None:
        """Reset to initial state."""
        initial_idx = self.REGIME_ORDER.index(self._params.initial_regime)
        self._state = RegimeState(
            regime=self._params.initial_regime,
            regime_index=initial_idx,
            drift_multiplier=self._drift_multipliers[initial_idx],
            volatility_multiplier=self._volatility_multipliers[initial_idx],
            duration=1,
        )
    
    def step(self, rng: RandomState) -> RegimeState:
        """
        Advance the regime model by one step.
        
        Uses the Markov transition probabilities to potentially
        switch to a new regime.
        
        Args:
            rng: Random state for reproducibility.
            
        Returns:
            Updated RegimeState.
        """
        current_idx = self._state.regime_index
        
        # Sample next regime from transition probabilities
        probs = self._transition_matrix[current_idx]
        next_idx = rng.choice(self.n_regimes, p=probs)
        
        # Update state
        if next_idx == current_idx:
            # Same regime, increment duration
            self._state = RegimeState(
                regime=self._state.regime,
                regime_index=current_idx,
                drift_multiplier=self._drift_multipliers[current_idx],
                volatility_multiplier=self._volatility_multipliers[current_idx],
                duration=self._state.duration + 1,
            )
        else:
            # New regime
            self._state = RegimeState(
                regime=self.REGIME_ORDER[next_idx],
                regime_index=next_idx,
                drift_multiplier=self._drift_multipliers[next_idx],
                volatility_multiplier=self._volatility_multipliers[next_idx],
                duration=1,
            )
        
        return self._state
    
    def generate_regime_series(
        self,
        rng: RandomState,
        n_steps: int
    ) -> np.ndarray:
        """
        Generate a series of regime indices.
        
        Args:
            rng: Random state for reproducibility.
            n_steps: Number of time steps.
            
        Returns:
            Array of shape (n_steps,) with regime indices.
        """
        self.reset()
        regimes = np.zeros(n_steps, dtype=np.int32)
        
        regimes[0] = self._state.regime_index
        
        for i in range(1, n_steps):
            self.step(rng)
            regimes[i] = self._state.regime_index
        
        return regimes
    
    def generate_multiplier_series(
        self,
        rng: RandomState,
        n_steps: int
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Generate regime indices and corresponding multipliers.
        
        Args:
            rng: Random state for reproducibility.
            n_steps: Number of time steps.
            
        Returns:
            Tuple of (regime_indices, drift_multipliers, volatility_multipliers).
        """
        regimes = self.generate_regime_series(rng, n_steps)
        
        drift_mults = self._drift_multipliers[regimes]
        vol_mults = self._volatility_multipliers[regimes]
        
        return regimes, drift_mults, vol_mults
    
    def get_regime_statistics(self, regime_series: np.ndarray) -> dict:
        """
        Compute statistics about a regime series.
        
        Args:
            regime_series: Array of regime indices.
            
        Returns:
            Dictionary with regime statistics.
        """
        n_steps = len(regime_series)
        stats = {}
        
        for regime in self.REGIME_ORDER:
            idx = self.REGIME_ORDER.index(regime)
            mask = regime_series == idx
            count = mask.sum()
            
            # Calculate average duration
            if count > 0:
                # Find runs of this regime
                changes = np.diff(mask.astype(int))
                starts = np.where(changes == 1)[0] + 1
                ends = np.where(changes == -1)[0] + 1
                
                # Handle edge cases
                if mask[0]:
                    starts = np.concatenate([[0], starts])
                if mask[-1]:
                    ends = np.concatenate([ends, [n_steps]])
                
                durations = ends - starts
                avg_duration = durations.mean() if len(durations) > 0 else 0
            else:
                avg_duration = 0
            
            stats[regime.value] = {
                "count": int(count),
                "fraction": count / n_steps,
                "avg_duration": float(avg_duration),
            }
        
        return stats
    
    def get_stationary_distribution(self) -> np.ndarray:
        """
        Compute the stationary distribution of regimes.
        
        Returns:
            Array of stationary probabilities for each regime.
        """
        # Solve π = π @ P for stationary distribution
        # Equivalent to finding left eigenvector with eigenvalue 1
        eigenvalues, eigenvectors = np.linalg.eig(self._transition_matrix.T)
        
        # Find eigenvector corresponding to eigenvalue 1
        idx = np.argmin(np.abs(eigenvalues - 1.0))
        stationary = np.real(eigenvectors[:, idx])
        
        # Normalize to sum to 1
        stationary = stationary / stationary.sum()
        
        return stationary


class SmoothRegimeModel(RegimeModel):
    """
    Regime model with smoothed transitions between states.
    
    Instead of abrupt regime changes, this model smoothly interpolates
    multipliers over a transition window, creating more realistic
    gradual shifts in market behavior.
    
    Attributes:
        transition_window: Number of periods for smooth transition.
    """
    
    def __init__(
        self,
        params: RegimeParams,
        transition_window: int = 30
    ) -> None:
        """
        Initialize smooth regime model.
        
        Args:
            params: Regime model parameters.
            transition_window: Periods for transition smoothing.
        """
        super().__init__(params)
        self._transition_window = transition_window
        self._transition_progress = 0
        self._previous_regime_idx: Optional[int] = None
    
    @property
    def transition_window(self) -> int:
        """Return transition window size."""
        return self._transition_window
    
    def reset(self) -> None:
        """Reset to initial state."""
        super().reset()
        self._transition_progress = 0
        self._previous_regime_idx = None
    
    def generate_smooth_multiplier_series(
        self,
        rng: RandomState,
        n_steps: int
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Generate smoothly transitioning multiplier series.
        
        Args:
            rng: Random state for reproducibility.
            n_steps: Number of time steps.
            
        Returns:
            Tuple of (regime_indices, smoothed_drift, smoothed_volatility).
        """
        regimes, raw_drift, raw_vol = self.generate_multiplier_series(rng, n_steps)
        
        # Find regime change points
        changes = np.where(np.diff(regimes) != 0)[0] + 1
        
        # Apply smoothing at each change point
        smoothed_drift = raw_drift.copy().astype(float)
        smoothed_vol = raw_vol.copy().astype(float)
        
        for change_idx in changes:
            # Smooth over transition window
            start = max(0, change_idx - self._transition_window // 2)
            end = min(n_steps, change_idx + self._transition_window // 2)
            
            if end - start < 2:
                continue
            
            # Create smooth transition weights
            window_size = end - start
            weights = np.linspace(0, 1, window_size)
            
            # Interpolate between before and after values
            before_drift = raw_drift[start]
            after_drift = raw_drift[end - 1] if end < n_steps else raw_drift[-1]
            smoothed_drift[start:end] = before_drift + weights * (after_drift - before_drift)
            
            before_vol = raw_vol[start]
            after_vol = raw_vol[end - 1] if end < n_steps else raw_vol[-1]
            smoothed_vol[start:end] = before_vol + weights * (after_vol - before_vol)
        
        return regimes, smoothed_drift, smoothed_vol

