import numpy as np
from marketforge.config.settings import GeneratorConfig, AssetConfig, MarketType
from marketforge.core.returns import ReturnGenerator
from marketforge.utils.random import RandomState


def _cfg(nu=None, seasonal=True, n_assets=2):
    assets = [AssetConfig(f"A{i}", start_price=100.0, volatility=0.5) for i in range(n_assets)]
    corr = np.eye(n_assets)
    return GeneratorConfig(
        assets=assets, market_type=MarketType.CRYPTO,
        start_timestamp=1704067200, end_timestamp=1704067200 + 2 * 86400,
        correlation_matrix=corr, seed=11,
        innovation_nu=nu, seasonality_enabled=seasonal,
    )


def test_student_t_returns_have_fatter_tails_than_gaussian():
    from scipy.stats import kurtosis
    g = ReturnGenerator(_cfg(nu=None))
    t = ReturnGenerator(_cfg(nu=3.5))
    rg = g.generate(RandomState(1)).returns[:, 0]
    rt = t.generate(RandomState(1)).returns[:, 0]
    assert kurtosis(rt) > kurtosis(rg)


def test_seasonality_changes_conditional_volatility_shape():
    gen = ReturnGenerator(_cfg(nu=None, seasonal=True))
    res = gen.generate(RandomState(2))
    vol = res.volatilities[:, 0]
    assert vol.std() / vol.mean() > 1e-3


def test_reproducible():
    gen = ReturnGenerator(_cfg(nu=4.0))
    a = gen.generate(RandomState(5)).returns
    b = gen.generate(RandomState(5)).returns
    assert np.allclose(a, b)
