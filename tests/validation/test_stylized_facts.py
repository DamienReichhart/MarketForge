import numpy as np
import pytest

import marketforge as mf
from marketforge.validation import stylized_facts as sf
from marketforge.validation.stylized_facts import (
    excess_kurtosis,
    leverage_correlation,
    range_efficiency,
    volatility_clustering_strength,
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
    vol = np.empty(n)
    vol[0] = 1.0
    for i in range(1, n):
        vol[i] = 0.99 * vol[i - 1] + 0.01 * abs(rng.standard_normal())
    r = vol * rng.standard_normal(n)
    assert volatility_clustering_strength(r) > volatility_clustering_strength(
        rng.standard_normal(n)
    )


def test_leverage_correlation_negative_when_downmoves_raise_vol():
    rng = np.random.default_rng(2)
    n = 50_000
    r = np.empty(n)
    sig = np.ones(n)
    for i in range(1, n):
        sig[i] = 0.9 * sig[i - 1] + (0.2 if r[i - 1] < 0 else 0.05) * abs(r[i - 1])
        r[i] = sig[i] * rng.standard_normal()
    assert leverage_correlation(r) < 0


def test_range_efficiency_in_unit_band():
    rng = np.random.default_rng(3)
    n = 10_000
    o = np.full(n, 100.0)
    c = 100.0 * np.exp(rng.normal(0, 0.001, n))
    h = np.maximum(o, c) + np.abs(rng.normal(0, 0.05, n))
    l = np.minimum(o, c) - np.abs(rng.normal(0, 0.05, n))
    val = range_efficiency(o, h, l, c)
    assert val > 1.0


def test_standard_errors_match_the_textbook_for_independent_normal_data():
    r = np.random.default_rng(0).standard_normal(20_000) * 1e-3
    textbook = 1 / np.sqrt(r.size)
    assert sf.leverage_standard_error(r) == pytest.approx(textbook, rel=0.05)
    assert sf.abs_autocorrelation_standard_error(r, 60) == pytest.approx(textbook, rel=0.1)
    assert sf.excess_kurtosis_standard_error(r) == pytest.approx(np.sqrt(24 / r.size), rel=0.2)


def test_standard_errors_widen_for_heavy_tailed_clustered_returns():
    m1 = mf.generate("AAPL", start="2024-01-01", end="2024-01-15", seed=1)["AAPL"]["m1"]
    r = np.log(m1["close"] / m1["open"]).to_numpy()
    textbook = 1 / np.sqrt(r.size)
    assert sf.leverage_standard_error(r) > 1.3 * textbook
    assert sf.abs_autocorrelation_standard_error(r, 60) > 1.5 * textbook
    assert sf.excess_kurtosis_standard_error(r) > 2 * np.sqrt(24 / r.size)


def test_the_leverage_standard_error_is_calibrated_on_generated_stocks():
    """The spread of the statistic across seeds is what its standard error says."""
    values, errors = [], []
    for seed in range(1, 9):
        data = mf.generate("AAPL,JPM,XOM,KO", start="2024-01-01", end="2024-01-15", seed=seed)
        for frames in data.values():
            m1 = frames["m1"]
            r = np.log(m1["close"] / m1["open"]).to_numpy()
            values.append(sf.leverage_correlation(r))
            errors.append(sf.leverage_standard_error(r))
    ratio = np.std(values) / np.median(errors)
    assert 0.7 < ratio < 1.6  # 1/sqrt(n) gives about 2.5 here
