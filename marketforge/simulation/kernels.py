# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

"""
Compiled per-minute recursions.

The recursions (regime spells, GJR-GARCH, AR(1)) are the parts of the
simulation that cannot be vectorised: each step depends on the previous one.
They are all *resumable*: they take the state left by the previous call and
return the state to pass to the next one, so a day-by-day simulation is
bit-identical to a single long run.

The fused kernels (:func:`factor_paths`, :func:`bar_arguments`,
:func:`finish_bars`) replace chains of NumPy expressions that each allocated
a full (minutes x instruments) temporary. They reproduce those expressions
bit for bit, which constrains how they are written (see docs/adr/0007):

- only IEEE-exact operations (``+ - * /``, ``sqrt``, ``abs``, ``min``/``max``),
  in the same order and grouping as the NumPy expression they replace;
- no transcendental function: ``exp`` and ``log`` stay in NumPy, whose SIMD
  implementations differ from libm (and so from Numba) in the last bit;
- no ``fastmath``, so LLVM never contracts ``a * b + c`` into an FMA.
"""

from __future__ import annotations

import sys

import numpy as np

if sys.platform == "emscripten":
    # Numba has no WebAssembly build. In the browser (Pyodide) the kernels run
    # as plain Python, which gives the same bits as the compiled kernels
    # (tests/simulation/test_kernels.py) at a fraction of the speed. Anywhere
    # else a missing Numba must fail, not fall back silently (docs/adr/0015).

    from typing import Any

    def njit(*args: Any, **kwargs: Any) -> Any:
        """Stand-in for ``numba.njit`` that returns the function unchanged."""

        def decorate(function: Any) -> Any:
            function.py_func = function
            return function

        return decorate(args[0]) if args and callable(args[0]) else decorate

else:
    from numba import njit


@njit(cache=True, nogil=True)
def regime_spells(
    uniforms: np.ndarray,
    lengths: np.ndarray,
    next_calm: np.ndarray,
    next_stressed: np.ndarray,
    mean_minutes: np.ndarray,
    stressed: np.ndarray,
    break_hazard: float,
    drift_targets: np.ndarray,
    vol_targets: np.ndarray,
    smoothing: float,
    regime: int,
    remaining: float,
    drift_mult: float,
    vol_mult: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, int, float, float, float]:
    """
    Advance the market's regime, spell by spell, one open minute per draw.

    A semi-Markov chain: a spell of regime r lasts ``mean_minutes[r]`` times
    a mean-1 random length (``lengths``, used at the minute a spell starts),
    then the next regime is drawn from the embedded jump chain, whose
    cumulative rows are ``next_calm`` or, while the macro state is stressed,
    ``next_stressed``. While stressed, a calm spell (trend_up, trend_down,
    range: regimes 0 to 2) also ends early with probability ``break_hazard``
    per minute, so sell-offs start in every market at about the same time.

    The drift and volatility multipliers glide towards the current regime's
    targets with an exponential moving average (``smoothing`` in (0, 1]), so
    regime changes ramp in causally instead of jumping.

    Args:
        uniforms: (n,) draws in [0, 1): an early end, and the next regime.
        lengths: (n,) mean-1 positive spell lengths.
        next_calm, next_stressed: (K, K) cumulative jump rows, zero diagonal.
        mean_minutes: (K,) mean spell length of each regime, in open minutes.
        stressed: (n,) 1 where the macro state is stressed.
        regime, remaining, drift_mult, vol_mult: state after the previous
            step; ``remaining`` open minutes are left in the current spell.

    Returns:
        (regimes, drift_mults, vol_mults, regime, remaining, drift_mult, vol_mult)
    """
    n = uniforms.shape[0]
    k = next_calm.shape[0]
    regimes = np.empty(n, dtype=np.int8)
    drifts = np.empty(n)
    vols = np.empty(n)
    for t in range(n):
        u = uniforms[t]
        rows = next_stressed if stressed[t] else next_calm
        ends = remaining <= 0.0
        if not ends and stressed[t] and regime <= 2 and u < break_hazard:
            ends = True
            u = u / break_hazard  # uniform again, for the next regime
        if ends:
            nxt = k - 1
            for j in range(k):
                if u < rows[regime, j]:
                    nxt = j
                    break
            regime = nxt
            remaining = mean_minutes[regime] * lengths[t]
        remaining -= 1.0
        drift_mult += smoothing * (drift_targets[regime] - drift_mult)
        vol_mult += smoothing * (vol_targets[regime] - vol_mult)
        regimes[t] = regime
        drifts[t] = drift_mult
        vols[t] = vol_mult
    return regimes, drifts, vols, regime, remaining, drift_mult, vol_mult


