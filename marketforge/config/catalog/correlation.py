# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the MIT License. See the LICENSE file in the project
# root for full license information.

"""Correlation-matrix repair shared by the catalogs and the override loader."""

from __future__ import annotations

import numpy as np


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
