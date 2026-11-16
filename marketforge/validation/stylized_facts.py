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


# Standard errors of the statistics above, for the sampling-noise allowance of
# the validation bands. The textbook 1/sqrt(n) (and sqrt(24/n) for kurtosis)
# hold for independent normal data only; minute returns are heavy-tailed and
# their volatility clusters, and on generated stock data the leverage
# correlation scatters 2.5 times more than 1/sqrt(n) says. These use the
# sample's own moments instead, so they widen exactly where a few large or
# clustered minutes dominate the statistic.


def _standardised(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    spread = x.std()
    return (x - x.mean()) / spread if spread > 0 else np.zeros_like(x)


def _correlation_standard_error(x: np.ndarray, y: np.ndarray, overlap: int = 0) -> float:
    """
    Standard error of corr(x, y), robust to heavy tails and to clustering: the
    Newey-West variance of the mean of the standardised products. The
    bandwidth is the usual 4 * (n / 100) ** (2 / 9), and at least ``overlap``:
    the number of steps over which consecutive products share data (the lag,
    for an autocorrelation). It is 1/sqrt(n) for independent normal data.

    For the autocorrelation of |returns| it is still an underestimate: how
    much volatility persists over an hour depends on a handful of regime
    changes, which no two-week sample can measure.
    """
    n = x.size
    if n < 2:
        return 0.0
    product = _standardised(x) * _standardised(y)
    product = product - product.mean()
    lags = min(n - 1, max(overlap, int(4.0 * (n / 100.0) ** (2.0 / 9.0))))
    variance = float(np.dot(product, product)) / n
    for k in range(1, lags + 1):
        weight = 1.0 - k / (lags + 1.0)
        variance += 2.0 * weight * float(np.dot(product[:-k], product[k:])) / n
    return float(np.sqrt(max(variance, 0.0) / n))


def excess_kurtosis_standard_error(returns: np.ndarray) -> float:
    """
    Standard error of the sample kurtosis of a symmetric distribution, from the
    sample's fourth, sixth and eighth moments (sqrt(24/n) for normal data).
    """
    z = _standardised(returns)
    if z.size < 2:
        return 0.0
    m4, m6, m8 = (float(np.mean(z**k)) for k in (4, 6, 8))
    variance = m8 - 4.0 * m4 * m6 + 4.0 * m4**3 - m4**2
    return float(np.sqrt(max(variance, 24.0) / z.size))


def leverage_standard_error(returns: np.ndarray) -> float:
    """Standard error of :func:`leverage_correlation`."""
    r = np.asarray(returns, dtype=float)
    return _correlation_standard_error(r[:-1], np.abs(r[1:]))


def abs_autocorrelation_standard_error(returns: np.ndarray, lag: int) -> float:
    """Standard error of the autocorrelation of |returns| at ``lag``."""
    a = np.abs(np.asarray(returns, dtype=float))
    return _correlation_standard_error(a[:-lag], a[lag:], overlap=lag)


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
