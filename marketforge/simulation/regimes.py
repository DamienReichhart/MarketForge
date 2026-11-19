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

from marketforge.config.catalog.forex.risk import RISK_LOADINGS, STOCK_INDICES
from marketforge.config.factors import split_pair
from marketforge.config.model_params import RegimeParams
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


def stock_market_shares(anchors: Sequence[str]) -> np.ndarray:
    """How much of the stock market's trend each forex anchor follows.

    An index CFD follows it by its risk loading relative to the S&P 500's
    (1 for SPXUSD), positively when the index is the base, negatively when
    the quote; every other anchor, 0.
    """
    spx = RISK_LOADINGS["SPX"]
    shares = []
    for symbol in anchors:
        base, quote = split_pair(symbol)
        share = RISK_LOADINGS[base] / spx if base in STOCK_INDICES else 0.0
        share -= RISK_LOADINGS[quote] / spx if quote in STOCK_INDICES else 0.0
        shares.append(share)
    return np.array(shares)


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
    """Exact long-run moments of the regime multipliers, mixed over the macro state.

    With the macro state fixed, regime i holds a share of time proportional to
    pi_i * m_i, where pi is the stationary distribution of the jump chain and
    m_i the mean spell (shortened while stressed for calm regimes, which may
    end early). The smoothing lags each jump from j to i: over the spell that
    follows, it adds (x_j - x_i) / a to the integral of x and
    2 x_i (x_j - x_i) / a + (x_j - x_i)^2 / (1 - (1 - a)^2) to that of x^2,
    exactly when spells outlast the ramp (hours against 15 minutes). Macro
    spells (weeks) outlast regime spells, so the two states mix by their
    shares. Exact, where a simulation of the chain carried percent-level
    noise into every market's volatility.
    """
    drift = spell_trends(params)
    vol = np.asarray(params.volatility_multipliers, dtype=float)
    stressed_share = STRESSED_DAYS / (CALM_DAYS + STRESSED_DAYS)
    mean_drift = mean_square = 0.0
    for stressed, share in ((False, 1.0 - stressed_share), (True, stressed_share)):
        d, v2 = _fixed_state_moments(params, drift, vol, stressed)
        mean_drift += share * d
        mean_square += share * v2
    targets = (drift - mean_drift, vol / np.sqrt(mean_square))
    for a in targets:
        a.setflags(write=False)  # shared by every simulator: never mutated
    return targets


def _fixed_state_moments(
    params: RegimeParams, drift: np.ndarray, vol: np.ndarray, stressed: bool
) -> tuple[float, float]:
    """Long-run mean of the smoothed trend, and mean square of the smoothed volatility."""
    cumulative = np.asarray(params.jump_rows(stressed))
    jumps = np.diff(
        np.concatenate([np.zeros((cumulative.shape[0], 1)), cumulative], axis=1), axis=1
    )
    eigenvalues, eigenvectors = np.linalg.eig(jumps.T)
    pi = np.real(eigenvectors[:, np.argmin(np.abs(eigenvalues - 1.0))])
    pi = pi / pi.sum()
    mean = np.asarray(params.mean_minutes())
    if stressed:  # calm spells also end at a rate h: E[min(T, Exp(h))] for T ~ m Gamma(k)/k
        h, k = 1.0 / params.minutes_per_step, params.spell_shape
        shortened = (1.0 - (1.0 + h * mean / k) ** -k) / h
        mean = np.where(np.arange(mean.size) <= 2, shortened, mean)
    cycle = float(pi @ mean)  # mean minutes per spell
    a = REGIME_SMOOTHING
    rate = pi[:, None] * jumps / cycle  # jumps from j (row) to i (column), per minute
    dd = drift[:, None] - drift[None, :]  # x_j - x_i
    dv = vol[:, None] - vol[None, :]
    mean_drift = float(pi * mean @ drift) / cycle + float(np.sum(rate * dd)) / a
    lag2 = 2.0 * vol[None, :] * dv / a + dv**2 / (1.0 - (1.0 - a) ** 2)
    mean_square = float(pi * mean @ vol**2) / cycle + float(np.sum(rate * lag2))
    return mean_drift, mean_square
