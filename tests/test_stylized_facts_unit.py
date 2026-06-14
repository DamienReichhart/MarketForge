import numpy as np
from marketforge.validation.stylized_facts import (
    excess_kurtosis, volatility_clustering_strength, leverage_correlation,
    range_efficiency, ljung_box_pvalue,
)


def test_excess_kurtosis_detects_fat_tails():
    rng = np.random.default_rng(0)
    normal = rng.standard_normal(100_000)
    t = rng.standard_t(4, size=100_000)
    assert abs(excess_kurtosis(normal)) < 0.2
    assert excess_kurtosis(t) > 1.0


def test_volatility_clustering_strength_positive_for_garch_like():
    rng = np.random.default_rng(1)
    n = 50_000
    vol = np.empty(n); vol[0] = 1.0
    for i in range(1, n):
        vol[i] = 0.99 * vol[i-1] + 0.01 * abs(rng.standard_normal())
    r = vol * rng.standard_normal(n)
    assert volatility_clustering_strength(r) > volatility_clustering_strength(rng.standard_normal(n))


def test_leverage_correlation_negative_when_downmoves_raise_vol():
    rng = np.random.default_rng(2)
    n = 50_000
    r = np.empty(n); sig = np.ones(n)
    for i in range(1, n):
        sig[i] = 0.9 * sig[i-1] + (0.2 if r[i-1] < 0 else 0.05) * abs(r[i-1])
        r[i] = sig[i] * rng.standard_normal()
    assert leverage_correlation(r) < 0


def test_range_efficiency_in_unit_band():
    rng = np.random.default_rng(3)
    n = 10_000
    o = np.full(n, 100.0); c = 100.0 * np.exp(rng.normal(0, 0.001, n))
    h = np.maximum(o, c) + np.abs(rng.normal(0, 0.05, n))
    l = np.minimum(o, c) - np.abs(rng.normal(0, 0.05, n))
    val = range_efficiency(o, h, l, c)
    assert val > 1.0
