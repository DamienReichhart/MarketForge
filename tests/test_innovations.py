import numpy as np
import pytest
from scipy.linalg import cholesky
from scipy.stats import kurtosis

from marketforge.utils.random import RandomState
from marketforge.core.innovations import GaussianInnovations, StudentTInnovations


def _chol(corr):
    return cholesky(corr + np.eye(corr.shape[0]) * 1e-12, lower=True)


def test_gaussian_unit_variance_and_correlation(small_corr):
    L = _chol(small_corr)
    gen = GaussianInnovations()
    x = gen.generate(RandomState(1), n_steps=200_000, n_assets=3, cholesky_lower=L)
    assert x.shape == (200_000, 3)
    assert np.allclose(x.var(axis=0), 1.0, atol=0.05)
    assert np.allclose(np.corrcoef(x.T), small_corr, atol=0.02)


def test_student_t_unit_variance_fat_tails_and_correlation(small_corr):
    L = _chol(small_corr)
    gen = StudentTInnovations(nu=5.0)
    x = gen.generate(RandomState(2), n_steps=400_000, n_assets=3, cholesky_lower=L)
    assert np.allclose(x.var(axis=0), 1.0, atol=0.06)
    assert kurtosis(x[:, 0]) > 2.0
    assert np.allclose(np.corrcoef(x.T), small_corr, atol=0.03)


def test_student_t_requires_nu_above_two():
    with pytest.raises(ValueError):
        StudentTInnovations(nu=2.0)


def test_student_t_has_tail_dependence(small_corr):
    L = _chol(small_corr)
    gen = StudentTInnovations(nu=4.0)
    x = gen.generate(RandomState(3), n_steps=400_000, n_assets=3, cholesky_lower=L)
    # Condition on asset 0 being in its extreme tail; asset 1's average magnitude
    # should rise well above its unconditional average (joint tail dependence).
    thr = np.quantile(np.abs(x[:, 0]), 0.99)
    extreme = np.abs(x[:, 0]) > thr
    cond_mag = np.abs(x[extreme, 1]).mean()
    uncond_mag = np.abs(x[:, 1]).mean()
    assert cond_mag > 1.3 * uncond_mag
