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

CASES = {
    "crypto": ["BTCUSD", "ETHUSD", "SOLUSD"],
    "forex": ["EURUSD", "USDJPY", "EURJPY", "XAUUSD"],
    "stocks": ["AAPL", "MSFT", "JPM"],
}


@pytest.mark.parametrize("seed", [123, 7])
@pytest.mark.parametrize("market", list(CASES))
def test_generated_data_matches_stylized_facts(market, seed):
    data = mf.generate(
        CASES[market], start="2024-01-01", end="2024-01-15", seed=seed, include_spread=True
    )
    for symbol in CASES[market]:
        report = mf.validate(data[symbol]["m1"], market)
        assert report.passed, f"{symbol}\n{report.summary()}"
        assert {"spread_bps", "spread_widening"} <= set(report.metrics)
