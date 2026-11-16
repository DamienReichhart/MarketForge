# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the MIT License. See the LICENSE file in the project
# root for full license information.

"""
End-to-end stylized-facts check: data from the public API must pass the
validation harness for every market, for several instruments and seeds.
"""

import pytest

import marketforge as mf
from marketforge.domain.markets import MarketType
from marketforge.validation.report import validate_ohlcv

CASES = {
    "crypto": ["BTCUSD", "ETHUSD", "SOLUSD"],
    "forex": ["EURUSD", "USDJPY", "EURJPY", "XAUUSD"],
    "stocks": ["AAPL", "MSFT", "JPM"],
}


@pytest.mark.parametrize("seed", [123, 7])
@pytest.mark.parametrize("market", list(CASES))
def test_generated_data_matches_stylized_facts(market, seed):
    data = mf.generate(CASES[market], start="2024-01-01", end="2024-01-15", seed=seed)
    for symbol in CASES[market]:
        d = data[symbol]["m1"]
        report = validate_ohlcv(d.open, d.high, d.low, d.close, MarketType(market))
        assert report.passed, f"{symbol}\n{report.summary()}"
