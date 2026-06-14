# MarketForge
# Copyright (C) 2026 REICHHART Damien
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

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
