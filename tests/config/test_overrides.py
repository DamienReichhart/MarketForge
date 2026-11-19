import numpy as np
import pytest

from marketforge.config.catalog.fitted import minute_correlation
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
    # A stated correlation is a daily one: the minute shocks get what gives it.
    assert cfg.correlation_matrix[i, j] == pytest.approx(
        minute_correlation(MarketType.CRYPTO, 0.6), abs=0.02
    )
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


def test_overrides_can_be_a_mapping():
    cat = load_catalog(
        {
            "btcusd": {"start_price": 42000},
            "MYCOIN": {
                "market": "crypto",
                "start_price": 1.5,
                "volatility": 0.9,
                "correlations": {"BTCUSD": 0.6},
            },
        }
    )
    crypto = cat[MarketType.CRYPTO]
    assert crypto.get_instrument("BTCUSD").start_price == 42000
    assert "MYCOIN" in crypto.symbols
    with pytest.raises(OverrideError, match=r"overrides: \[instruments.BTCUSD\] has unknown key"):
        load_catalog({"BTCUSD": {"price": 1}})


def _clipped(matrix):
    """The eigenvalue clipping 3.x and early 4.0 used: the comparison to beat."""
    values, vectors = np.linalg.eigh(matrix)
    out = vectors @ np.diag(np.maximum(values, 1e-6)) @ vectors.T
    d = np.sqrt(np.diag(out))
    return out / np.outer(d, d)


def test_edited_correlations_hold_exactly_when_the_catalog_must_give_way():
    # BTC-ETH -0.5 contradicts every other crypto correlation, but it is possible
    # on its own: the user's value must hold and the rest of the market move.
    with pytest.warns(UserWarning, match="crypto: overridden correlations"):
        cfg = load_catalog({"BTCUSD": {"correlations": {"ETHUSD": -0.5}}})[MarketType.CRYPTO]
    i, j = cfg.symbols.index("BTCUSD"), cfg.symbols.index("ETHUSD")
    held = minute_correlation(MarketType.CRYPTO, -0.5)  # the minute value of a daily -0.5
    assert cfg.correlation_matrix[i, j] == pytest.approx(held, abs=1e-6)
    assert np.linalg.eigvalsh(cfg.correlation_matrix).min() > 0
    np.testing.assert_allclose(np.diag(cfg.correlation_matrix), 1.0)


def test_contradictory_edits_get_the_nearest_valid_matrix_and_say_how_far():
    edits = {
        "BTCUSD": {"correlations": {"ETHUSD": 0.95, "SOLUSD": 0.95}},
        "ETHUSD": {"correlations": {"SOLUSD": -0.95}},
    }
    with pytest.warns(UserWarning, match=r"cannot all hold; moved by up to \d\.\d+"):
        cfg = load_catalog(edits)[MarketType.CRYPTO]
    m = cfg.correlation_matrix
    assert np.linalg.eigvalsh(m).min() > 0
    # Nearer to what was asked than eigenvalue clipping gets.
    raw = m.copy()
    s = [cfg.symbols.index(x) for x in ("BTCUSD", "ETHUSD", "SOLUSD")]
    base = load_catalog()[MarketType.CRYPTO].correlation_matrix
    raw[:] = base
    for (a, b), rho in {(0, 1): 0.95, (0, 2): 0.95, (1, 2): -0.95}.items():
        raw[s[a], s[b]] = raw[s[b], s[a]] = rho
    assert np.linalg.norm(m - raw) <= np.linalg.norm(_clipped(raw) - raw) + 1e-9


def test_tick_size_is_overridable_and_must_be_a_power_of_ten():
    import marketforge as mf

    data = mf.generate(
        "BTCUSD",
        start="2024-01-02",
        days=1,
        seed=1,
        timeframes="m1",
        overrides={"BTCUSD": {"tick_size": 10.0}},
    )
    close = data["BTCUSD"]["m1"]["close"].to_numpy()
    assert (close % 10 == 0).all()
    with pytest.raises(ValueError, match="power of ten"):
        mf.generate("BTCUSD", start="2024-01-02", days=1, overrides={"BTCUSD": {"tick_size": 0.5}})
