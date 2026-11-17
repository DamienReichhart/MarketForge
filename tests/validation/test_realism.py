# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

"""
Modelled properties of generated data, measured from the public API.

The expected values are the catalog's stated relationships (literal numbers
from marketforge/config/catalog), or properties of real markets.
"""

import numpy as np
import pandas as pd
import pytest

import marketforge as mf


def _returns(data, timeframe: str) -> pd.DataFrame:
    closes = data.panel("close", timeframe)
    return np.log(closes).diff().dropna()


@pytest.fixture(scope="module")
def forex():
    return mf.generate(
        "EURUSD,GBPUSD,USDCHF,USDJPY,AUDUSD,NZDUSD,AUDNZD,EURGBP",
        start="2024-01-01",
        end="2024-07-01",
        seed=11,
        timeframes="H1",
    )


@pytest.mark.parametrize(
    ("a", "b", "stated"),
    [
        ("EURUSD", "USDCHF", -0.92),
        ("EURUSD", "GBPUSD", 0.82),
        ("AUDUSD", "NZDUSD", 0.88),
        ("EURUSD", "USDJPY", -0.55),
    ],
)
def test_forex_anchor_correlations_are_the_ones_the_catalog_states(forex, a, b, stated):
    realised = _returns(forex, "H1")[[a, b]].corr().iloc[0, 1]
    assert realised == pytest.approx(stated, abs=0.1)


@pytest.mark.parametrize(("cross", "stated"), [("AUDNZD", 0.070), ("EURGBP", 0.060)])
def test_forex_crosses_have_about_their_catalog_volatility(forex, cross, stated):
    # Relative to EURUSD (stated 0.065), so the regimes' common scaling cancels.
    returns = _returns(forex, "H1")
    ratio = returns[cross].std() / returns["EURUSD"].std()
    assert ratio == pytest.approx(stated / 0.065, rel=0.25)


@pytest.mark.parametrize(
    ("market", "a", "b", "stated"),
    [
        ("crypto", "BTCUSD", "ETHUSD", 0.88),
        ("crypto", "BTCUSD", "LTCUSD", 0.85),
        ("stocks", "AAPL", "MSFT", 0.78),
    ],
)
def test_stated_correlations_survive_into_the_data(market, a, b, stated):
    data = mf.generate([a, b], start="2024-01-01", end="2024-04-01", seed=5, timeframes="H1")
    realised = _returns(data, "H1").corr().iloc[0, 1]
    assert realised == pytest.approx(stated, abs=0.1)
