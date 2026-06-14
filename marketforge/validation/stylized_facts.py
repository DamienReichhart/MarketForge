# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the MIT License. See the LICENSE file in the project
# root for full license information.
"""
Stylized-fact metrics for validating synthetic market data against the
documented statistical properties of real financial returns.
"""

from __future__ import annotations

import numpy as np
from scipy.stats import kurtosis


def log_returns(close: np.ndarray) -> np.ndarray:
    """Close-to-close log returns."""
    close = np.asarray(close, dtype=float)
    return np.diff(np.log(close))


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
    """Mean of (High-Low) / |Close-Open|, a measure of intrabar range richness.

    Near-doji candles (body < 0.01% of mid-price) are excluded from the mean
    because their body is effectively zero on a relative scale and would
    produce arbitrarily large ratios that are not meaningful.
    """
    o = np.asarray(open_, float); h = np.asarray(high, float)
    l = np.asarray(low, float); c = np.asarray(close, float)
    body = np.abs(c - o)
    rng_ = h - l
    mid = (h + l) * 0.5
    # Relative threshold: exclude bars where body < 0.01% of mid-price
    mask = body > mid * 1e-4
    if not np.any(mask):
        return float("inf")
    return float(np.mean(rng_[mask] / body[mask]))


def ljung_box_pvalue(x: np.ndarray, lags: int = 20) -> float:
    """Ljung-Box p-value (small => significant autocorrelation present)."""
    from statsmodels.stats.diagnostic import acorr_ljungbox
    res = acorr_ljungbox(np.asarray(x, dtype=float), lags=[lags], return_df=True)
    return float(res["lb_pvalue"].iloc[-1])


def arch_lm_pvalue(returns: np.ndarray, lags: int = 12) -> float:
    """ARCH-LM test p-value (small => volatility clustering / ARCH effects)."""
    from statsmodels.stats.diagnostic import het_arch
    r = np.asarray(returns, dtype=float)
    r = r - r.mean()
    return float(het_arch(r, nlags=lags)[1])
