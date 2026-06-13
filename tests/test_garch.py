import numpy as np
from marketforge.config.settings import GARCHParams
from marketforge.core.garch import GARCHModel
from marketforge.utils.random import RandomState


def test_gamma_default_zero_is_symmetric():
    p = GARCHParams(alpha=0.05, beta=0.90)
    assert p.gamma == 0.0
    assert abs(p.persistence - 0.95) < 1e-12


def test_stationarity_constraint_includes_gamma():
    import pytest
    with pytest.raises(ValueError):
        GARCHParams(alpha=0.10, beta=0.90, gamma=0.10)  # 0.10+0.90+0.05 = 1.05


def test_long_run_variance_matches_base_volatility():
    base_vol = 0.30
    p = GARCHParams(alpha=0.06, beta=0.88, gamma=0.04)
    model = GARCHModel(p, base_volatility=base_vol)
    per_minute_var = (base_vol ** 2) / (252 * 24 * 60)
    assert abs(model.unconditional_variance - per_minute_var) / per_minute_var < 1e-9


def test_negative_shocks_raise_volatility_more():
    p = GARCHParams(alpha=0.05, beta=0.88, gamma=0.10)
    m_neg = GARCHModel(p, base_volatility=0.3)
    m_pos = GARCHModel(p, base_volatility=0.3)
    m_neg.initialize_state()
    m_pos.initialize_state()
    s_neg = m_neg.step(-2.0)
    s_pos = m_pos.step(+2.0)
    n_neg = m_neg.step(0.0).variance
    n_pos = m_pos.step(0.0).variance
    assert n_neg > n_pos
