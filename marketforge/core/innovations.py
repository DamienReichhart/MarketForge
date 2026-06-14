# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the MIT License. See the LICENSE file in the project
# root for full license information.

"""
Pluggable innovation generators for correlated return shocks.

Provides the standardized (unit-variance) correlated innovations z_t that drive
the GARCH/return recursion. Two implementations:

- GaussianInnovations: classic multivariate normal (thin tails).
- StudentTInnovations: multivariate Student-t via a normal-variance mixture,
  giving heavy tails AND tail dependence (assets get extreme draws together).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import numpy as np

from marketforge.utils.random import RandomState


class InnovationGenerator(ABC):
    """Abstract base for correlated, unit-variance innovation generators."""

    @abstractmethod
    def generate(
        self,
        rng: RandomState,
        n_steps: int,
        n_assets: int,
        cholesky_lower: np.ndarray,
    ) -> np.ndarray:
        """
        Generate correlated innovations of shape (n_steps, n_assets).

        The result has (approximately) unit marginal variance per asset and a
        correlation matrix equal to ``cholesky_lower @ cholesky_lower.T``.
        """
        ...


class GaussianInnovations(InnovationGenerator):
    """Multivariate standard-normal innovations (thin tails)."""

    def generate(
        self,
        rng: RandomState,
        n_steps: int,
        n_assets: int,
        cholesky_lower: np.ndarray,
    ) -> np.ndarray:
        z = rng.standard_normal((n_steps, n_assets))
        return np.asarray(z @ cholesky_lower.T)


class StudentTInnovations(InnovationGenerator):
    """
    Multivariate Student-t innovations via normal-variance mixture.

    Construction:
        Y = Z @ Lᵀ              correlated normals
        W = chi2(nu) / nu       shared mixing variable per time step
        T = Y / sqrt(W)         multivariate-t (E[T Tᵀ] = nu/(nu-2) · Σ)
        z = T * sqrt((nu-2)/nu) standardized to unit variance

    A single shared W per row yields joint tail dependence (simultaneous
    extreme moves across assets), a documented feature of real markets.
    """

    def __init__(self, nu: float) -> None:
        if nu <= 2.0:
            raise ValueError(f"nu must be > 2 for finite variance, got {nu}")
        self._nu = float(nu)

    @property
    def nu(self) -> float:
        return self._nu

    def generate(
        self,
        rng: RandomState,
        n_steps: int,
        n_assets: int,
        cholesky_lower: np.ndarray,
    ) -> np.ndarray:
        z = rng.standard_normal((n_steps, n_assets))
        correlated = z @ cholesky_lower.T
        mixing = rng.chisquare(self._nu, size=n_steps) / self._nu  # (n_steps,)
        t = correlated / np.sqrt(mixing)[:, None]
        return np.asarray(t * np.sqrt((self._nu - 2.0) / self._nu))
