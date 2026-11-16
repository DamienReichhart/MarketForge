import numpy as np
import pytest

from marketforge.simulation.innovations import correlated_shocks

CORR = np.array([[1.0, 0.6, 0.3], [0.6, 1.0, 0.5], [0.3, 0.5, 1.0]])
L = np.linalg.cholesky(CORR)


def _draw(nu, n=400_000, seed=0):
    rng = np.random.default_rng(seed)
    return correlated_shocks(rng.standard_normal((n, 3)), rng.chisquare(nu or 5, n), L, nu)


@pytest.mark.parametrize("nu", [None, 6.0])
def test_unit_variance_and_target_correlation(nu):
    z = _draw(nu)
    np.testing.assert_allclose(z.var(axis=0), 1.0, atol=0.03)
    np.testing.assert_allclose(np.corrcoef(z.T), CORR, atol=0.02)


def test_student_t_has_fat_tails_and_tail_dependence():
    t, g = _draw(6.0), _draw(None)
    kurt = lambda x: ((x - x.mean()) ** 4).mean() / x.var() ** 2 - 3
    assert kurt(t[:, 0]) > 1.5 and abs(kurt(g[:, 0])) < 0.1
    q = lambda x: np.quantile(np.abs(x), 0.999)
    joint = lambda z: np.mean((np.abs(z[:, 0]) > q(z[:, 0])) & (np.abs(z[:, 2]) > q(z[:, 2])))
    assert joint(t) > 2 * joint(g)


def test_nu_must_exceed_two():
    with pytest.raises(ValueError):
        correlated_shocks(np.zeros((1, 3)), np.ones(1), L, 2.0)
