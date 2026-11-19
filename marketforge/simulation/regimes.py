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

from marketforge.config.catalog.forex.risk import RISK_LOADINGS
from marketforge.config.factors import split_pair
from marketforge.config.model_params import RegimeParams
from marketforge.simulation.kernels import regime_spells
from marketforge.simulation.macro import CALM_DAYS, STRESSED_DAYS

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
    return np.asarray(np.asarray(params.trend_strength, dtype=float) * vol / np.sqrt(durations))


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
    return np.asarray(loadings if loadings[0] >= 0 else -loadings)


def dollar_portfolio(anchors: Sequence[str]) -> np.ndarray:
    """Weights of an equal-weight dollar index on forex anchors: +1 for USDxxx, -1 for xxxUSD."""
    weights = []
    for symbol in anchors:
        base, quote = split_pair(symbol)
        weights.append(1.0 if base == "USD" else -1.0 if quote == "USD" else 0.0)
    return np.array(weights)


def forex_risk_direction(anchors: Sequence[str]) -> np.ndarray:
    """Each forex anchor's loading on global risk: its base code's minus its quote code's."""
    loads = []
    for symbol in anchors:
        base, quote = split_pair(symbol)
        loads.append(RISK_LOADINGS.get(base, 0.0) - RISK_LOADINGS.get(quote, 0.0))
    return np.array(loads)


def normalised_spell_targets(
    params: RegimeParams, open_minutes_per_day: int
) -> tuple[np.ndarray, np.ndarray]:
    """
    Regime targets rescaled so that, over the long run (smoothing and the macro
    state included), the mean trend is 0 and the mean squared volatility
    multiplier is 1. Without this the configured annual drift and volatility
    were not what the simulation produced (e.g. stocks drifted down on average).

    The chain is run for millions of minutes with a fixed seed and a macro path
    of the same statistics, so its result is cached per set of parameters.
    """
    d, v = _cached_spell_targets(params, int(open_minutes_per_day))
    return d.copy(), v.copy()


@lru_cache(maxsize=32)
def _cached_spell_targets(params: RegimeParams, per_day: int) -> tuple[np.ndarray, np.ndarray]:
    drift = spell_trends(params)
    vol = np.asarray(params.volatility_multipliers, dtype=float)
    mean = np.asarray(params.mean_minutes())
    initial = params.get_regime_index(params.initial_regime)
    # Visit every regime many times: >= ~2000 spells of the longest.
    n = int(min(20_000_000, max(400_000, 2000 * float(mean.max()))))
    rng = np.random.Generator(np.random.PCG64(20260613))
    u = rng.random(n)
    lengths = rng.gamma(params.spell_shape, 1.0 / params.spell_shape, n)
    stressed = _macro_path(rng, n, per_day)
    _, d, v, *_ = regime_spells(
        u,
        lengths,
        np.asarray(params.jump_rows(False)),
        np.asarray(params.jump_rows(True)),
        mean,
        stressed,
        1.0 / params.minutes_per_step,
        drift,
        vol,
        REGIME_SMOOTHING,
        initial,
        0.0,
        float(drift[initial]),
        float(vol[initial]),
    )
    burn = min(n // 10, int(20 * float(mean.max())))
    vol_scale = 1.0 / np.sqrt(np.mean(v[burn:] ** 2))
    drift_shift = -float(np.mean(d[burn:]))
    targets = (drift + drift_shift, vol * vol_scale)
    for a in targets:
        a.setflags(write=False)  # shared by every simulator: never mutated
    return targets


def _macro_path(rng: np.random.Generator, n: int, per_day: int) -> np.ndarray:
    """A macro state per open minute with the statistics of the real one."""
    days = n // per_day + 1
    flips = rng.random(days)
    state, out = 0, np.empty(days, dtype=np.int8)
    for day in range(days):
        out[day] = state
        if flips[day] < 1.0 / (STRESSED_DAYS if state else CALM_DAYS):
            state = 1 - state
    return np.repeat(out, per_day)[:n]
