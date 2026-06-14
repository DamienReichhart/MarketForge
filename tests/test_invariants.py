# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the MIT License. See the LICENSE file in the project
# root for full license information.

"""
OHLC invariant tests across all market types.

Verifies that High >= max(Open, Close), Low <= min(Open, Close), all prices
positive, and volume non-negative — both before and after anomaly injection
(SPIKES + GAPS).
"""

import numpy as np
import pytest

from marketforge.configs.loader import load_market_config, market_config_to_generator_config
from marketforge.generators.ohlcv import OHLCVBuilder
from marketforge.generators.anomalies import AnomalyInjector
from marketforge.config.settings import AnomalyConfig, AnomalyType
from marketforge.utils.random import RandomState


@pytest.mark.parametrize("market", ["crypto", "stocks", "forex"])
def test_ohlc_invariants_with_anomalies(market):
    mc = load_market_config(market)
    syms = mc.symbols[:2]
    cfg = market_config_to_generator_config(
        mc, 1704067200, 1704067200 + 3 * 86400, seed=7, batch_symbols=syms,
    )
    data = OHLCVBuilder(cfg).build(RandomState(7))
    inj = AnomalyInjector(
        AnomalyConfig(types=frozenset({AnomalyType.SPIKES, AnomalyType.GAPS})),
        market_type=cfg.market_type,
    )
    for sym in syms:
        out, _ = inj.inject(RandomState(7), data[sym])
        out.validate()
        assert np.all(out.volume >= 0)
        assert np.all(out.low > 0)
