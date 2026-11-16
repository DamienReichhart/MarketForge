# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the GNU Affero General Public License v3.0 or later.
# See the LICENSE file in the project root for full license information.

"""Access to the built-in instrument catalogs, with optional user overrides."""

from __future__ import annotations

from functools import cache

from marketforge.config.catalog.crypto import correlations as crypto_correlations
from marketforge.config.catalog.crypto import instruments as crypto_instruments
from marketforge.config.catalog.forex import correlations as forex_correlations
from marketforge.config.catalog.forex import instruments as forex_instruments
from marketforge.config.catalog.schema import MarketConfig
from marketforge.config.catalog.stocks import correlations as stocks_correlations
from marketforge.config.catalog.stocks import instruments as stocks_instruments
from marketforge.config.overrides import Overrides, apply_overrides, resolve_overrides
from marketforge.domain.markets import MarketType

_BUILTIN = {
    MarketType.CRYPTO: (
        crypto_instruments.INSTRUMENTS,
        crypto_correlations.build_correlation_matrix,
    ),
    MarketType.FOREX: (forex_instruments.INSTRUMENTS, forex_correlations.build_correlation_matrix),
    MarketType.STOCKS: (
        stocks_instruments.INSTRUMENTS,
        stocks_correlations.build_correlation_matrix,
    ),
}


@cache
def load_market_config(market_type: MarketType | str) -> MarketConfig:
    """Built-in catalog of one market (cached; treat as read-only)."""
    market = MarketType(
        str(market_type.value if isinstance(market_type, MarketType) else market_type).lower()
    )
    instruments, build_correlation_matrix = _BUILTIN[market]
    correlation_matrix, symbol_order = build_correlation_matrix()
    return MarketConfig(
        market_type=market,
        instruments=instruments,
        correlation_matrix=correlation_matrix,
        symbol_order=symbol_order,
    )


def load_catalog(overrides: Overrides | None = None) -> dict[MarketType, MarketConfig]:
    """
    Built-in catalog for every market, with optional overrides applied.

    Args:
        overrides: Path to a TOML override file, or the content of its
            ``[instruments]`` table as ``{SYMBOL: {key: value}}`` (see
            :mod:`marketforge.config.overrides`).

    Returns:
        {MarketType: MarketConfig}; cached catalog objects are never mutated.
    """
    catalog = {m: load_market_config(m) for m in MarketType}
    resolved = resolve_overrides(overrides)
    return apply_overrides(catalog, resolved) if resolved else catalog
