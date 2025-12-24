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
Base configuration structures for market assets.

Defines the core dataclasses used across all market configurations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import numpy as np


class MarketType(str, Enum):
    """Supported market types."""
    FOREX = "forex"
    CRYPTO = "crypto"
    STOCKS = "stocks"


@dataclass
class AssetParams:
    """
    Parameters for a single asset.
    
    Attributes:
        symbol: Asset symbol (e.g., 'EURUSD', 'BTCUSD', 'AAPL').
        start_price: Initial price for the asset.
        volatility: Annualized volatility (e.g., 0.02 for 2%).
        drift: Annualized drift/trend (e.g., 0.0001).
        volume_base: Base volume level for the asset.
        volume_volatility: Volatility of volume (log-normal sigma).
        category: Optional category for grouping (e.g., 'major', 'tech').
    """
    symbol: str
    start_price: float
    volatility: float
    drift: float = 0.0
    volume_base: float = 1000.0
    volume_volatility: float = 0.5
    category: Optional[str] = None
    
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
    
    def get_correlation_submatrix(self, symbols: list[str]) -> np.ndarray:
        """
        Get correlation submatrix for a subset of assets.
        
        Args:
            symbols: List of symbols to include.
            
        Returns:
            Correlation submatrix for the specified symbols.
        """
        indices = [self.asset_order.index(s) for s in symbols]
        return self.correlation_matrix[np.ix_(indices, indices)]
    
    def get_assets_by_category(self, category: str) -> list[AssetParams]:
        """Get all assets in a category."""
        return [a for a in self.assets.values() if a.category == category]


def build_correlation_matrix(
    n_assets: int,
    correlations: dict[tuple[int, int], float],
    default_correlation: float = 0.3
) -> np.ndarray:
    """
    Build a correlation matrix from sparse correlation definitions.
    
    Args:
        n_assets: Number of assets.
        correlations: Dict mapping (i, j) pairs to correlation values.
        default_correlation: Default correlation for unspecified pairs.
        
    Returns:
        Full symmetric correlation matrix.
    """
    matrix = np.full((n_assets, n_assets), default_correlation)
    np.fill_diagonal(matrix, 1.0)
    
    for (i, j), corr in correlations.items():
        matrix[i, j] = corr
        matrix[j, i] = corr
    
    return matrix


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
    
    return adjusted

