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
Correlation engine for generating correlated multi-asset returns.

Uses Cholesky decomposition to transform independent random variables
into correlated random variables while maintaining the desired correlation
structure.
"""

from __future__ import annotations

from typing import Optional
import numpy as np
from scipy.linalg import cholesky

from marketforge.utils.random import RandomState


class CorrelationEngine:
    """
    Engine for generating correlated random variables using Cholesky decomposition.
    
    The correlation engine transforms independent standard normal random variables
    into correlated random variables that follow a specified correlation matrix.
    This is essential for realistic multi-asset simulation where assets typically
    exhibit non-zero correlations.
    
    Mathematical Background:
        If Z ~ N(0, I) is a vector of independent standard normals, and
        L is the Cholesky decomposition of correlation matrix Σ (so LLᵀ = Σ),
        then Y = LZ has covariance matrix Σ.
    
    Attributes:
        n_assets: Number of assets in the correlation structure.
        correlation_matrix: The target correlation matrix.
        cholesky_matrix: Lower triangular Cholesky factor.
    
    Example:
        >>> corr_matrix = np.array([[1.0, 0.8], [0.8, 1.0]])
        >>> engine = CorrelationEngine(corr_matrix)
        >>> rng = RandomState(42)
        >>> correlated = engine.generate_correlated_normals(rng, 1000)
        >>> np.corrcoef(correlated.T)  # Should be close to corr_matrix
    """
    
    def __init__(self, correlation_matrix: np.ndarray) -> None:
        """
        Initialize the correlation engine with a correlation matrix.
        
        Args:
            correlation_matrix: Square symmetric positive semi-definite matrix
                              with ones on the diagonal.
        
        Raises:
            ValueError: If matrix is not valid (not square, not symmetric,
                       not positive semi-definite, or diagonal not ones).
        """
        self._validate_correlation_matrix(correlation_matrix)
        self._correlation_matrix = correlation_matrix.copy()
        self._n_assets = correlation_matrix.shape[0]
        
        # Compute Cholesky decomposition
        # Add small regularization for numerical stability
        regularized = self._correlation_matrix + np.eye(self._n_assets) * 1e-10
        self._cholesky_matrix = cholesky(regularized, lower=True)
    
    @property
    def n_assets(self) -> int:
        """Return number of assets."""
        return self._n_assets
    
    @property
    def correlation_matrix(self) -> np.ndarray:
        """Return a copy of the correlation matrix."""
        return self._correlation_matrix.copy()
    
    @property
    def cholesky_matrix(self) -> np.ndarray:
        """Return a copy of the Cholesky factor."""
        return self._cholesky_matrix.copy()
    
    def _validate_correlation_matrix(self, matrix: np.ndarray) -> None:
        """
        Validate that the matrix is a valid correlation matrix.
        
        Args:
            matrix: Matrix to validate.
            
        Raises:
            ValueError: If validation fails.
        """
        if matrix.ndim != 2:
            raise ValueError(f"Matrix must be 2D, got {matrix.ndim}D")
        
        n, m = matrix.shape
        if n != m:
            raise ValueError(f"Matrix must be square, got shape {matrix.shape}")
        
        if n == 0:
            raise ValueError("Matrix cannot be empty")
        
        # Check symmetry
        if not np.allclose(matrix, matrix.T, atol=1e-10):
            raise ValueError("Correlation matrix must be symmetric")
        
        # Check diagonal is ones
        if not np.allclose(np.diag(matrix), 1.0, atol=1e-10):
            raise ValueError("Diagonal elements must be 1.0")
        
        # Check values in [-1, 1]
        if np.any(matrix < -1.0 - 1e-10) or np.any(matrix > 1.0 + 1e-10):
            raise ValueError("Correlation values must be in [-1, 1]")
        
        # Check positive semi-definite
        eigenvalues = np.linalg.eigvalsh(matrix)
        if np.any(eigenvalues < -1e-8):
            raise ValueError(
                f"Correlation matrix must be positive semi-definite. "
                f"Min eigenvalue: {eigenvalues.min()}"
            )
    
    def generate_correlated_normals(
        self,
        rng: RandomState,
        n_samples: int
    ) -> np.ndarray:
        """
        Generate correlated standard normal samples.
        
        Args:
            rng: Random state for reproducibility.
            n_samples: Number of samples to generate.
            
        Returns:
            Array of shape (n_samples, n_assets) with correlated normals.
        """
        # Generate independent standard normals
        independent = rng.standard_normal((n_samples, self._n_assets))
        
        # Transform to correlated using Cholesky factor
        # Y = Z @ Lᵀ is equivalent to Y = (L @ Zᵀ)ᵀ
        correlated = independent @ self._cholesky_matrix.T
        
        return correlated
    
    def transform_independent_to_correlated(
        self,
        independent: np.ndarray
    ) -> np.ndarray:
        """
        Transform independent samples to correlated samples.
        
        Useful when you want to apply correlation to pre-generated
        random samples.
        
        Args:
            independent: Array of shape (n_samples, n_assets) with
                        independent standard normal samples.
                        
        Returns:
            Array of same shape with correlated samples.
        """
        if independent.shape[1] != self._n_assets:
            raise ValueError(
                f"Expected {self._n_assets} assets, got {independent.shape[1]}"
            )
        
        return independent @ self._cholesky_matrix.T
    
    def get_conditional_parameters(
        self,
        known_values: dict[int, float]
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        Get conditional mean and covariance given known asset values.
        
        Useful for conditional simulation where some assets are fixed.
        
        Args:
            known_values: Dict mapping asset index to its known value.
            
        Returns:
            Tuple of (conditional_mean, conditional_covariance) for
            the unknown assets.
        """
        if not known_values:
            return np.zeros(self._n_assets), self._correlation_matrix.copy()
        
        known_idx = sorted(known_values.keys())
        unknown_idx = [i for i in range(self._n_assets) if i not in known_idx]
        
        if not unknown_idx:
            return np.array([]), np.array([[]])
        
        # Partition the correlation matrix
        sigma_uu = self._correlation_matrix[np.ix_(unknown_idx, unknown_idx)]
        sigma_uk = self._correlation_matrix[np.ix_(unknown_idx, known_idx)]
        sigma_kk = self._correlation_matrix[np.ix_(known_idx, known_idx)]
        
        # Known values vector
        x_k = np.array([known_values[i] for i in known_idx])
        
        # Conditional mean: μ_u|k = Σ_uk @ Σ_kk⁻¹ @ x_k
        sigma_kk_inv = np.linalg.inv(sigma_kk)
        conditional_mean = sigma_uk @ sigma_kk_inv @ x_k
        
        # Conditional covariance: Σ_u|k = Σ_uu - Σ_uk @ Σ_kk⁻¹ @ Σ_ku
        conditional_cov = sigma_uu - sigma_uk @ sigma_kk_inv @ sigma_uk.T
        
        return conditional_mean, conditional_cov


