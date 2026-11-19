# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

"""
What links the markets: the macro state and the global shock (ADR 0016).

Both come from random streams of their own, keyed by the seed and the UTC
day but not by the market, so every market simulator computes the same
values on its own: markets still run in parallel, and a market's candles
still do not depend on which other markets are generated.

- The **macro state** is a world-wide hidden state, calm or stressed, that
  changes at UTC midnight. It is a two-state Markov chain run over eras of
  :data:`ERA_DAYS` days, each era starting from the chain's stationary
  distribution, so the state of any day is computed from one era at most.
- The **global shock** is one standard normal per UTC minute. Each market
  swaps part of its main factor's shock for it (:func:`global_mixing`).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from marketforge.domain.time import MINUTES_PER_DAY

# Stream identifier of the world-wide draws: 0, next to the markets' 1, 2, 3.
GLOBAL_STREAM = 0
ERA_DAYS = 4096
# Mean spell lengths of the macro state, in days: calm for most of a year,
# stressed for about a month (the world's sell-offs: 2008, 2020, 2022).
CALM_DAYS = 240.0
STRESSED_DAYS = 30.0
CALM, STRESSED = 0, 1
# A stressed spell is a world bear market: each market's global direction
# falls by this many of the spell's own standard deviations, on average.
# Calm days drift up by the share that keeps the long-run drift at zero.
STRESSED_TREND = -1.0


def macro_trends(open_minutes_per_day: int) -> tuple[float, float]:
    """Per-minute trend of the global direction (in units of its per-minute
    volatility) on calm and on stressed days."""
    spell = STRESSED_DAYS * open_minutes_per_day
    stressed = STRESSED_TREND / np.sqrt(spell)
    calm = -stressed * STRESSED_DAYS / CALM_DAYS
    return float(calm), float(stressed)


@dataclass(frozen=True)
class GlobalMixing:
    """How a market's shocks load on the global shock.

    ``weights`` (F,) turn a minute of factor shocks into the market's own
    global-direction shock M = z . weights, of unit variance; ``covariance``
    (F,) is each factor's covariance with M. Replacing M by
    ``c * w + sqrt(1 - c^2) * M`` (w the global shock) keeps the market's
    correlation matrix exactly and correlates it with every other market.
    """

    weights: np.ndarray
    covariance: np.ndarray
    coupling: tuple[float, float]  # c when calm, when stressed

    def apply(self, z: np.ndarray, w: np.ndarray, stressed: np.ndarray) -> np.ndarray:
        """Shocks ``z`` (n, F) with their global-direction part tied to ``w`` (n,)."""
        own = np.sum(z * self.weights, axis=1)  # row by row: no BLAS, any row count
        c = np.where(stressed, self.coupling[STRESSED], self.coupling[CALM])
        mixed = c * w + np.sqrt(1.0 - c * c) * own
        return np.asarray(z + (mixed - own)[:, None] * self.covariance)


def global_mixing(
    correlation: np.ndarray, direction: np.ndarray, coupling: tuple[float, float]
) -> GlobalMixing:
    """The mixing that ties a market's ``direction`` (portfolio weights on its factors) to the global shock."""
    g = np.asarray(direction, dtype=float)
    if not np.any(g):  # nothing in the market moves with the world
        return GlobalMixing(np.zeros_like(g), np.zeros_like(g), (0.0, 0.0))
    # The shock of a portfolio with these weights, scaled to unit variance:
    # well defined whatever the correlation matrix, where solving R a = g
    # blew up along directions the catalog gives no variance (forex).
    weights = g / float(np.sqrt(g @ correlation @ g))
    return GlobalMixing(weights, correlation @ weights, coupling)


@lru_cache(maxsize=8)
def _era(seed: int, era: int) -> np.ndarray:
    rng = np.random.Generator(
        np.random.PCG64(np.random.SeedSequence([seed, GLOBAL_STREAM, era, 0]))
    )
    leave = (1.0 / CALM_DAYS, 1.0 / STRESSED_DAYS)
    u = rng.random(ERA_DAYS + 1)
    states = np.empty(ERA_DAYS, dtype=np.int8)
    state = STRESSED if u[0] < leave[0] / (leave[0] + leave[1]) else CALM  # stationary start
    for day in range(ERA_DAYS):
        states[day] = state
        if u[day + 1] < leave[state]:
            state = 1 - state
    states.setflags(write=False)
    return states


def macro_state(seed: int, day: int) -> int:
    """The macro state (:data:`CALM` or :data:`STRESSED`) of UTC day ``day``."""
    era, offset = divmod(int(day), ERA_DAYS)
    return int(_era(int(seed), era)[offset])


@lru_cache(maxsize=16)
def _global_day(seed: int, day: int, kind: int) -> np.ndarray:
    seq = np.random.SeedSequence([seed, GLOBAL_STREAM, day, kind])
    shocks = np.random.Generator(np.random.PCG64(seq)).standard_normal(MINUTES_PER_DAY)
    shocks.setflags(write=False)
    return shocks


def global_shocks(seed: int, day: int) -> np.ndarray:
    """The global shock of every minute of UTC day ``day`` (read-only)."""
    return _global_day(int(seed), int(day), 1)


def global_stress_shocks(seed: int, day: int) -> np.ndarray:
    """The common shock of stressed regimes, world-wide (read-only).

    Independent of :func:`global_shocks`, which every shock already holds:
    reusing it would count it twice and inflate the variance of stressed minutes.
    """
    return _global_day(int(seed), int(day), 2)


def closure_shock(seed: int, first_minute: int, last_minute: int) -> float:
    """The global shocks of minutes ``[first_minute, last_minute]`` (epoch minutes) as one unit normal.

    What the world did while a market was closed reaches it in its gap.
    """
    total = 0.0
    for day in range(first_minute // MINUTES_PER_DAY, last_minute // MINUTES_PER_DAY + 1):
        lo = max(first_minute - day * MINUTES_PER_DAY, 0)
        hi = min(last_minute - day * MINUTES_PER_DAY, MINUTES_PER_DAY - 1)
        total += float(np.sum(global_shocks(seed, day)[lo : hi + 1]))
    return float(total / np.sqrt(last_minute - first_minute + 1))
