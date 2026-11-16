# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the MIT License. See the LICENSE file in the project
# root for full license information.

"""Optional, deliberately unrealistic events layered on simulated candles."""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from marketforge.config.model_params import AnomalyConfig
from marketforge.domain.anomalies import AnomalyType
from marketforge.domain.bars import Bars
from marketforge.domain.time import MINUTES_PER_DAY


def inject_anomalies(
    cfg: AnomalyConfig,
    rng: np.random.Generator,
    res: Bars,
    *,
    n_market_instruments: int,
    selected: np.ndarray,
    select: Callable[[np.ndarray], np.ndarray],
) -> None:
    """
    Add the configured anomalies to one day of m1 candles, in place.

    Draws cover the whole market in a fixed order (reproducibility contract);
    ``select`` keeps the simulated minutes and the selected instruments of a
    market-wide (minute-of-day, instrument) draw, and ``selected`` holds the
    market indices of those instruments.
    """
    n_i = n_market_instruments
    u_spike = rng.random((MINUTES_PER_DAY, n_i))
    u_dir = rng.random((MINUTES_PER_DAY, n_i))
    u_mag = rng.random((MINUTES_PER_DAY, n_i))
    u_crash = np.asarray(rng.random(n_i))[selected]
    u_start = np.asarray(rng.random(n_i))[selected]

    if AnomalyType.SPIKES in cfg.types:
        lo_m, hi_m = cfg.spike_magnitude_range
        hit = select(u_spike) < cfg.spike_probability
        if hit.any():
            mag = lo_m + (hi_m - lo_m) * select(u_mag)
            mid = 0.5 * (res.open + res.close)
            up = hit & (select(u_dir) < 0.5)
            down = hit & ~up
            res.high = np.where(up, res.high + mid * mag, res.high)
            res.low = np.where(down, np.maximum(res.low - mid * mag, 0.5 * mid), res.low)
            res.volume = np.where(hit, res.volume * 2.0, res.volume)

    if AnomalyType.FLASH_CRASH in cfg.types:
        length = int(cfg.flash_crash_recovery_candles)
        n = len(res)
        if n > length + 1:
            envelope = flash_crash_envelope(length, cfg.flash_crash_magnitude)
            for i in np.nonzero(u_crash < cfg.flash_crash_probability)[0]:
                s = int(u_start[i] * (n - length - 1))
                _apply_envelope(res, int(i), s, envelope)


def flash_crash_envelope(length: int, magnitude: float) -> np.ndarray:
    """Price multiplier at each candle close: sharp drop, short floor, recovery to 1."""
    drop = max(1, length // 3)
    floor = max(1, length // 6)
    rec = max(1, length - drop - floor)
    p = np.arange(1, drop + 1) / drop
    fall = magnitude * (1 - np.exp(-3 * p)) / (1 - np.exp(-3))
    rise = magnitude * (1 - np.arange(1, rec + 1) / rec)
    depth = np.concatenate([fall, np.full(floor, magnitude), rise])
    return np.asarray(1.0 - depth)


def _apply_envelope(res: Bars, i: int, start: int, env: np.ndarray) -> None:
    """Scale candles [start, start+len) of instrument i so prices dip and recover."""
    k = env.size
    sl = slice(start, start + k)
    e_close = env
    e_open = np.concatenate(([1.0], env[:-1]))
    o = res.open[sl, i] * e_open
    c = res.close[sl, i] * e_close
    h = res.high[sl, i] * np.maximum(e_open, e_close)
    lw = res.low[sl, i] * np.minimum(e_open, e_close)
    res.open[sl, i] = o
    res.close[sl, i] = c
    res.high[sl, i] = np.maximum(h, np.maximum(o, c))
    res.low[sl, i] = np.minimum(lw, np.minimum(o, c))
    res.volume[sl, i] *= 1.0 + 2.0 * (1.0 - env) / max(1e-12, 1.0 - env.min())
