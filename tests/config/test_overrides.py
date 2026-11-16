import numpy as np
import pytest

from marketforge.config.loader import load_catalog
from marketforge.config.overrides import OverrideError
from marketforge.domain.markets import MarketType


def _write(tmp_path, text):
    p = tmp_path / "o.toml"
    p.write_text(text)
    return p


def test_override_existing_instrument(tmp_path):
    cat = load_catalog(
        _write(tmp_path, "[instruments.btcusd]\nstart_price = 42000\nvolatility = 0.7\n")
    )
    btc = cat[MarketType.CRYPTO].get_instrument("BTCUSD")
    assert btc.start_price == 42000 and btc.volatility == 0.7
    # The cached built-in catalog is untouched.
    assert load_catalog()[MarketType.CRYPTO].get_instrument("BTCUSD").start_price != 42000


def test_add_new_instrument_with_correlations(tmp_path):
    cat = load_catalog(
        _write(
            tmp_path,
            """
[instruments.MYCOIN]
market = "crypto"
start_price = 1.5
volatility = 0.9
correlations = { BTCUSD = 0.6 }
""",
        )
    )
    cfg = cat[MarketType.CRYPTO]
    assert cfg.symbols[-1] == "MYCOIN"
    i, j = cfg.symbols.index("MYCOIN"), cfg.symbols.index("BTCUSD")
    assert cfg.correlation_matrix[i, j] == pytest.approx(0.6, abs=0.02)
    assert np.linalg.eigvalsh(cfg.correlation_matrix).min() > 0


@pytest.mark.parametrize(
    "text,match",
    [
        ("[instruments.NEW]\nstart_price = 1\nvolatility = 0.1\n", "set market"),
        ("[instruments.NEW]\nmarket = 'crypto'\nvolatility = 0.1\n", "needs start_price"),
        ("[instruments.BTCUSD]\nmarket = 'stocks'\n", "already exists"),
        ("[instruments.BTCUSD]\nprice = 1\n", "unknown key"),
        ("[instruments.BTCUSD]\nvolatility = -1\n", "volatility must be positive"),
        ("[instruments.BTCUSD]\ncorrelations = { AAPL = 0.5 }\n", "not a crypto instrument"),
        ("[assets.BTCUSD]\nvolatility = 1\n", "unknown top-level"),
    ],
)
def test_invalid_overrides_are_explained(tmp_path, text, match):
    with pytest.raises(OverrideError, match=match):
        load_catalog(_write(tmp_path, text))
