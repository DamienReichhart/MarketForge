# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

"""Regime multipliers calibrated to reshape drift and volatility without changing their level."""

from __future__ import annotations

from collections.abc import Sequence
from functools import lru_cache

import numpy as np

from marketforge.config.factors import split_pair
from marketforge.config.model_params import RegimeParams
from marketforge.simulation.kernels import regime_chain

# EMA weight per minute for regime multipliers (~15-minute ramp).
REGIME_SMOOTHING = 1.0 / 15.0


def spell_trends(params: RegimeParams) -> np.ndarray:
    """Per-minute trend of each regime, in units of a factor's per-minute volatility.

    A spell of regime r lasts D_r = minutes_per_step / (1 - P_rr) open minutes
    on average, with volatility v_r * sqrt(D_r) (v_r normalised to a mean
    square of 1 over the stationary distribution). A trend of strength k_r over
    the spell is a per-minute drift of k_r * v_r / sqrt(D_r).
    """
    p = np.asarray(params.transition_matrix, dtype=float)
    stay = np.clip(np.diag(p), 0.0, 1.0 - 1e-12)
    durations = params.minutes_per_step / (1.0 - stay)
    eigenvalues, eigenvectors = np.linalg.eig(p.T)
    stationary = np.real(eigenvectors[:, np.argmin(np.abs(eigenvalues - 1.0))])
    stationary = stationary / stationary.sum()
    vol = np.asarray(params.volatility_multipliers, dtype=float)
    vol = vol / np.sqrt(float(stationary @ vol**2))
    return np.asarray(params.trend_strength, dtype=float) * vol / np.sqrt(durations)


def main_factor_loadings(
    correlation: np.ndarray, portfolio: np.ndarray | None = None
) -> np.ndarray:
    """Each series' correlation with the market's main factor.

    The factor is ``portfolio`` (weights on the series) when given, else the
    first principal component. It is signed so the market's lead series (its
    first: BTCUSD, EURUSD, AAPL) loads positively, so ``trend_up`` means it
    rises.
    """
    if portfolio is None:
        eigenvalues, eigenvectors = np.linalg.eigh(correlation)
        loadings = eigenvectors[:, -1] * np.sqrt(max(float(eigenvalues[-1]), 0.0))
    else:
        w = np.asarray(portfolio, dtype=float)
        loadings = correlation @ w / np.sqrt(float(w @ correlation @ w))
    return loadings if loadings[0] >= 0 else -loadings


def dollar_portfolio(anchors: Sequence[str]) -> np.ndarray:
    """Weights of an equal-weight dollar index on forex anchors: +1 for USDxxx, -1 for xxxUSD."""
    weights = []
    for symbol in anchors:
        base, quote = split_pair(symbol)
        weights.append(1.0 if base == "USD" else -1.0 if quote == "USD" else 0.0)
    return np.array(weights)


def normalised_regime_targets(
    cumulative: np.ndarray, drift: np.ndarray, vol: np.ndarray, initial: int
) -> tuple[np.ndarray, np.ndarray]:
    """
    Rescale regime targets so that, over the long run (smoothing included), the
    mean trend is 0 and the mean squared volatility multiplier is 1. Without
    this the configured annual drift and volatility were not what the
    simulation produced (e.g. stocks drifted down on average).

    The calibration runs a multi-million-step chain (~0.15 s and up to ~200 MB
    of temporaries), so its result is cached per distinct set of parameters.
    """
    key = (
        cumulative.shape,
        np.ascontiguousarray(cumulative, dtype=float).tobytes(),
        np.ascontiguousarray(drift, dtype=float).tobytes(),
        np.ascontiguousarray(vol, dtype=float).tobytes(),
        int(initial),
    )
    d, v = _cached_regime_targets(key)
    return d.copy(), v.copy()


@lru_cache(maxsize=32)
def _cached_regime_targets(
    key: tuple[tuple[int, ...], bytes, bytes, bytes, int],
) -> tuple[np.ndarray, np.ndarray]:
    shape, cum_bytes, drift_bytes, vol_bytes, initial = key
    cumulative = np.frombuffer(cum_bytes).reshape(shape).copy()
    drift = np.frombuffer(drift_bytes).copy()
    vol = np.frombuffer(vol_bytes).copy()
    # Simulate long enough to visit every regime many times (>= ~2000 mean
    # durations of the stickiest one), with a fixed seed: deterministic.
    stay = np.diff(
        np.concatenate([np.zeros((cumulative.shape[0], 1)), cumulative], axis=1), axis=1
    ).diagonal()
    longest = float(np.max(1.0 / np.maximum(1.0 - stay, 1e-9)))
    n = int(min(20_000_000, max(400_000, 2000 * longest)))
    u = np.random.Generator(np.random.PCG64(20260613)).random(n)
    _, d, v, *_ = regime_chain(
        u,
        cumulative,
        drift,
        vol,
        REGIME_SMOOTHING,
        initial,
        float(drift[initial]),
        float(vol[initial]),
    )
    burn = min(n // 10, int(20 * longest))
    vol_scale = 1.0 / np.sqrt(np.mean(v[burn:] ** 2))
    drift_shift = -float(np.mean(d[burn:]))
    targets = (drift + drift_shift, vol * vol_scale)
    for a in targets:
        a.setflags(write=False)  # shared by every simulator: never mutated
    return targets
