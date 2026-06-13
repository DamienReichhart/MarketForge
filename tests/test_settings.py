import numpy as np
from marketforge.config.settings import (
    GeneratorConfig, AssetConfig, MarketType, VolumeParams,
)


def _cfg(**kw):
    return GeneratorConfig(
        assets=[AssetConfig("X", start_price=100.0, volatility=0.3)],
        market_type=MarketType.CRYPTO,
        start_timestamp=1704067200,
        end_timestamp=1704067200 + 3600,
        **kw,
    )


def test_new_fields_have_defaults():
    cfg = _cfg()
    assert cfg.innovation_nu is None
    assert cfg.seasonality_enabled is True
    assert isinstance(cfg.volume_params, VolumeParams)
    assert 0 < cfg.volume_params.phi < 1


def test_volume_params_validation():
    import pytest
    with pytest.raises(ValueError):
        VolumeParams(phi=1.0)
    with pytest.raises(ValueError):
        VolumeParams(phi=-0.1)


def test_innovation_nu_must_exceed_two():
    import pytest
    with pytest.raises(ValueError):
        _cfg(innovation_nu=1.5)
