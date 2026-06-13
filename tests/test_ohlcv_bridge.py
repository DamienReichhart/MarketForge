import numpy as np
from marketforge.generators.ohlcv import intrabar_high_low
from marketforge.utils.random import RandomState


def test_high_low_bracket_open_close():
    rng = RandomState(3)
    n = 5000
    openp = np.full(n, 100.0)
    closep = 100.0 * np.exp(rng.normal(0, 0.001, n))
    sigma = np.full(n, 0.001)
    high, low = intrabar_high_low(rng, openp, closep, sigma, k=8)
    body_high = np.maximum(openp, closep)
    body_low = np.minimum(openp, closep)
    assert np.all(high >= body_high - 1e-9)
    assert np.all(low <= body_low + 1e-9)
    assert np.all(high >= low)
    assert np.all(low > 0)


def test_range_scales_with_volatility():
    rng = RandomState(4)
    n = 20000
    openp = np.full(n, 100.0)
    closep = np.full(n, 100.0)
    lo_sigma = np.full(n, 0.0005)
    hi_sigma = np.full(n, 0.005)
    h1, l1 = intrabar_high_low(RandomState(4), openp, closep, lo_sigma, k=8)
    h2, l2 = intrabar_high_low(RandomState(4), openp, closep, hi_sigma, k=8)
    assert np.mean(h2 - l2) > 3 * np.mean(h1 - l1)
