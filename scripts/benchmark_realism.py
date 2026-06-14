# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the MIT License. See the LICENSE file in the project
# root for full license information.

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
