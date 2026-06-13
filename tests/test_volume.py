import numpy as np
from marketforge.config.settings import GeneratorConfig, AssetConfig, MarketType, VolumeParams
from marketforge.generators.volume import VolumeGenerator
from marketforge.utils.random import RandomState


def _cfg():
    return GeneratorConfig(
        assets=[AssetConfig("A", start_price=100.0, volatility=0.4, volume_base=5000.0)],
        market_type=MarketType.CRYPTO,
        start_timestamp=1704067200, end_timestamp=1704067200 + 86400,
        volume_params=VolumeParams(phi=0.8, lam=0.4, noise_sigma=0.3),
    )


def test_volume_positive_and_level_near_base():
    cfg = _cfg()
    gen = VolumeGenerator(cfg)
    n = cfg.duration_minutes
    rng = RandomState(9)
    std_abs_ret = np.abs(rng.standard_normal((n, 1)))
    vols = gen.generate(rng, n, abs_returns=std_abs_ret)
    assert np.all(vols > 0)
    assert 2500.0 < vols[:, 0].mean() < 10000.0


def test_volume_has_autocorrelation():
    cfg = _cfg()
    gen = VolumeGenerator(cfg)
    n = cfg.duration_minutes
    rng = RandomState(10)
    std_abs_ret = np.abs(rng.standard_normal((n, 1)))
    v = gen.generate(rng, n, abs_returns=std_abs_ret)[:, 0]
    lv = np.log(v)
    ac1 = np.corrcoef(lv[:-1], lv[1:])[0, 1]
    assert ac1 > 0.3


def test_volume_correlates_with_abs_returns():
    cfg = _cfg()
    gen = VolumeGenerator(cfg)
    n = cfg.duration_minutes
    rng = RandomState(12)
    z = rng.standard_normal((n, 1))
    abs_z = np.abs(z)
    v = gen.generate(rng, n, abs_returns=abs_z)[:, 0]
    assert np.corrcoef(abs_z[:, 0], v)[0, 1] > 0.1


def test_volume_with_seasonality_stays_positive_and_autocorrelated():
    cfg = _cfg()
    gen = VolumeGenerator(cfg)
    n = cfg.duration_minutes
    ts = np.arange(cfg.start_timestamp, cfg.start_timestamp + n * 60, 60, dtype=np.int64)
    rng = RandomState(13)
    abs_ret = np.abs(rng.standard_normal((n, 1)))
    v = gen.generate(rng, n, abs_returns=abs_ret, timestamps=ts)[:, 0]
    assert np.all(np.isfinite(v)) and np.all(v > 0)
    lv = np.log(v)
    assert np.corrcoef(lv[:-1], lv[1:])[0, 1] > 0.3
