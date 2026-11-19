# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

"""The instruments MarketForge can generate, as a table."""

from __future__ import annotations

import pandas as pd

from marketforge.api.parsing import Names, parse_markets
from marketforge.config.loader import load_catalog
from marketforge.config.overrides import Overrides
from marketforge.domain.markets import MarketType
from marketforge.simulation.spec import build_market_spec


def instruments(
    markets: Names | None = None, *, overrides: Overrides | None = None
) -> pd.DataFrame:
    """
    The catalog as a DataFrame indexed by symbol.

    Args:
        markets: Restrict to these markets (default: all).
        overrides: Override file or mapping to apply first, as for :func:`generate`.

    Returns:
        One row per instrument with the columns ``market``, ``start_price``,
        ``volatility`` and ``drift`` (annualised), ``volume_base`` (mean volume
        per open minute) and ``derived`` (True for forex crosses, whose candles
        are derived from anchor pairs rather than simulated directly).
    """
    wanted = parse_markets(markets) or list(MarketType)
    rows = []
    for market, config in load_catalog(overrides).items():
        if market not in wanted:
            continue
        anchors = set(build_market_spec(config).structure.factors)
        for symbol in config.symbols:
            params = config.get_instrument(symbol)
            rows.append(
                {
                    "symbol": symbol,
                    "market": market.value,
                    "start_price": params.start_price,
                    "volatility": params.volatility,
                    "drift": params.drift,
                    "volume_base": params.volume_base,
                    "derived": symbol not in anchors,
                }
            )
    return pd.DataFrame(rows).set_index("symbol")
