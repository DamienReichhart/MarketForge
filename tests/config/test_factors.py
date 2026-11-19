import numpy as np
import pytest

from marketforge.config.catalog.forex.instruments import INSTRUMENTS
from marketforge.config.factors import FactorStructure, forex_structure


def _row(fs: FactorStructure, symbol: str) -> dict[str, float]:
    w = fs.weights[fs.instruments.index(symbol)]
    return {fs.factors[j]: w[j] for j in np.nonzero(w)[0]}


def test_identity_structure():
    fs = FactorStructure.identity(["A", "B"])
    assert fs.is_identity
    np.testing.assert_array_equal(fs.weights, np.eye(2))


def test_crosses_are_signed_sums_of_usd_anchors():
    fs = forex_structure(["EURUSD", "USDJPY", "GBPUSD", "EURJPY", "EURGBP", "GBPJPY"])
    assert fs.factors == ("EURUSD", "USDJPY", "GBPUSD")
    assert _row(fs, "EURJPY") == {"EURUSD": 1, "USDJPY": 1}
    assert _row(fs, "EURGBP") == {"EURUSD": 1, "GBPUSD": -1}
    assert _row(fs, "GBPJPY") == {"GBPUSD": 1, "USDJPY": 1}


def test_codes_without_usd_pair_anchor_through_another_code():
    fs = forex_structure(["EURUSD", "GRXEUR"])
    assert fs.factors == ("EURUSD", "GRXEUR")
    assert _row(fs, "GRXEUR") == {"GRXEUR": 1}


def test_unreachable_code_is_rejected():
    with pytest.raises(ValueError, match="cannot be linked"):
        forex_structure(["EURUSD", "AUDNZD"])


def test_full_forex_catalog_derives_every_cross_consistently():
    symbols = list(INSTRUMENTS)
    fs = forex_structure(symbols)
    assert len(fs.factors) < len(symbols)
    log_start = np.log([INSTRUMENTS[s].start_price for s in fs.factors])
    derived = np.exp(fs.weights @ log_start)
    implied = dict(zip(fs.instruments, derived, strict=True))
    # Derived start prices agree with the catalog to within a few percent.
    assert abs(implied["EURJPY"] / INSTRUMENTS["EURJPY"].start_price - 1) < 0.02
    assert abs(implied["EURGBP"] / INSTRUMENTS["EURGBP"].start_price - 1) < 0.02
