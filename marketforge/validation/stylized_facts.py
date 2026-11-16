# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the GNU Affero General Public License v3.0 or later.
# See the LICENSE file in the project root for full license information.
"""
Stylized-fact metrics for validating synthetic market data against the
documented statistical properties of real financial returns.
"""

from __future__ import annotations

import numpy as np
from scipy.stats import kurtosis


def excess_kurtosis(returns: np.ndarray) -> float:
    """Excess kurtosis (0 for a normal distribution; > 0 = fat tails)."""
    return float(kurtosis(np.asarray(returns, dtype=float), fisher=True, bias=False))


def _acf(x: np.ndarray, lag: int) -> float:
    x = np.asarray(x, dtype=float)
    x = x - x.mean()
    denom = np.sum(x * x)
    if denom == 0:
        return 0.0
    return float(np.sum(x[:-lag] * x[lag:]) / denom)


def volatility_clustering_strength(returns: np.ndarray, max_lag: int = 20) -> float:
    """Mean autocorrelation of |returns| over the first ``max_lag`` lags.

    Positive and slowly decaying for real markets; ~0 for i.i.d. noise.
    """
    a = np.abs(np.asarray(returns, dtype=float))
    return float(np.mean([_acf(a, k) for k in range(1, max_lag + 1)]))


def leverage_correlation(returns: np.ndarray) -> float:
    """corr(r_t, |r_{t+1}|): negative indicates the leverage effect."""
    r = np.asarray(returns, dtype=float)
    if r.size < 3:
        return 0.0
    return float(np.corrcoef(r[:-1], np.abs(r[1:]))[0, 1])


def range_efficiency(open_, high, low, close) -> float:
    """Mean intrabar range over mean absolute body: mean(High-Low) / mean(|Close-Open|).

    A driftless Brownian path gives 2.0 (E[range] = 2*sqrt(2/pi)*s versus
    E|body| = sqrt(2/pi)*s). Using the ratio of means needs no threshold for
    near-doji candles; the previous mean of per-candle ratios dropped bodies
    under 1 bp and returned inf for quiet instruments such as pegged USDHKD.
    """
    o = np.asarray(open_, float)
    h = np.asarray(high, float)
    l = np.asarray(low, float)
    c = np.asarray(close, float)
    body = float(np.mean(np.abs(c - o)))
    if body == 0.0:
        return float("inf")
    return float(np.mean(h - l) / body)


def median_spread_bps(spread: np.ndarray, close: np.ndarray) -> float:
    """Median quoted spread, in basis points of the price."""
    return float(1e4 * np.median(np.asarray(spread, dtype=float) / np.asarray(close, dtype=float)))


def spread_widening(spread: np.ndarray, returns: np.ndarray, window: int = 30) -> float:
    """
    Mean spread during the most turbulent tenth of the minutes, relative to
    the median spread. Turbulence is the mean |return| of the ``window``
    minutes up to each one. Above 1: spreads widen when the market moves.
    """
    s = np.asarray(spread, dtype=float)
    moves = np.abs(np.asarray(returns, dtype=float))
    if s.size <= window:
        return float("nan")
    total = np.concatenate(([0.0], np.cumsum(moves)))
    turbulence = total[window:] - total[:-window]
    recent = s[window - 1 :]
    turbulent = turbulence >= np.quantile(turbulence, 0.9)
    return float(recent[turbulent].mean() / np.median(s))