def build_correlation_matrix_from_upper_triangle(
    n_assets: int,
    upper_triangle_values: list[float]
) -> np.ndarray:
    """
    Build a full correlation matrix from upper triangle values.
    
    For n assets, the upper triangle (excluding diagonal) has
    n*(n-1)/2 elements, ordered as:
    (0,1), (0,2), ..., (0,n-1), (1,2), (1,3), ..., (n-2,n-1)
    
    Args:
        n_assets: Number of assets.
        upper_triangle_values: List of correlation values for upper triangle.
        
    Returns:
        Full symmetric correlation matrix.
        
    Raises:
        ValueError: If wrong number of values provided.
        
    Example:
        >>> # For 3 assets: values are [corr(0,1), corr(0,2), corr(1,2)]
        >>> build_correlation_matrix_from_upper_triangle(3, [0.8, 0.6, 0.7])
        array([[1. , 0.8, 0.6],
               [0.8, 1. , 0.7],
               [0.6, 0.7, 1. ]])
    """
    expected_count = n_assets * (n_assets - 1) // 2
    if len(upper_triangle_values) != expected_count:
        raise ValueError(
            f"Expected {expected_count} correlation values for {n_assets} assets, "
            f"got {len(upper_triangle_values)}"
        )
    
    # Initialize with identity
    matrix = np.eye(n_assets)
    
    # Fill upper triangle
    idx = 0
    for i in range(n_assets):
        for j in range(i + 1, n_assets):
            matrix[i, j] = upper_triangle_values[idx]
            matrix[j, i] = upper_triangle_values[idx]  # Symmetric
            idx += 1
    
    return matrix


def create_correlation_engine(
    correlation_values: Optional[list[float]] = None,
    n_assets: int = 1,
    uniform_correlation: Optional[float] = None
) -> CorrelationEngine:
    """
    Factory function to create a CorrelationEngine.
    
    Args:
        correlation_values: Upper triangle correlation values.
        n_assets: Number of assets (used if correlation_values is None).
        uniform_correlation: If provided, use this value for all pairs.
        
    Returns:
        Configured CorrelationEngine instance.
    """
    if correlation_values is not None:
        # Infer n_assets from number of values
        # n*(n-1)/2 = len(values) => n = (1 + sqrt(1 + 8*len)) / 2
        n = int((1 + np.sqrt(1 + 8 * len(correlation_values))) / 2)
        matrix = build_correlation_matrix_from_upper_triangle(n, correlation_values)
    elif uniform_correlation is not None:
        matrix = np.full((n_assets, n_assets), uniform_correlation)
        np.fill_diagonal(matrix, 1.0)
    else:
        matrix = np.eye(n_assets)
    
    return CorrelationEngine(matrix)