@njit(cache=True, nogil=True)
def gjr_garch(
    shocks: np.ndarray,
    omega: float,
    alpha: float,
    beta: float,
    gamma: float,
    variance: np.ndarray,
    last_shock: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Unit-level GJR-GARCH(1,1) variance filter, one column per series.

        h_t = omega + (alpha + gamma * 1[e_{t-1} < 0]) * e_{t-1}^2 + beta * h_{t-1}
        e_t = sqrt(h_t) * z_t

    With ``omega = 1 - (alpha + beta + gamma/2)`` the unconditional variance
    is 1, so ``sqrt(h_t)`` is a dimensionless volatility multiplier.

    Args:
        shocks: (n, F) unit-variance shocks z_t.
        variance: (F,) h_{t-1} before the first row.
        last_shock: (F,) e_{t-1} before the first row.

    Returns:
        (h, variance, last_shock) where h is (n, F) and the others are the
        state after the last row.
    """
    n, f = shocks.shape
    h = np.empty((n, f))
    variance = variance.copy()
    last_shock = last_shock.copy()
    for t in range(n):
        for i in range(f):
            e = last_shock[i]
            lev = gamma if e < 0.0 else 0.0
            v = omega + (alpha + lev) * e * e + beta * variance[i]
            h[t, i] = v
            variance[i] = v
            last_shock[i] = np.sqrt(v) * shocks[t, i]
    return h, variance, last_shock


@njit(cache=True, nogil=True)
def ar1(drivers: np.ndarray, phi: float, state: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """
    Column-wise AR(1): y_t = phi * y_{t-1} + u_t.

    Args:
        drivers: (n, I) innovations u_t.
        state: (I,) y_{t-1} before the first row.

    Returns:
        (y, state) with y of shape (n, I).
    """
    n, m = drivers.shape
    y = np.empty((n, m))
    state = state.copy()
    for t in range(n):
        for i in range(m):
            v = phi * state[i] + drivers[t, i]
            y[t, i] = v
            state[i] = v
    return y, state


@njit(cache=True, nogil=True)
def factor_paths(
    h: np.ndarray,
    vol_mult: np.ndarray,
    drift_mult: np.ndarray,
    season: np.ndarray,
    z: np.ndarray,
    sigma: np.ndarray,
    mu: np.ndarray,
    trend: np.ndarray,
    gap_rows: np.ndarray,
    gap: np.ndarray,
    log_price: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Per-minute volatility, returns and log price path of each factor.

    Exactly reproduces::

        level     = sqrt(h) * vol_mult[:, None]
        sigma_f   = sigma * level * season[:, None]
        returns   = mu + drift_mult @ trend + sigma_f * z      (trends added in order)
        log_close = log_price + cumsum(gap + returns, axis=0)
        log_open  = vstack([log_price, log_close[:-1]]) + gap

    where ``gap`` is zero except on ``gap_rows``.

    Args:
        h: (n, F) GJR-GARCH variance multipliers.
        vol_mult, season: (n,) market-wide multipliers.
        drift_mult: (n, K) the strength of each of K trends (the market's
            regime, and for index CFDs the stock market's), in units of ``trend``.
        z: (n, F) unit-variance shocks.
        sigma, mu: (F,) per-minute volatility and drift.
        trend: (K, F) per-minute return of each factor per unit of each trend.
        gap_rows: (k,) rows that open after a closure (strictly increasing).
        gap: (k, F) log gap applied at those rows.
        log_price: (F,) log close before the first row.

    Returns:
        (sigma_f, returns, log_open, log_close), each (n, F).
    """
    n, f = z.shape
    k = trend.shape[0]
    sigma_f = np.empty((n, f))
    returns = np.empty((n, f))
    log_open = np.empty((n, f))
    log_close = np.empty((n, f))
    cum = np.zeros(f)
    prev = log_price.copy()
    g_idx = 0
    for t in range(n):
        at_gap = g_idx < gap_rows.shape[0] and gap_rows[g_idx] == t
        level_t = vol_mult[t]
        for i in range(f):
            s = sigma[i] * (np.sqrt(h[t, i]) * level_t) * season[t]
            r = mu[i]
            for j in range(k):
                r += trend[j, i] * drift_mult[t, j]
            r += s * z[t, i]
            g = gap[g_idx, i] if at_gap else 0.0
            x = g + r
            c = x if t == 0 else cum[i] + x
            cum[i] = c
            close = log_price[i] + c
            log_open[t, i] = prev[i] + g
            log_close[t, i] = close
            prev[i] = close
            sigma_f[t, i] = s
            returns[t, i] = r
        if at_gap:
            g_idx += 1
    return sigma_f, returns, log_open, log_close


@njit(cache=True, nogil=True)
def pull_to_pegs(
    log_open: np.ndarray,
    log_close: np.ndarray,
    returns: np.ndarray,
    start: np.ndarray,
    held: np.ndarray,
    vectors: np.ndarray,
    centres: np.ndarray,
    half_widths: np.ndarray,
    pulls: np.ndarray,
) -> None:
    """
    Hold pegged pairs near their centres, in place.

    Each peg is a pair whose log price is ``vectors[k] @ log_close[t]``; it is
    moved through one factor, ``held[k]`` (the pegged currency's anchor),
    whose path shifts by ``-pulls[k] * (level - centre) / vectors[k, held]``
    per minute and by whatever keeps the level inside ``centre +- half_width``,
    at each open (after a gap) and each close.
    A shift carries to every later minute of that factor, as a price would.
    ``start`` is each factor's log close before the first row.
    """
    n, f = log_close.shape
    for k in range(held.shape[0]):
        p = held[k]
        weight = vectors[k, p]
        shift = 0.0
        prev = 0.0
        for i in range(f):
            prev += vectors[k, i] * start[i]
        for t in range(n):
            pull = -pulls[k] * (prev - centres[k]) / weight
            log_open[t, p] += shift
            # The open too stays in the band: the peg holds over a closure,
            # so a reopening gap cannot carry the pair out of it.
            opened = 0.0
            for i in range(f):
                opened += vectors[k, i] * log_open[t, i]
            over = 0.0
            if opened > centres[k] + half_widths[k]:
                over = opened - (centres[k] + half_widths[k])
            elif opened < centres[k] - half_widths[k]:
                over = opened - (centres[k] - half_widths[k])
            if over != 0.0:
                shift -= over / weight
                log_open[t, p] -= over / weight
            shift += pull
            close = log_close[t, p] + shift
            level = 0.0
            for i in range(f):
                level += vectors[k, i] * (close if i == p else log_close[t, i])
            excess = 0.0
            if level > centres[k] + half_widths[k]:
                excess = level - (centres[k] + half_widths[k])
            elif level < centres[k] - half_widths[k]:
                excess = level - (centres[k] - half_widths[k])
            if excess != 0.0:
                shift -= excess / weight
                close -= excess / weight
                level -= excess
            log_close[t, p] = close
            returns[t, p] = close - log_open[t, p]
            prev = level


@njit(cache=True, nogil=True)
def project_signed(x: np.ndarray, index: np.ndarray, sign: np.ndarray) -> np.ndarray:
    """
    Instruments as signed sums of at most two factor columns.

    ``out[:, j] = sign[j, 0] * x[:, index[j, 0]] + sign[j, 1] * x[:, index[j, 1]]``,
    where an unused second term has ``index == -1``. With weights of +-1 and at
    most two non-zero terms, every summation order rounds to the same double,
    so this equals ``x @ weights`` computed by any BLAS.
    """
    n = x.shape[0]
    m = index.shape[0]
    out = np.empty((n, m))
    for t in range(n):
        for j in range(m):
            v = sign[j, 0] * x[t, index[j, 0]]
            if index[j, 1] >= 0:
                v = v + sign[j, 1] * x[t, index[j, 1]]
            out[t, j] = v
    return out


@njit(cache=True, nogil=True)
def bar_arguments(
    log_open: np.ndarray,
    log_close: np.ndarray,
    body: np.ndarray,
    sigma_i: np.ndarray,
    intrabar_ratio: float,
    body_share: float,
    log_u_high: np.ndarray,
    log_u_low: np.ndarray,
    sigma_ref: np.ndarray,
    season: np.ndarray,
    exp_args: np.ndarray,
    level: np.ndarray,
) -> None:
    """
    Fill the arguments of the per-bar transcendentals, in place.

    ``exp_args`` (4, n, I) receives log open, log close and the log of the
    Brownian-bridge high and low (:func:`bridge_extremes` with a bar variance
    ``(sigma_i * intrabar_ratio)^2 + body_share * body^2``: a minute that moved
    far was turbulent, so its path wandered and it keeps wicks); ``level``
    (n, I) receives the
    turbulence ``sigma_i / (sigma_ref * season)`` whose log drives volume.
    The caller applies ``np.exp`` / ``np.log`` to them in place.
    """
    n, m = body.shape
    for t in range(n):
        for j in range(m):
            b = body[t, j]
            bar_std = sigma_i[t, j] * intrabar_ratio
            b2 = b * b
            s2 = bar_std * bar_std + body_share * b2
            hi = 0.5 * (b + np.sqrt(b2 - 2.0 * s2 * log_u_high[t, j]))
            lo = 0.5 * (b - np.sqrt(b2 - 2.0 * s2 * log_u_low[t, j]))
            lo_t = log_open[t, j]
            exp_args[0, t, j] = lo_t
            exp_args[1, t, j] = log_close[t, j]
            exp_args[2, t, j] = lo_t + hi
            exp_args[3, t, j] = lo_t + lo
            level[t, j] = sigma_i[t, j] / (sigma_ref[j] * season[t])


@njit(cache=True, nogil=True)
def finish_bars(
    prices: np.ndarray,
    body: np.ndarray,
    sigma_i: np.ndarray,
    log_level: np.ndarray,
    log_season: np.ndarray,
    noise: np.ndarray,
    e_volume: np.ndarray,
    lam: float,
    kappa: float,
    phi: float,
    z_clip: float,
    mean_abs_z: float,
    log_correction: np.ndarray,
    memory: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Close high/low over the body and run the log-volume AR(1).

    ``prices`` (4, n, I) holds exp() of the :func:`bar_arguments` output:
    open, close, bridge high, bridge low. Exactly reproduces::

        high    = maximum(bridge_high, maximum(open, close))
        low     = minimum(bridge_low, minimum(open, close))
        zabs    = clip(abs(body) / sigma_i, 0, z_clip) - mean_abs_z
        drivers = lam * zabs + kappa * log_level + log_season[:, None] + noise * e_volume
        y, memory = ar1(drivers, phi, memory)
        returned volume argument = y - log_correction

    Returns:
        (high, low, volume_arg) and ``memory`` is updated in place.
    """
    n, m = body.shape
    high = np.empty((n, m))
    low = np.empty((n, m))
    vol_arg = np.empty((n, m))
    for t in range(n):
        for j in range(m):
            o = prices[0, t, j]
            c = prices[1, t, j]
            high[t, j] = max(prices[2, t, j], max(o, c))
            low[t, j] = min(prices[3, t, j], min(o, c))
            za = min(max(abs(body[t, j]) / sigma_i[t, j], 0.0), z_clip) - mean_abs_z
            d = lam * za + kappa * log_level[t, j] + log_season[t] + noise[j] * e_volume[t, j]
            y = phi * memory[j] + d
            memory[j] = y
            vol_arg[t, j] = y - log_correction[j]
    return high, low, vol_arg


def bridge_extremes(
    log_body: np.ndarray,
    bar_std: np.ndarray,
    u_high: np.ndarray,
    u_low: np.ndarray,
    body_share: float = 0.0,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Exact maximum and minimum of a Brownian bridge, sampled by inversion.

    For a Brownian path over one bar with standard deviation ``s`` that ends
    at ``b`` (the log close/open), the running maximum M satisfies
    ``P(M > m) = exp(-2 m (m - b) / s^2)`` for ``m >= max(0, b)``; the minimum
    is symmetric. Inverting with a uniform draw gives the continuous-path
    extreme with two numbers per bar instead of a discretised path.

    Args:
        log_body: log(close / open) per bar.
        bar_std: per-bar standard deviation of the log price.
        u_high, u_low: uniforms in (0, 1].
        body_share: share of ``log_body**2`` added to the bridge variance.

    Returns:
        (log_high, log_low) relative to the log open.
    """
    b2 = log_body * log_body
    s2 = bar_std * bar_std + body_share * b2
    high = 0.5 * (log_body + np.sqrt(b2 - 2.0 * s2 * np.log(u_high)))
    low = 0.5 * (log_body - np.sqrt(b2 - 2.0 * s2 * np.log(u_low)))
    return high, low
