# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the MIT License. See the LICENSE file in the project
# root for full license information.

"""
Whole-market simulation engine.

A :class:`MarketSimulator` simulates every instrument of one market jointly,
walking time one UTC day at a time and carrying its state (prices, GARCH
variance, regime, volume memory) from day to day (see docs/adr/0001).

Per open minute t and simulated factor f:

    z_t        correlated, unit-variance Student-t shocks (shared mixing => tail dependence)
    h_t        GJR-GARCH(1,1) variance multiplier (unconditional mean 1)
    g_t, d_t   market-wide regime volatility / drift multipliers
    s_t        intraday seasonality (mean square 1 over a year)
    sigma_t  = sigma_f * sqrt(h_t) * g_t * s_t
    r_t      = mu_f * d_t + sigma_t * z_t                 (open -> close log return)

After a closure of C minutes the next open gaps from the last close by a
shock with variance sigma_f^2 * h * g^2 * k * C^p (k, p per market).

Instruments are signed sums of factors (identity except for forex crosses);
intrabar high/low are exact Brownian-bridge extremes; volume is a log-AR(1)
driven by the standardised move, the volatility level and seasonality.

Every random number used for a UTC day comes from a generator seeded by
(seed, market, day) with fixed shapes indexed by minute-of-day, so output is
independent of which instruments are written and of the end of the range.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from functools import lru_cache
from typing import Iterator, Optional

import numpy as np

from marketforge.config.catalog.base import AssetParams, MarketConfig
from marketforge.config.defaults import MarketDefaults, get_market_defaults
from marketforge.config.settings import AnomalyConfig, AnomalyType, MarketType
from marketforge.core.factors import FactorStructure, forex_structure
from marketforge.core.innovations import correlated_shocks
from marketforge.core.kernels import ar1, bridge_extremes, gjr_garch, regime_chain
from marketforge.core.seasonality import SessionSeasonality
from marketforge.trading_calendar import (
    MINUTES_PER_DAY,
    SECONDS_PER_DAY,
    TradingCalendar,
    get_calendar,
)

# Stable per-market stream identifiers (part of the reproducibility contract).
_MARKET_STREAM = {MarketType.CRYPTO: 1, MarketType.FOREX: 2, MarketType.STOCKS: 3}
# Max session opens (gaps) a calendar can produce within one UTC day.
_MAX_GAPS_PER_DAY = 4
# EMA weight per minute for regime multipliers (~15-minute ramp).
_REGIME_SMOOTHING = 1.0 / 15.0
_MEAN_ABS_Z = float(np.sqrt(2.0 / np.pi))
_VAR_ABS_Z = 1.0 - 2.0 / np.pi
_Z_CLIP = 10.0
_REFERENCE_YEAR = (1672531200, 1704067200)  # 2023, for annualisation


@dataclass(frozen=True)
class MarketSpec:
    """Everything needed to simulate one market."""

    market: MarketType
    instruments: tuple[AssetParams, ...]
    structure: FactorStructure
    factor_correlation: np.ndarray
    defaults: MarketDefaults
    anomaly: AnomalyConfig = field(default_factory=lambda: AnomalyConfig(types=frozenset()))

    @property
    def symbols(self) -> tuple[str, ...]:
        return self.structure.instruments


def build_market_spec(
    config: MarketConfig,
    anomalies: frozenset[AnomalyType] = frozenset(),
    defaults: Optional[MarketDefaults] = None,
) -> MarketSpec:
    """Turn a catalog market configuration into a simulation spec."""
    market = MarketType(config.market_type)
    defaults = defaults or get_market_defaults(market)
    symbols = list(config.symbols)
    if market == MarketType.FOREX:
        structure = forex_structure(symbols)
    else:
        structure = FactorStructure.identity(symbols)
    idx = [symbols.index(s) for s in structure.factors]
    corr = np.asarray(config.correlation_matrix)[np.ix_(idx, idx)]
    anomaly = replace(defaults.anomaly_config, types=frozenset(anomalies))
    return MarketSpec(
        market=market,
        instruments=tuple(config.get_asset(s) for s in symbols),
        structure=structure,
        factor_correlation=corr,
        defaults=defaults,
        anomaly=anomaly,
    )


@dataclass
class DayResult:
    """One UTC day of m1 candles for every instrument of a market."""

    timestamps: np.ndarray  # (n,) int64 UTC seconds
    open: np.ndarray        # (n, I)
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    volume: np.ndarray
    regime: np.ndarray      # (n,) int8, market-wide


@dataclass
class _State:
    log_price: np.ndarray       # (F,) factor log close
    garch_variance: np.ndarray  # (F,)
    garch_shock: np.ndarray     # (F,)
    regime: int
    drift_mult: float
    vol_mult: float
    volume_memory: np.ndarray   # (I,)
    last_timestamp: Optional[int] = None


def _normalised_regime_targets(
    cumulative: np.ndarray, drift: np.ndarray, vol: np.ndarray, initial: int
) -> tuple[np.ndarray, np.ndarray]:
    """
    Rescale regime multipliers so that, over the long run (smoothing included),
    the mean drift multiplier is 1 and the mean squared volatility multiplier
    is 1. Without this the configured annual drift and volatility were not
    what the simulation produced (e.g. stocks drifted down on average).
    """
    u = np.random.Generator(np.random.PCG64(20260613)).random(400_000)
    _, d, v, *_ = regime_chain(
        u, cumulative, drift, vol, _REGIME_SMOOTHING, initial, float(drift[initial]), float(vol[initial])
    )
    burn = 10_000
    vol_scale = 1.0 / np.sqrt(np.mean(v[burn:] ** 2))
    drift_shift = 1.0 - float(np.mean(d[burn:]))
    return drift + drift_shift, vol * vol_scale


def _closure_variance(minutes: np.ndarray, defaults: MarketDefaults) -> np.ndarray:
    m = np.asarray(minutes, dtype=float)
    return np.asarray(defaults.closure_variance_scale * np.power(m, defaults.closure_variance_exponent))


@lru_cache(maxsize=None)
def _effective_minutes_per_year(market: MarketType, scale: float, exponent: float) -> float:
    """Open minutes per year plus closure variance, in open-minute units."""
    cal = get_calendar(market)
    ts = cal.open_minutes(*_REFERENCE_YEAR)
    closed = np.diff(ts) // 60 - 1
    closed = closed[closed > 0]
    gap_var = float(np.sum(scale * np.power(closed.astype(float), exponent))) if closed.size else 0.0
    return float(ts.size) + gap_var


class MarketSimulator:
    """Stateful, day-by-day simulator for one market."""

    def __init__(self, spec: MarketSpec, seed: int) -> None:
        if seed < 0:
            raise ValueError(f"seed must be a non-negative integer, got {seed}")
        self.spec = spec
        self.seed = int(seed)
        d = spec.defaults
        self.calendar: TradingCalendar = get_calendar(spec.market)
        self.seasonality = SessionSeasonality(self.calendar)

        structure = spec.structure
        self._identity = structure.is_identity
        self._weights_t = structure.weights.T.copy()  # (F, I)
        n_f = len(structure.factors)
        n_i = len(structure.instruments)
        by_symbol = {a.symbol: a for a in spec.instruments}
        factors = [by_symbol[s] for s in structure.factors]

        minutes_per_year = _effective_minutes_per_year(
            spec.market, d.closure_variance_scale, d.closure_variance_exponent
        )
        self._sigma = np.array([a.volatility for a in factors]) / np.sqrt(minutes_per_year)
        self._mu = np.array([a.drift for a in factors]) / minutes_per_year
        self._cholesky = np.linalg.cholesky(spec.factor_correlation)
        self._nu = float(d.innovation_nu) if d.innovation_nu else None

        g = d.garch_params
        self._garch = (1.0 - g.persistence, g.alpha, g.beta, g.gamma)

        rp = d.regime_params
        self._regime_cum = np.cumsum(np.asarray(rp.transition_matrix, dtype=float), axis=1)
        self._regime_cum[:, -1] = 1.0
        r0 = rp.get_regime_index(rp.initial_regime)
        self._regime_drift, self._regime_vol = _normalised_regime_targets(
            self._regime_cum,
            np.asarray(rp.drift_multipliers, dtype=float),
            np.asarray(rp.volatility_multipliers, dtype=float),
            r0,
        )

        # Cross volatilities: (factor indices, weights) per derived instrument.
        corr = spec.factor_correlation
        self._cross_terms: list[tuple[int, np.ndarray, np.ndarray]] = []
        if not self._identity:
            for i in range(n_i):
                nz = np.nonzero(structure.weights[i])[0]
                if len(nz) == 1 and structure.weights[i, nz[0]] == 1.0:
                    continue
                self._cross_terms.append((i, nz, structure.weights[i, nz]))
        ref = self._instrument_sigma(np.tile(self._sigma, (1, 1)))[0]
        self._sigma_ref = ref  # (I,) unconditional per-minute sigma

        vp = d.volume_params
        self._volume = (vp.phi, vp.lam, vp.kappa)
        # volume_volatility is the stationary std of the noise part of log-volume;
        # the AR(1) innovation that produces it is smaller by sqrt(1 - phi^2).
        self._volume_noise = np.array(
            [by_symbol[s].volume_volatility for s in structure.instruments]
        ) * np.sqrt(1.0 - vp.phi ** 2)
        var_u = vp.lam ** 2 * _VAR_ABS_Z + self._volume_noise ** 2 + self.seasonality.log_variance
        self._volume_log_correction = 0.5 * var_u / (1.0 - vp.phi ** 2)
        self._base_volume = np.array([by_symbol[s].volume_base for s in structure.instruments])

        self._state = _State(
            log_price=np.log([a.start_price for a in factors]),
            garch_variance=np.ones(n_f),
            garch_shock=np.zeros(n_f),
            regime=r0,
            drift_mult=float(self._regime_drift[r0]),
            vol_mult=float(self._regime_vol[r0]),
            volume_memory=np.zeros(n_i),
        )

    # ------------------------------------------------------------- helpers
    def _instrument_sigma(self, factor_sigma: np.ndarray) -> np.ndarray:
        """Per-instrument std from factor stds (rows = minutes)."""
        if self._identity:
            return factor_sigma
        out = np.abs(factor_sigma @ self._weights_t)  # exact for anchors
        corr = self.spec.factor_correlation
        for i, idx, w in self._cross_terms:
            s = factor_sigma[:, idx] * w
            out[:, i] = np.sqrt(np.maximum(np.einsum("nj,jk,nk->n", s, corr[np.ix_(idx, idx)], s), 0.0))
        return np.asarray(out)

    def _correlated(self, z: np.ndarray, chi2: np.ndarray) -> np.ndarray:
        return correlated_shocks(z, chi2, self._cholesky, self._nu)

    def _day_rng(self, day: int, stream: int) -> np.random.Generator:
        seq = np.random.SeedSequence([self.seed, _MARKET_STREAM[self.spec.market], day, stream])
        return np.random.Generator(np.random.PCG64(seq))

    # ---------------------------------------------------------------- core
    def simulate_day(self, day: int, start: int, end: int) -> Optional[DayResult]:
        """Simulate the open minutes of UTC day `day` that fall within [start, end)."""
        day_ts = day * SECONDS_PER_DAY + 60 * np.arange(MINUTES_PER_DAY, dtype=np.int64)
        mask = self.calendar.open_mask(day_ts) & (day_ts >= start) & (day_ts < end)
        rows = np.nonzero(mask)[0]
        if rows.size == 0:
            return None
        ts = day_ts[rows]
        n = rows.size
        st = self._state
        n_f = self._sigma.size
        n_i = self._base_volume.size
        nu = self._nu if self._nu is not None else 5.0

        # Fixed-shape draws, in a fixed order (reproducibility contract).
        rng = self._day_rng(day, 0)
        z_all = rng.standard_normal((MINUTES_PER_DAY, n_f))
        chi_all = rng.chisquare(nu, MINUTES_PER_DAY)
        z_gap = rng.standard_normal((_MAX_GAPS_PER_DAY, n_f))
        chi_gap = rng.chisquare(nu, _MAX_GAPS_PER_DAY)
        u_regime = rng.random(MINUTES_PER_DAY)
        u_high = 1.0 - rng.random((MINUTES_PER_DAY, n_i))
        u_low = 1.0 - rng.random((MINUTES_PER_DAY, n_i))
        e_volume = rng.standard_normal((MINUTES_PER_DAY, n_i))

        z = self._correlated(z_all[rows], chi_all[rows])

        regimes, drift_m, vol_m, st.regime, st.drift_mult, st.vol_mult = regime_chain(
            u_regime[rows], self._regime_cum, self._regime_drift, self._regime_vol,
            _REGIME_SMOOTHING, st.regime, st.drift_mult, st.vol_mult,
        )
        h, st.garch_variance, st.garch_shock = gjr_garch(
            z, *self._garch, st.garch_variance, st.garch_shock
        )
        season = self.seasonality.factor(ts)
        level = np.sqrt(h) * vol_m[:, None]                 # (n, F) turbulence
        sigma_f = self._sigma * level * season[:, None]
        returns_f = self._mu * drift_m[:, None] + sigma_f * z

        # Gaps after closures.
        gap_f = np.zeros_like(returns_f)
        if st.last_timestamp is not None:
            prev = np.concatenate(([st.last_timestamp], ts[:-1]))
            closed = (ts - prev) // 60 - 1
            gap_rows = np.nonzero(closed > 0)[0]
            if gap_rows.size > _MAX_GAPS_PER_DAY:
                raise RuntimeError("calendar produced more session opens in a day than supported")
            if gap_rows.size:
                k = gap_rows.size
                zg = self._correlated(z_gap[:k], chi_gap[:k])
                var_units = _closure_variance(closed[gap_rows], self.spec.defaults)
                gap_f[gap_rows] = (
                    self._sigma * level[gap_rows] * np.sqrt(var_units)[:, None] * zg
                    + self._mu * var_units[:, None]
                )

        # Factor log path, then project to instruments.
        log_close_f = st.log_price + np.cumsum(gap_f + returns_f, axis=0)
        # Open = previous close (+ gap), built from the same floats so that an
        # in-session open is bit-identical to the previous close.
        log_open_f = np.vstack([st.log_price[None, :], log_close_f[:-1]]) + gap_f
        st.log_price = log_close_f[-1].copy()
        st.last_timestamp = int(ts[-1])
        if self._identity:
            log_open, log_close, body = log_open_f, log_close_f, returns_f
            sigma_i = sigma_f
            level_i = sigma_f / (self._sigma * season[:, None])
        else:
            wt = self._weights_t
            log_open, log_close, body = log_open_f @ wt, log_close_f @ wt, returns_f @ wt
            sigma_i = self._instrument_sigma(sigma_f)
            level_i = sigma_i / (self._sigma_ref * season[:, None])

        hi, lo = bridge_extremes(body, sigma_i, u_high[rows], u_low[rows])
        open_ = np.exp(log_open)
        close = np.exp(log_close)
        high = np.maximum(np.exp(log_open + hi), np.maximum(open_, close))
        low = np.minimum(np.exp(log_open + lo), np.minimum(open_, close))

        # Volume: log-AR(1) driven by the standardised move, turbulence and seasonality.
        phi, lam, kappa = self._volume
        zabs = np.clip(np.abs(body) / sigma_i, 0.0, _Z_CLIP) - _MEAN_ABS_Z
        drivers = (
            lam * zabs
            + kappa * np.log(level_i)
            + np.log(season)[:, None]
            + self._volume_noise * e_volume[rows]
        )
        y, st.volume_memory = ar1(drivers, phi, st.volume_memory)
        volume = self._base_volume * np.exp(y - self._volume_log_correction)

        result = DayResult(ts, open_, high, low, close, volume, regimes)
        if self.spec.anomaly.types:
            self._inject_anomalies(day, rows, result)
        return result

    def run(self, start: int, end: int) -> Iterator[DayResult]:
        """Yield simulated days covering [start, end)."""
        first = int(start) // SECONDS_PER_DAY
        last = (int(end) - 1) // SECONDS_PER_DAY
        for day in range(first, last + 1):
            res = self.simulate_day(day, start, end)
            if res is not None:
                yield res

    # ----------------------------------------------------------- anomalies
    def _inject_anomalies(self, day: int, rows: np.ndarray, res: DayResult) -> None:
        cfg = self.spec.anomaly
        n_i = res.open.shape[1]
        rng = self._day_rng(day, 1)
        u_spike = rng.random((MINUTES_PER_DAY, n_i))
        u_dir = rng.random((MINUTES_PER_DAY, n_i))
        u_mag = rng.random((MINUTES_PER_DAY, n_i))
        u_crash = rng.random(n_i)
        u_start = rng.random(n_i)

        if AnomalyType.SPIKES in cfg.types:
            lo_m, hi_m = cfg.spike_magnitude_range
            hit = u_spike[rows] < cfg.spike_probability
            if hit.any():
                mag = lo_m + (hi_m - lo_m) * u_mag[rows]
                mid = 0.5 * (res.open + res.close)
                up = hit & (u_dir[rows] < 0.5)
                down = hit & ~up
                res.high = np.where(up, res.high + mid * mag, res.high)
                res.low = np.where(down, np.maximum(res.low - mid * mag, 0.5 * mid), res.low)
                res.volume = np.where(hit, res.volume * 2.0, res.volume)

        if AnomalyType.FLASH_CRASH in cfg.types:
            length = int(cfg.flash_crash_recovery_candles)
            n = rows.size
            if n > length + 1:
                envelope = _flash_crash_envelope(length, cfg.flash_crash_magnitude)
                for i in np.nonzero(u_crash < cfg.flash_crash_probability)[0]:
                    s = int(u_start[i] * (n - length - 1))
                    _apply_envelope(res, i, s, envelope)


def _flash_crash_envelope(length: int, magnitude: float) -> np.ndarray:
    """Price multiplier at each candle close: sharp drop, short floor, recovery to 1."""
    drop = max(1, length // 3)
    floor = max(1, length // 6)
    rec = max(1, length - drop - floor)
    p = np.arange(1, drop + 1) / drop
    fall = magnitude * (1 - np.exp(-3 * p)) / (1 - np.exp(-3))
    rise = magnitude * (1 - np.arange(1, rec + 1) / rec)
    depth = np.concatenate([fall, np.full(floor, magnitude), rise])
    return np.asarray(1.0 - depth)


def _apply_envelope(res: DayResult, i: int, start: int, env: np.ndarray) -> None:
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
