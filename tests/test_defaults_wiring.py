from marketforge.configs.loader import market_config_to_generator_config, load_market_config
from marketforge.config.settings import MarketType


def test_generator_config_gets_market_model_params():
    mc = load_market_config("crypto")
    gc = market_config_to_generator_config(
        mc, start_timestamp=1704067200, end_timestamp=1704067200 + 3600,
        seed=1, batch_symbols=mc.symbols[:3],
    )
    assert gc.innovation_nu is not None and gc.innovation_nu <= 4.0
    assert gc.garch_params.gamma > 0.0
    assert gc.volume_params.phi > 0.0


def test_forex_has_higher_nu_than_crypto():
    fx = market_config_to_generator_config(
        load_market_config("forex"), 1704067200, 1704067200 + 3600, batch_symbols=["EURUSD"],
    )
    cr = market_config_to_generator_config(
        load_market_config("crypto"), 1704067200, 1704067200 + 3600,
        batch_symbols=load_market_config("crypto").symbols[:1],
    )
    assert fx.innovation_nu > cr.innovation_nu
