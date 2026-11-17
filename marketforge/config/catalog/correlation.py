# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

"""
Valid correlation matrices from stated relationships.

The catalogs state the correlations that matter (BTC-ETH 0.88, EURUSD-USDCHF
-0.92, ...) and fill the other pairs with a market-wide default. Taken
together the stated values are not a valid correlation matrix: no set of
returns has them all. :func:`fit_correlation` finds the valid matrix whose
*implied* correlations come closest to them, weighting each pair by how
much it was meant (stated pairs fully, defaults a little), instead of
clipping eigenvalues, which moved stated pairs by up to 0.6 and kept the
defaults.

For forex the fitted matrix is the anchors' (ADR 0002). Each instrument is a
signed sum of anchors, so its correlations with every other instrument, and
its volatility, follow from the anchors' matrix and volatilities: the fit
scores those implied values, crosses included, and also the crosses' stated
volatilities.

The fit runs offline (``python scripts/fit_correlations.py``) and its result
ships with the package, so loading the catalog needs no optimiser and gives
the same matrix on every platform.
"""

from __future__ import annotations

import numpy as np

# Weight of a pair the catalog states, and of one it fills with the default.
STATED_WEIGHT = 1.0
DEFAULT_WEIGHT = 0.05
# Forex: a pair that involves a cross is a derived quantity, and the
# hand-written values contradict the anchors they derive from (USDCHF-EURCHF
# is stated -0.78 but EURCHF = EURUSD * USDCHF makes it positive), so they
# count for less than the anchors' own relationships and the crosses'
# volatilities, which are measured directly. Defaults involving a cross mean
# nothing and count for nothing.
DERIVED_STATED_WEIGHT = 0.1
DERIVED_DEFAULT_WEIGHT = 0.0
# Added to the identity (then renormalised) so the result is positive definite
# with some margin: the simulator takes its Cholesky factor.
RIDGE = 1e-4


def implied_correlation(
    factor_correlation: np.ndarray, loadings: np.ndarray, scales: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Instrument correlations and volatilities implied by the factors'.

    ``loadings`` is (instruments, factors): instrument log price = loadings @
    factor log prices; ``scales`` are the factors' volatilities.
    """
    m = loadings * scales[None, :]
    cov = m @ factor_correlation @ m.T
    vol = np.sqrt(np.diag(cov))
    corr = cov / np.outer(vol, vol)
    corr = (corr + corr.T) / 2
    np.fill_diagonal(corr, 1.0)
    return corr, vol


def _normalised(a: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    g = a @ a.T
    d = np.diag(g).copy()
    q = np.sqrt(np.outer(d, d))
    return g / q, d, q


def objective(
    a: np.ndarray,
    target: np.ndarray,
    weight: np.ndarray,
    m: np.ndarray,
    vol_target: np.ndarray,
    vol_weight: np.ndarray,
) -> tuple[float, np.ndarray]:
    """Weighted squared error of the implied correlations and volatilities, and its gradient in ``a``.

    The factor correlation is ``a @ a.T`` with unit diagonal, so every ``a``
    gives a valid matrix.
    """
    c, d, qg = _normalised(a)
    sigma = m @ c @ m.T
    s = np.diag(sigma).copy()
    q = np.sqrt(np.outer(s, s))
    r = sigma / q
    e = weight * (r - target)
    vol = np.sqrt(s)
    ratio = vol / vol_target
    loss = float(np.sum(e * (r - target)) + np.sum(vol_weight * (ratio - 1.0) ** 2))

    e2 = 2.0 * e
    d_sigma = e2 / q
    d_s = -np.sum(e2 * r, axis=1) / s + 2.0 * vol_weight * (ratio - 1.0) * ratio / (2.0 * s)
    d_sigma[np.diag_indices_from(d_sigma)] += d_s
    d_c = m.T @ d_sigma @ m
    d_g = d_c / qg
    d_g[np.diag_indices_from(d_g)] -= np.sum(d_c * c, axis=1) / d
    grad = (d_g + d_g.T) @ a
    return loss, grad


def fit_correlation(
    target: np.ndarray,
    weight: np.ndarray,
    *,
    loadings: np.ndarray | None = None,
    scales: np.ndarray | None = None,
    vol_target: np.ndarray | None = None,
    vol_weight: np.ndarray | None = None,
    start: np.ndarray | None = None,
) -> np.ndarray:
    """The valid factor correlation matrix that best explains ``target``.

    Without ``loadings`` the factors are the instruments themselves. The
    diagonal of ``weight`` is ignored.
    """
    from scipy.optimize import minimize  # offline only: not needed to load the catalog

    n = target.shape[0]
    loadings = np.eye(n) if loadings is None else np.asarray(loadings, dtype=float)
    k = loadings.shape[1]
    scales = np.ones(k) if scales is None else np.asarray(scales, dtype=float)
    vol_target = np.ones(n) if vol_target is None else np.asarray(vol_target, dtype=float)
    vol_weight = np.zeros(n) if vol_weight is None else np.asarray(vol_weight, dtype=float)
    weight = np.array(weight, dtype=float)
    np.fill_diagonal(weight, 0.0)
    m = loadings * scales[None, :]

    if start is None:
        start = np.eye(k) if loadings.shape != (n, n) else clipped(target)
    a0 = np.linalg.cholesky(clipped(start, 1e-3))

    def f(flat: np.ndarray) -> tuple[float, np.ndarray]:
        loss, grad = objective(flat.reshape(k, k), target, weight, m, vol_target, vol_weight)
        return loss, grad.ravel()

    result = minimize(
        f, a0.ravel(), jac=True, method="L-BFGS-B", options={"maxiter": 20_000, "gtol": 1e-9}
    )
    c, _, _ = _normalised(result.x.reshape(k, k))
    c = (1.0 - RIDGE) * c + RIDGE * np.eye(k)
    c = (c + c.T) / 2
    np.fill_diagonal(c, 1.0)
    return c


def clipped(matrix: np.ndarray, epsilon: float = 1e-6) -> np.ndarray:
    """``matrix`` with eigenvalues clipped to ``epsilon`` and its diagonal renormalised to 1."""
    eigenvalues, eigenvectors = np.linalg.eigh(matrix)
    adjusted = eigenvectors @ np.diag(np.maximum(eigenvalues, epsilon)) @ eigenvectors.T
    d = np.sqrt(np.diag(adjusted))
    adjusted = adjusted / np.outer(d, d)
    adjusted = (adjusted + adjusted.T) / 2
    np.fill_diagonal(adjusted, 1.0)
    return np.asarray(adjusted)


# Kept for the override loader, which repairs a user's edits of a valid matrix.
ensure_positive_semidefinite = clipped
