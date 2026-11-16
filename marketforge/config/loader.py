# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the MIT License. See the LICENSE file in the project
# root for full license information.

"""Access to the built-in instrument catalogs, with optional user overrides."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional, Union

from marketforge.config.catalog.base import MarketConfig
from marketforge.config.settings import MarketType


@lru_cache(maxsize=None)
def load_market_config(market_type: Union[MarketType, str]) -> MarketConfig:
    """Built-in catalog of one market (cached; treat as read-only)."""
    market = MarketType(
        str(market_type.value if isinstance(market_type, MarketType) else market_type).lower()
    )
    if market == MarketType.FOREX:
        from marketforge.config.catalog.forex import get_forex_config

        return get_forex_config()
    if market == MarketType.CRYPTO:
        from marketforge.config.catalog.crypto import get_crypto_config

        return get_crypto_config()
    from marketforge.config.catalog.stocks import get_stocks_config

    return get_stocks_config()


def load_catalog(
    overrides: Optional[Union[str, "os.PathLike[str]"]] = None,
) -> dict[MarketType, MarketConfig]:
    """
    Built-in catalog for every market, with an optional TOML override file applied.

    Args:
        overrides: Path to an override file (see :mod:`marketforge.config.overrides`).

    Returns:
        {MarketType: MarketConfig}; cached catalog objects are never mutated.
    """
    catalog = {m: load_market_config(m) for m in MarketType}
    if overrides is None:
        return catalog
    from marketforge.config.overrides import apply_overrides, read_overrides

    return apply_overrides(catalog, read_overrides(overrides))
