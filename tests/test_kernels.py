import numpy as np

from marketforge.core.kernels import ar1, bridge_extremes, gjr_garch, regime_chain


def _cum(p):
    return np.cumsum(np.asarray(p, dtype=float), axis=1)


def test_regime_chain_matches_stationary_distribution():
    p = np.array([[0.9, 0.1], [0.3, 0.7]])
    rng = np.random.default_rng(0)
    regimes, *_ = regime_chain(
        rng.random(200_000), _cum(p), np.zeros(2), np.ones(2), 1.0, 0, 0.0, 1.0
    )
    # Stationary distribution of p is (0.75, 0.25).
    assert abs((regimes == 0).mean() - 0.75) < 0.01


def test_regime_chain_is_resumable():
    p = np.array([[0.8, 0.2], [0.4, 0.6]])
    u = np.random.default_rng(1).random(1000)
    args = (_cum(p), np.array([1.0, -1.0]), np.array([1.0, 3.0]), 0.1)
    full = regime_chain(u, *args, 0, 1.0, 1.0)
    first = regime_chain(u[:400], *args, 0, 1.0, 1.0)
    second = regime_chain(u[400:], *args, *first[3:])
    for a, b1, b2 in zip(full[:3], first[:3], second[:3]):
        np.testing.assert_array_equal(a, np.concatenate([b1, b2]))


def test_gjr_garch_has_unit_unconditional_variance_and_clustering():
    alpha, beta, gamma = 0.05, 0.85, 0.08
    omega = 1 - (alpha + beta + gamma / 2)
    z = np.random.default_rng(2).standard_normal((400_000, 1))
    h, *_ = gjr_garch(z, omega, alpha, beta, gamma, np.ones(1), np.zeros(1))
    e = np.sqrt(h[:, 0]) * z[:, 0]
    assert abs(e.var() - 1.0) < 0.05
    a = np.abs(e)
    assert np.corrcoef(a[:-1], a[1:])[0, 1] > 0.05


def test_gjr_garch_is_resumable():
    z = np.random.default_rng(3).standard_normal((500, 3))
    params = (0.1, 0.05, 0.85, 0.0)
    full, *_ = gjr_garch(z, *params, np.ones(3), np.zeros(3))
    h1, v, e = gjr_garch(z[:200], *params, np.ones(3), np.zeros(3))
    h2, *_ = gjr_garch(z[200:], *params, v, e)
    np.testing.assert_array_equal(full, np.vstack([h1, h2]))


def test_ar1_is_resumable_and_persistent():
    u = np.random.default_rng(4).standard_normal((10_000, 2))
    full, _ = ar1(u, 0.7, np.zeros(2))
    y1, s = ar1(u[:3000], 0.7, np.zeros(2))
    y2, _ = ar1(u[3000:], 0.7, s)
    np.testing.assert_array_equal(full, np.vstack([y1, y2]))
    assert abs(np.corrcoef(full[:-1, 0], full[1:, 0])[0, 1] - 0.7) < 0.03


def test_bridge_extremes_bracket_the_body_and_match_brownian_range():
    rng = np.random.default_rng(5)
    n = 200_000
    b = rng.standard_normal(n)  # Brownian increment over a unit bar, std 1
    hi, lo = bridge_extremes(b, np.ones(n), 1 - rng.random(n), 1 - rng.random(n))
    assert np.all(hi >= np.maximum(0, b) - 1e-12)
    assert np.all(lo <= np.minimum(0, b) + 1e-12)
    # E[max - min] of Brownian motion over a unit interval is 2*sqrt(2/pi).
    assert abs((hi - lo).mean() - 2 * np.sqrt(2 / np.pi)) < 0.02
