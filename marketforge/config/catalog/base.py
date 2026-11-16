# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the MIT License. See the LICENSE file in the project
# root for full license information.

"""
Base configuration structures for market assets.

Defines the core dataclasses used across all market configurations.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from marketforge.config.settings import MarketType


@dataclass
class AssetParams:
    """
    Parameters for a single instrument.

    Attributes:
        symbol: Instrument symbol (e.g., 'EURUSD', 'BTCUSD', 'AAPL').
        start_price: Initial price.
        volatility: Annualized volatility (e.g., 0.25 for 25%).
        drift: Annualized log drift (e.g., 0.08).
        volume_base: Mean volume per open minute, in the market's unit:
            base-asset units (crypto), ticks (forex), shares (stocks).
        volume_volatility: Lognormal sigma of the volume noise.
        category: Optional category for grouping (e.g., 'major', 'tech').
    """

    symbol: str
    start_price: float
    volatility: float
    drift: float = 0.0
    volume_base: float = 1000.0
    volume_volatility: float = 0.5
    category: str | None = None

    def __post_init__(self) -> None:
        """Validate asset parameters."""
        if self.start_price <= 0:
            raise ValueError(f"start_price must be positive, got {self.start_price}")
        if self.volatility <= 0:
            raise ValueError(f"volatility must be positive, got {self.volatility}")
        if self.volume_base <= 0:
            raise ValueError(f"volume_base must be positive, got {self.volume_base}")


@dataclass
class MarketConfig:
    """
    Complete configuration for a market.

    Contains all assets and their correlation matrix for a specific market type.

    Attributes:
        market_type: Type of market (forex, crypto, stocks).
        assets: Dictionary mapping symbol to AssetParams.
        correlation_matrix: Full correlation matrix for all assets.
        asset_order: List of symbols defining matrix row/column order.
    """

    market_type: MarketType
    assets: dict[str, AssetParams]
    correlation_matrix: np.ndarray
    asset_order: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Validate market configuration."""
        if not self.asset_order:
            self.asset_order = list(self.assets.keys())

        n_assets = len(self.assets)

        if self.correlation_matrix.shape != (n_assets, n_assets):
            raise ValueError(
                f"Correlation matrix shape {self.correlation_matrix.shape} "
                f"doesn't match number of assets ({n_assets})"
            )

        # Verify matrix is symmetric
        if not np.allclose(self.correlation_matrix, self.correlation_matrix.T, atol=1e-10):
            raise ValueError("Correlation matrix must be symmetric")

        # Verify diagonal is ones
        if not np.allclose(np.diag(self.correlation_matrix), 1.0, atol=1e-10):
            raise ValueError("Correlation matrix diagonal must be 1.0")

    @property
    def n_assets(self) -> int:
        """Return number of assets."""
        return len(self.assets)

    @property
    def symbols(self) -> list[str]:
        """Return list of asset symbols in order."""
        return self.asset_order

    def get_asset(self, symbol: str) -> AssetParams:
        """Get asset parameters by symbol."""
        return self.assets[symbol]


def ensure_positive_semidefinite(matrix: np.ndarray, epsilon: float = 1e-6) -> np.ndarray:
    """
    Ensure a correlation matrix is positive semi-definite.

    Uses eigenvalue adjustment method.

    Args:
        matrix: Input correlation matrix.
        epsilon: Minimum eigenvalue threshold.

    Returns:
        Adjusted positive semi-definite correlation matrix.
    """
    # Compute eigendecomposition
    eigenvalues, eigenvectors = np.linalg.eigh(matrix)

    # Adjust negative eigenvalues
    eigenvalues = np.maximum(eigenvalues, epsilon)

    # Reconstruct matrix
    adjusted = eigenvectors @ np.diag(eigenvalues) @ eigenvectors.T

    # Normalize to ensure diagonal is 1
    d = np.sqrt(np.diag(adjusted))
    adjusted = adjusted / np.outer(d, d)

    # Ensure perfect symmetry
    adjusted = (adjusted + adjusted.T) / 2
    np.fill_diagonal(adjusted, 1.0)
    return np.asarray(adjusted)
