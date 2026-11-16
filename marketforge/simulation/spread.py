# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the MIT License. See the LICENSE file in the project
# root for full license information.

"""Quoted bid-ask spread around the mid price (see docs/adr/0008)."""

from __future__ import annotations

import numpy as np

from marketforge.calendars.trading_calendar import TradingCalendar
from marketforge.config.model_params import SpreadParams
from marketforge.domain.time import MINUTES_PER_DAY, SECONDS_PER_DAY

# A reopening widens spreads for well under this many minutes.
_REOPEN_WINDOW = 240


def minutes_since_reopen(calendar: TradingCalendar, day: int) -> np.ndarray:
    """
    For each minute of a UTC day, how many minutes the market has been open
    since it was last closed (1 for the first minute of a session), counted
    over the last few hours only. Meaningful where the market is open.
    """
    grid = day * SECONDS_PER_DAY + 60 * np.arange(-_REOPEN_WINDOW, MINUTES_PER_DAY, dtype=np.int64)
    index = np.arange(grid.size)
    last_closed = np.maximum.accumulate(np.where(calendar.open_mask(grid), -1, index))
    return np.asarray((index - last_closed)[_REOPEN_WINDOW:], dtype=float)


def quoted_spread(
    params: SpreadParams,
    base: np.ndarray,
    mid: np.ndarray,
    log_turbulence: np.ndarray,
    season: np.ndarray,
    since_reopen: np.ndarray,
    noise: np.ndarray,
) -> np.ndarray:
    """
    Spread of each minute and instrument, in price units.

    Args:
        base: (I,) typical spread of each instrument as a fraction of its price.
        mid: (n, I) mid price the spread is quoted around.
        log_turbulence: (n, I) log of the volatility level relative to normal.
        season: (n,) intraday seasonality multiplier.
        since_reopen: (n,) open minutes since the market last reopened.
        noise: (n, I) standard normal draws.
    """
    reopening = 1.0 + params.reopen_widening * np.exp(-(since_reopen - 1.0) / params.reopen_minutes)
    by_minute = reopening / season**params.liquidity_exponent
    relative = base * np.exp(
        params.turbulence_exponent * log_turbulence + params.noise * noise - 0.5 * params.noise**2
    )
    return np.asarray(np.maximum(mid * relative * by_minute[:, None], params.tick))
