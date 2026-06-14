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
Print stylized-fact metrics for generated data, per market - the v2 realism proof.

Usage: python scripts/benchmark_realism.py
"""
from __future__ import annotations

from marketforge.configs.loader import load_market_config, market_config_to_generator_config
from marketforge.generators.ohlcv import OHLCVBuilder
from marketforge.utils.random import RandomState
from marketforge.validation.report import validate_ohlcv
from marketforge.config.settings import MarketType

TEN_DAYS = 10 * 86400


def main() -> None:
    for market in ("crypto", "stocks", "forex"):
        mc = load_market_config(market)
        syms = mc.symbols[:1]
        cfg = market_config_to_generator_config(
            mc, 1704067200, 1704067200 + TEN_DAYS, seed=2024, batch_symbols=syms,
        )
        data = OHLCVBuilder(cfg).build(RandomState(2024))
        d = data[syms[0]]
        report = validate_ohlcv(d.open, d.high, d.low, d.close, MarketType(market))
        print(report.summary())
        print()


if __name__ == "__main__":
    main()
