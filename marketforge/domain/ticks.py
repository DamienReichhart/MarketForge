# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

"""The tick size: the price step an instrument is quoted in."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from marketforge.domain.markets import MarketType

# Files keep 8 decimals: no tick may be finer.
FINEST_DECIMALS = 8
# Reg NMS rule 612: US stocks quote in cents from $1, in hundredths of a cent below.
_STOCK_DECIMALS = 2
_SUB_PENNY_DECIMALS = 4


def default_tick(market: MarketType, start_price: float) -> float:
    """The tick of an instrument whose catalog entry names none.

    Stocks quote in cents. Currencies, metals, CFDs and coins quote about five
    significant digits: 0.00001 on EURUSD, 0.001 on USDJPY, 0.01 on XAUUSD,
    0.1 on BTCUSD, the steps their venues use.
    """
    if MarketType(market) == MarketType.STOCKS:
        return 10.0**-_STOCK_DECIMALS
    exponent = math.floor(math.log10(start_price)) - 5
    return 10.0 ** max(exponent, -FINEST_DECIMALS)


def decimals_of(tick: float) -> int:
    """The decimals of a power-of-ten tick (0.01 -> 2, 10 -> -1)."""
    decimals = -math.log10(tick)
    if abs(decimals - round(decimals)) > 1e-9:
        raise ValueError(f"tick_size must be a power of ten (0.01, 0.5 is not), got {tick}")
    return round(decimals)


@dataclass(frozen=True)
class TickGrid:
    """The ticks of a market's instruments, to put prices on them.

    ``decimals`` holds each instrument's tick as decimals (2 for 0.01). With
    ``sub_penny`` (US stocks), prices below 1 quote two more decimals.
    """

    decimals: np.ndarray  # (I,) int
    sub_penny: bool = False

    @property
    def _scale(self) -> np.ndarray:
        """10 ** decimals, once (the grid of every price when there is no sub-penny rule)."""
        cached = self.__dict__.get("_cached_scale")
        if cached is None:
            cached = 10.0 ** np.asarray(self.decimals, dtype=float)
            object.__setattr__(self, "_cached_scale", cached)
        return np.asarray(cached)

    def grid(self, prices: np.ndarray) -> np.ndarray:
        """Decimals of the tick at each price, (k, I) like ``prices``."""
        decimals = np.broadcast_to(self.decimals, prices.shape)
        if self.sub_penny:
            decimals = np.where(
                prices < 1.0, decimals + _SUB_PENNY_DECIMALS - _STOCK_DECIMALS, decimals
            )
        return np.asarray(decimals)

    def round(self, prices: np.ndarray) -> np.ndarray:
        """``prices`` on the nearest tick."""
        return self._apply(prices, np.rint)

    def floor(self, prices: np.ndarray) -> np.ndarray:
        """``prices`` on the tick at or below them (a bid)."""
        return self._apply(prices, np.floor)

    def ceil(self, prices: np.ndarray) -> np.ndarray:
        """``prices`` on the tick at or above them (an ask)."""
        return self._apply(prices, np.ceil)

    def _apply(self, prices: np.ndarray, how: np.ufunc) -> np.ndarray:
        prices = np.asarray(prices, dtype=float)
        # Above $1 a stock's grid is its plain tick: skip the per-price rule.
        plain = not self.sub_penny or bool(np.all(prices >= 1.0))
        scale = self._scale if plain else 10.0 ** self.grid(prices)
        out = prices * scale
        if how is not np.rint:
            # A millionth of a tick absorbs the binary error of prices on the grid.
            out += -1e-6 if how is np.ceil else 1e-6
        how(out, out=out)
        out /= scale
        return np.asarray(out)

    def take(self, columns: np.ndarray) -> TickGrid:
        """The grid of some instruments, by column."""
        return TickGrid(self.decimals[columns], self.sub_penny)
