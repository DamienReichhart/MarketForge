# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the MIT License. See the LICENSE file in the project
# root for full license information.

"""
Compiled per-minute recursions.

These are the only parts of the simulation that cannot be vectorised: each
step depends on the previous one. They are compiled with Numba and are all
*resumable*: they take the state left by the previous call and return the
state to pass to the next one, so a day-by-day simulation is bit-identical
to a single long run.
"""

from __future__ import annotations

import numpy as np
from numba import njit


@njit(cache=True, nogil=True)
def regime_chain(
    uniforms: np.ndarray,
    cumulative_transitions: np.ndarray,
    drift_targets: np.ndarray,
    vol_targets: np.ndarray,
    smoothing: float,
    regime: int,
    drift_mult: float,
    vol_mult: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, int, float, float]:
    """
    Advance the market regime Markov chain one step per uniform draw.

    The drift and volatility multipliers glide towards the current regime's
    targets with an exponential moving average (``smoothing`` in (0, 1]), so
    regime changes ramp in causally instead of jumping.

    Args:
        uniforms: (n,) draws in [0, 1) deciding each transition.
        cumulative_transitions: (K, K) row-wise cumulative transition matrix.
        drift_targets, vol_targets: (K,) multipliers per regime.
        smoothing: EMA weight of the new target at each step.
        regime, drift_mult, vol_mult: state after the previous step.

    Returns:
        (regimes, drift_mults, vol_mults, regime, drift_mult, vol_mult)
    """
    n = uniforms.shape[0]
    k = cumulative_transitions.shape[0]
    regimes = np.empty(n, dtype=np.int8)
    drifts = np.empty(n)
    vols = np.empty(n)
    for t in range(n):
        u = uniforms[t]
        nxt = k - 1
        for j in range(k):
            if u < cumulative_transitions[regime, j]:
                nxt = j
                break
        regime = nxt
        drift_mult += smoothing * (drift_targets[regime] - drift_mult)
        vol_mult += smoothing * (vol_targets[regime] - vol_mult)
        regimes[t] = regime
        drifts[t] = drift_mult
        vols[t] = vol_mult
    return regimes, drifts, vols, regime, drift_mult, vol_mult


@njit(cache=True, nogil=True)
def gjr_garch(
    shocks: np.ndarray,
    omega: float,
    alpha: float,
    beta: float,
    gamma: float,
    variance: np.ndarray,
    last_shock: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Unit-level GJR-GARCH(1,1) variance filter, one column per series.

        h_t = omega + (alpha + gamma * 1[e_{t-1} < 0]) * e_{t-1}^2 + beta * h_{t-1}
        e_t = sqrt(h_t) * z_t

    With ``omega = 1 - (alpha + beta + gamma/2)`` the unconditional variance
    is 1, so ``sqrt(h_t)`` is a dimensionless volatility multiplier.

    Args:
        shocks: (n, F) unit-variance shocks z_t.
        variance: (F,) h_{t-1} before the first row.
        last_shock: (F,) e_{t-1} before the first row.

    Returns:
        (h, variance, last_shock) where h is (n, F) and the others are the
        state after the last row.
    """
    n, f = shocks.shape
    h = np.empty((n, f))
    variance = variance.copy()
    last_shock = last_shock.copy()
    for t in range(n):
        for i in range(f):
            e = last_shock[i]
            lev = gamma if e < 0.0 else 0.0
            v = omega + (alpha + lev) * e * e + beta * variance[i]
            h[t, i] = v
            variance[i] = v
            last_shock[i] = np.sqrt(v) * shocks[t, i]
    return h, variance, last_shock


@njit(cache=True, nogil=True)
def ar1(drivers: np.ndarray, phi: float, state: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """
    Column-wise AR(1): y_t = phi * y_{t-1} + u_t.

    Args:
        drivers: (n, I) innovations u_t.
        state: (I,) y_{t-1} before the first row.

    Returns:
        (y, state) with y of shape (n, I).
    """
    n, m = drivers.shape
    y = np.empty((n, m))
    state = state.copy()
    for t in range(n):
        for i in range(m):
            v = phi * state[i] + drivers[t, i]
            y[t, i] = v
            state[i] = v
    return y, state


def bridge_extremes(
    log_body: np.ndarray,
    bar_std: np.ndarray,
    u_high: np.ndarray,
    u_low: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Exact maximum and minimum of a Brownian bridge, sampled by inversion.

    For a Brownian path over one bar with standard deviation ``s`` that ends
    at ``b`` (the log close/open), the running maximum M satisfies
    ``P(M > m) = exp(-2 m (m - b) / s^2)`` for ``m >= max(0, b)``; the minimum
    is symmetric. Inverting with a uniform draw gives the continuous-path
    extreme with two numbers per bar instead of a discretised path.

    Args:
        log_body: log(close / open) per bar.
        bar_std: per-bar standard deviation of the log price.
        u_high, u_low: uniforms in (0, 1].

    Returns:
        (log_high, log_low) relative to the log open.
    """
    s2 = bar_std * bar_std
    b2 = log_body * log_body
    high = 0.5 * (log_body + np.sqrt(b2 - 2.0 * s2 * np.log(u_high)))
    low = 0.5 * (log_body - np.sqrt(b2 - 2.0 * s2 * np.log(u_low)))
    return high, low
