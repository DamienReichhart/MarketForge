# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

"""Regime multipliers calibrated to reshape drift and volatility without changing their level."""

from __future__ import annotations

from functools import lru_cache

import numpy as np

from marketforge.simulation.kernels import regime_chain

# EMA weight per minute for regime multipliers (~15-minute ramp).
REGIME_SMOOTHING = 1.0 / 15.0


def normalised_regime_targets(
    cumulative: np.ndarray, drift: np.ndarray, vol: np.ndarray, initial: int
) -> tuple[np.ndarray, np.ndarray]:
    """
    Rescale regime multipliers so that, over the long run (smoothing included),
    the mean drift multiplier is 1 and the mean squared volatility multiplier
    is 1. Without this the configured annual drift and volatility were not
    what the simulation produced (e.g. stocks drifted down on average).

    The calibration runs a multi-million-step chain (~0.15 s and up to ~200 MB
    of temporaries), so its result is cached per distinct set of parameters.
    """
    key = (
        cumulative.shape,
        np.ascontiguousarray(cumulative, dtype=float).tobytes(),
        np.ascontiguousarray(drift, dtype=float).tobytes(),
        np.ascontiguousarray(vol, dtype=float).tobytes(),
        int(initial),
    )
    d, v = _cached_regime_targets(key)
    return d.copy(), v.copy()


@lru_cache(maxsize=32)
def _cached_regime_targets(
    key: tuple[tuple[int, ...], bytes, bytes, bytes, int],
) -> tuple[np.ndarray, np.ndarray]:
    shape, cum_bytes, drift_bytes, vol_bytes, initial = key
    cumulative = np.frombuffer(cum_bytes).reshape(shape).copy()
    drift = np.frombuffer(drift_bytes).copy()
    vol = np.frombuffer(vol_bytes).copy()
    # Simulate long enough to visit every regime many times (>= ~2000 mean
    # durations of the stickiest one), with a fixed seed: deterministic.
    stay = np.diff(
        np.concatenate([np.zeros((cumulative.shape[0], 1)), cumulative], axis=1), axis=1
    ).diagonal()
    longest = float(np.max(1.0 / np.maximum(1.0 - stay, 1e-9)))
    n = int(min(20_000_000, max(400_000, 2000 * longest)))
    u = np.random.Generator(np.random.PCG64(20260613)).random(n)
    _, d, v, *_ = regime_chain(
        u,
        cumulative,
        drift,
        vol,
        REGIME_SMOOTHING,
        initial,
        float(drift[initial]),
        float(vol[initial]),
    )
    burn = min(n // 10, int(20 * longest))
    vol_scale = 1.0 / np.sqrt(np.mean(v[burn:] ** 2))
    drift_shift = 1.0 - float(np.mean(d[burn:]))
    targets = (drift + drift_shift, vol * vol_scale)
    for a in targets:
        a.setflags(write=False)  # shared by every simulator: never mutated
    return targets
