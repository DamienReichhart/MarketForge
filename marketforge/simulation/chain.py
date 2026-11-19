# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

"""
A market's regime chain, drawn from a random stream of its own (ADR 0016).

The chain's draws are keyed by the seed, the market and the UTC day alone,
not by the market's other draws, so another market's simulator can run the
same chain and get the same path: the forex market runs the stock market's
chain, so that index CFDs (SPXUSD...) follow the stock market's bull and bear
spells and not only its shocks.
"""

from __future__ import annotations

from typing import NamedTuple

import numpy as np

from marketforge.config.model_params import RegimeParams
from marketforge.simulation.kernels import regime_spells
from marketforge.simulation.regimes import REGIME_SMOOTHING, normalised_spell_targets

# Stream identifier of the regime draws within a market's day (0 is the
# market's shocks, 1 anomalies, 2 spreads, 3 earnings, 4 noise, 5 slow volatility).
REGIME_STREAM = 6
_MINUTES_PER_DAY = 1440


class ChainState(NamedTuple):
    """Where a regime chain stands between two days."""

    regime: int
    spell_left: float  # open minutes left in the current spell
    drift_mult: float
    vol_mult: float


class RegimeChain:
    """The regime path of one market: the same for every simulator that runs it."""

    def __init__(
        self, params: RegimeParams, market_stream: int, open_minutes_per_day: int, seed: int
    ) -> None:
        self._seed = int(seed)
        self._stream = int(market_stream)
        self._next_calm = np.asarray(params.jump_rows(False))
        self._next_stressed = np.asarray(params.jump_rows(True))
        self._spell_minutes = np.asarray(params.mean_minutes())
        self._shape = float(params.spell_shape)
        self._break_hazard = 1.0 / float(params.minutes_per_step)
        self.drift_targets, self.vol_targets = normalised_spell_targets(
            params, open_minutes_per_day
        )
        r0 = params.get_regime_index(params.initial_regime)
        self.initial = ChainState(
            r0,
            float(self._spell_minutes[r0]),
            float(self.drift_targets[r0]),
            float(self.vol_targets[r0]),
        )

    def advance(
        self, day: int, rows: np.ndarray, stressed: bool, state: ChainState
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, ChainState]:
        """The regime, trend and volatility multipliers of the open minutes ``rows``
        (minutes of UTC day ``day``), and the state after them."""
        seq = np.random.SeedSequence([self._seed, self._stream, int(day), REGIME_STREAM])
        rng = np.random.Generator(np.random.PCG64(seq))
        uniforms = rng.random(_MINUTES_PER_DAY)  # fixed shapes: one per minute of the day
        lengths = rng.gamma(self._shape, 1.0 / self._shape, _MINUTES_PER_DAY)
        regimes, drift, vol, *after = regime_spells(
            uniforms[rows],
            lengths[rows],
            self._next_calm,
            self._next_stressed,
            self._spell_minutes,
            np.full(rows.size, stressed, dtype=np.int8),
            self._break_hazard,
            self.drift_targets,
            self.vol_targets,
            REGIME_SMOOTHING,
            *state,
        )
        return regimes, drift, vol, ChainState(int(after[0]), *map(float, after[1:]))
