# MarketForge
# Copyright (C) 2026 REICHHART Damien
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
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
    """Mean of (High-Low) / |Close-Open|, a measure of intrabar range richness."""
    o = np.asarray(open_, float); h = np.asarray(high, float)
    l = np.asarray(low, float); c = np.asarray(close, float)
    body = np.abs(c - o)
    rng_ = h - l
    mask = body > 1e-12
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
