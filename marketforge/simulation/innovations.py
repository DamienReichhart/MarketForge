# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

"""
Correlated, unit-variance shocks.

Multivariate Student-t via a normal-variance mixture:

    Y = Z @ L^T             correlated normals (L = Cholesky factor)
    W = chi2(nu) / nu       ONE mixing variable per minute, shared by all series
    z = Y / sqrt(W) * sqrt((nu - 2) / nu)

Sharing W across series gives tail dependence: extreme minutes hit every
instrument of a market together, as in real sell-offs. With ``nu=None`` the
shocks are Gaussian.
"""

from __future__ import annotations

import numpy as np


def correlated_shocks(
    normals: np.ndarray,
    chi2: np.ndarray,
    cholesky_lower: np.ndarray,
    nu: float | None,
) -> np.ndarray:
    """
    Turn independent draws into correlated unit-variance shocks.

    Args:
        normals: (n, F) independent standard normals.
        chi2: (n,) chi-square(nu) draws (ignored when ``nu`` is None).
        cholesky_lower: (F, F) lower Cholesky factor of the correlation matrix.
        nu: Student-t degrees of freedom (> 2), or None for Gaussian shocks.

    Returns:
        (n, F) shocks with unit variance and the requested correlation.
    """
    y = normals @ cholesky_lower.T
    if nu is None:
        return np.asarray(y)
    if nu <= 2.0:
        raise ValueError(f"nu must be > 2 for finite variance, got {nu}")
    return np.asarray(y / np.sqrt(chi2 / nu)[:, None] * np.sqrt((nu - 2.0) / nu))


def stressed_shocks(
    shocks: np.ndarray,
    stress: np.ndarray,
    scale: np.ndarray,
    common: np.ndarray,
    loading: np.ndarray,
) -> np.ndarray:
    """Add a common factor to every shock, by a share ``stress`` (per row).

        z'_i = sqrt(1 - s b_i^2) z_i + sqrt(s) b_i * scale * m

    keeps unit variance and gives correlations
    sqrt((1 - s b_i^2)(1 - s b_j^2)) C_ij + s b_i b_j: with loadings ``b`` near
    +-1, pairs that move together move together more, and pairs that move
    apart move apart more. ``scale`` is each row's Student-t mixing factor, so
    the common part shares the tails of the shocks it joins.

    Args:
        shocks: (n, F) correlated unit-variance shocks.
        stress: (n,) share in [0, 1).
        scale: (n,) mixing factor of each row (1 for Gaussian shocks).
        common: (n,) standard normals of the common factor.
        loading: (F,) loadings on the common factor, |b| < 1.
    """
    if not np.any(stress):
        return shocks
    keep = np.sqrt(1.0 - stress[:, None] * loading[None, :] ** 2)
    added = (np.sqrt(stress) * scale * common)[:, None] * loading[None, :]
    return np.asarray(keep * shocks + added)
