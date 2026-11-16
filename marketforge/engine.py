# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the MIT License. See the LICENSE file in the project
# root for full license information.

"""
Whole-market simulation engine.

A :class:`MarketSimulator` simulates one market jointly, walking time one UTC
day at a time and carrying its state (prices, GARCH variance, regime, volume
memory) from day to day (see docs/adr/0001). Random draws always cover the
whole market; the computation after them covers only the requested
instruments and their factors, which is bit-identical (see docs/adr/0007).

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

from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field, replace
from functools import cache, lru_cache

import numpy as np

from marketforge.calendars.trading_calendar import TradingCalendar, get_calendar
from marketforge.config.catalog.base import AssetParams, MarketConfig
from marketforge.config.defaults import MarketDefaults, get_market_defaults
from marketforge.config.settings import AnomalyConfig
from marketforge.core.factors import FactorStructure, forex_structure
from marketforge.core.innovations import correlated_shocks
from marketforge.core.kernels import (
    bar_arguments,
    factor_paths,
    finish_bars,
    gjr_garch,
    project_signed,
    regime_chain,
)
from marketforge.core.seasonality import SessionSeasonality
from marketforge.domain.anomalies import AnomalyType
from marketforge.domain.markets import MarketType
from marketforge.domain.time import MINUTES_PER_DAY, REFERENCE_YEAR, SECONDS_PER_DAY

# Stable per-market stream identifiers (part of the reproducibility contract).
_MARKET_STREAM = {MarketType.CRYPTO: 1, MarketType.FOREX: 2, MarketType.STOCKS: 3}
# Max session opens (gaps) a calendar can produce within one UTC day.
_MAX_GAPS_PER_DAY = 4
# EMA weight per minute for regime multipliers (~15-minute ramp).
_REGIME_SMOOTHING = 1.0 / 15.0
_MEAN_ABS_Z = float(np.sqrt(2.0 / np.pi))
_VAR_ABS_Z = 1.0 - 2.0 / np.pi
_Z_CLIP = 10.0


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
    defaults: MarketDefaults | None = None,
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
    open: np.ndarray  # (n, I)
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    volume: np.ndarray
    regime: np.ndarray  # (n,) int8, market-wide


@dataclass
class _State:
    log_price: np.ndarray  # (Fa,) log close of each active factor
    garch_variance: np.ndarray  # (Fa,)
    garch_shock: np.ndarray  # (Fa,)
    regime: int
    drift_mult: float
    vol_mult: float
    volume_memory: np.ndarray  # (I,) one per selected instrument
    last_timestamp: int | None = None


def _normalised_regime_targets(
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
        _REGIME_SMOOTHING,
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


def _closure_variance(minutes: np.ndarray, defaults: MarketDefaults) -> np.ndarray:
    m = np.asarray(minutes, dtype=float)
    return np.asarray(
        defaults.closure_variance_scale * np.power(m, defaults.closure_variance_exponent)
    )


@cache
def _effective_minutes_per_year(market: MarketType, scale: float, exponent: float) -> float:
    """Open minutes per year plus closure variance, in open-minute units."""
    cal = get_calendar(market)
    ts = cal.open_minutes(*REFERENCE_YEAR)
    closed = np.diff(ts) // 60 - 1
    closed = closed[closed > 0]
    gap_var = (
        float(np.sum(scale * np.power(closed.astype(float), exponent))) if closed.size else 0.0
    )
    return float(ts.size) + gap_var


class MarketSimulator:
    """
    Stateful, day-by-day simulator for one market.

    Every random number is drawn for the whole market with fixed shapes, so an
    instrument's candles never depend on which other instruments are requested.
    The work after the draws is done only for ``instruments`` (default: every
    instrument of the market) and the factors they are built from, and the
    columns of each :class:`DayResult` follow the order of ``instruments``.
    """

    def __init__(
        self, spec: MarketSpec, seed: int, instruments: Sequence[str] | None = None
    ) -> None:
        if seed < 0:
            raise ValueError(f"seed must be a non-negative integer, got {seed}")
        self.spec = spec
        self.seed = int(seed)
        d = spec.defaults
        self.calendar: TradingCalendar = get_calendar(spec.market)
        self.seasonality = _seasonality(spec.market)

        structure = spec.structure
        symbols = structure.instruments
        selected = list(symbols) if instruments is None else list(instruments)
        unknown = [s for s in selected if s not in symbols]
        if unknown:
            raise ValueError(f"Not instruments of the {spec.market.value} market: {unknown}")
        if len(set(selected)) != len(selected):
            raise ValueError(f"Duplicate instruments requested: {selected}")
        if not selected:
            raise ValueError("At least one instrument is required")
        self.instruments: tuple[str, ...] = tuple(selected)
        inst = np.array([symbols.index(s) for s in selected], dtype=np.intp)

        self._n_factors = len(structure.factors)
        self._n_instruments = len(symbols)
        by_symbol = {a.symbol: a for a in spec.instruments}
        factors = [by_symbol[s] for s in structure.factors]

        minutes_per_year = _effective_minutes_per_year(
            spec.market, d.closure_variance_scale, d.closure_variance_exponent
        )
        sigma = np.array([a.volatility for a in factors]) / np.sqrt(minutes_per_year)
        mu = np.array([a.drift for a in factors]) / minutes_per_year
        self._cholesky = np.linalg.cholesky(spec.factor_correlation)
        self._nu = float(d.innovation_nu) if d.innovation_nu else None

        g = d.garch_params
        self._garch = (1.0 - g.persistence, g.alpha, g.beta, g.gamma)

        rp = d.regime_params
        self._regime_cum = np.cumsum(np.asarray(rp.per_minute_matrix(), dtype=float), axis=1)
        self._regime_cum[:, -1] = 1.0
        r0 = rp.get_regime_index(rp.initial_regime)
        self._regime_drift, self._regime_vol = _normalised_regime_targets(
            self._regime_cum,
            np.asarray(rp.drift_multipliers, dtype=float),
            np.asarray(rp.volatility_multipliers, dtype=float),
            r0,
        )

        # ---- active subset: the selected instruments and their factors ----
        self._projection = _Projection.build(structure, inst, spec.factor_correlation)
        fa = self._projection.factors
        self._factors = fa
        self._all_factors = fa.size == self._n_factors and bool(np.all(fa == np.arange(fa.size)))
        self._inst = inst
        self._all_instruments = inst.size == self._n_instruments and bool(
            np.all(inst == np.arange(inst.size))
        )
        self._sigma = sigma[fa]
        self._mu = mu[fa]
        # Unconditional per-minute sigma of each selected instrument.
        self._sigma_ref = self._projection.sigma(self._sigma[None, :])[0]

        vp = d.volume_params
        self._volume = (vp.phi, vp.lam, vp.kappa)
        # volume_volatility is the stationary std of the noise part of log-volume;
        # the AR(1) innovation that produces it is smaller by sqrt(1 - phi^2).
        noise = np.array([by_symbol[s].volume_volatility for s in symbols]) * np.sqrt(
            1.0 - vp.phi**2
        )
        var_u = vp.lam**2 * _VAR_ABS_Z + noise**2 + self.seasonality.log_variance
        self._volume_noise = noise[inst]
        self._volume_log_correction = (0.5 * var_u / (1.0 - vp.phi**2))[inst]
        self._base_volume = np.array([by_symbol[s].volume_base for s in symbols])[inst]

        self._state = _State(
            log_price=np.log([a.start_price for a in factors])[fa],
            garch_variance=np.ones(fa.size),
            garch_shock=np.zeros(fa.size),
            regime=r0,
            drift_mult=float(self._regime_drift[r0]),
            vol_mult=float(self._regime_vol[r0]),
            volume_memory=np.zeros(inst.size),
        )

    # ------------------------------------------------------------- helpers
    def _correlated(self, z: np.ndarray, chi2: np.ndarray) -> np.ndarray:
        """Correlated shocks of the active factors (always computed market-wide)."""
        full = correlated_shocks(z, chi2, self._cholesky, self._nu)
        return full if self._all_factors else np.ascontiguousarray(full[:, self._factors])

    def _select(self, draws: np.ndarray, rows: np.ndarray) -> np.ndarray:
        """Rows ``rows`` and the selected instruments' columns of a market-wide draw."""
        if self._all_instruments:
            return np.asarray(draws[rows])
        return np.asarray(draws[np.ix_(rows, self._inst)])

    def _day_rng(self, day: int, stream: int) -> np.random.Generator:
        seq = np.random.SeedSequence([self.seed, _MARKET_STREAM[self.spec.market], day, stream])
        return np.random.Generator(np.random.PCG64(seq))

    # ---------------------------------------------------------------- core
    def simulate_day(self, day: int, start: int, end: int) -> DayResult | None:
        """Simulate the open minutes of UTC day `day` that fall within [start, end)."""
        day_ts = day * SECONDS_PER_DAY + 60 * np.arange(MINUTES_PER_DAY, dtype=np.int64)
        session_mask = self.calendar.open_mask(day_ts)
        rows = np.nonzero(session_mask & (day_ts >= start) & (day_ts < end))[0]
        if rows.size == 0:
            return None
        # Matrix products go through BLAS, and some BLAS builds (Accelerate on
        # macOS 15) round a row differently depending on how many rows the
        # matrix has. So a day cut short by the range is computed in the shape
        # of the whole session (its rows at their own positions), exactly like
        # the full day, and extending a range never changes earlier candles.
        # Whole days are unaffected: there, rows *is* the session.
        session = SessionShape.of(np.nonzero(session_mask)[0], rows)
        ts = day_ts[rows]
        st = self._state
        n_f = self._n_factors
        n_i = self._n_instruments
        nu = self._nu if self._nu is not None else 5.0

        # Fixed-shape, market-wide draws in a fixed order (reproducibility contract).
        rng = self._day_rng(day, 0)
        z_all = rng.standard_normal((MINUTES_PER_DAY, n_f))
        chi_all = rng.chisquare(nu, MINUTES_PER_DAY)
        z_gap = rng.standard_normal((_MAX_GAPS_PER_DAY, n_f))
        chi_gap = rng.chisquare(nu, _MAX_GAPS_PER_DAY)
        u_regime = rng.random(MINUTES_PER_DAY)
        u_high = rng.random((MINUTES_PER_DAY, n_i))
        u_low = rng.random((MINUTES_PER_DAY, n_i))
        e_volume = rng.standard_normal((MINUTES_PER_DAY, n_i))

        z = session.rows_of(self._correlated(z_all[session.rows], chi_all[session.rows]))

        regimes, drift_m, vol_m, st.regime, st.drift_mult, st.vol_mult = regime_chain(
            u_regime[rows],
            self._regime_cum,
            self._regime_drift,
            self._regime_vol,
            _REGIME_SMOOTHING,
            st.regime,
            st.drift_mult,
            st.vol_mult,
        )
        h, st.garch_variance, st.garch_shock = gjr_garch(
            z, *self._garch, st.garch_variance, st.garch_shock
        )
        season = self.seasonality.factor(ts)

        # Gaps after closures: at most a few rows a day.
        # intp, not int64: it is what np.nonzero returns below, so both paths
        # hand factor_paths the same dtype. The explicit annotation keeps mypy
        # from pinning the narrower type inferred from this placeholder.
        gap_rows: np.ndarray = np.empty(0, dtype=np.intp)
        gap = np.empty((0, self._sigma.size))
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
                level = np.sqrt(h[gap_rows]) * vol_m[gap_rows, None]
                gap = (
                    self._sigma * level * np.sqrt(var_units)[:, None] * zg
                    + self._mu * var_units[:, None]
                )

        # Factor paths, then instruments.
        sigma_f, returns_f, log_open_f, log_close_f = factor_paths(
            h, vol_m, drift_m, season, z, self._sigma, self._mu, gap_rows, gap, st.log_price
        )
        st.log_price = log_close_f[-1].copy()
        st.last_timestamp = int(ts[-1])
        proj = self._projection
        if proj.kind == "matrix":  # the only projection that goes through BLAS
            log_open = session.apply(proj.apply, log_open_f)
            log_close = session.apply(proj.apply, log_close_f)
            body = session.apply(proj.apply, returns_f)
        else:
            log_open = proj.apply(log_open_f)
            log_close = proj.apply(log_close_f)
            body = proj.apply(returns_f)
        sigma_i = session.apply(proj.sigma, sigma_f) if proj.crosses else proj.sigma(sigma_f)

        # Intrabar extremes, prices and volume. Transcendentals stay in NumPy
        # (bit-exactness, see docs/adr/0007); everything else is fused.
        n, m = body.shape
        prices = np.empty((4, n, m))
        level_i = np.empty((n, m))
        bar_arguments(
            log_open,
            log_close,
            body,
            sigma_i,
            self.spec.defaults.intrabar_volatility_ratio,
            np.log(1.0 - self._select(u_high, rows)),
            np.log(1.0 - self._select(u_low, rows)),
            self._sigma_ref,
            season,
            prices,
            level_i,
        )
        np.exp(prices, out=prices)  # open, close, bridge high, bridge low
        np.log(level_i, out=level_i)
        phi, lam, kappa = self._volume
        high, low, volume = finish_bars(
            prices,
            body,
            sigma_i,
            level_i,
            np.log(season),
            self._volume_noise,
            self._select(e_volume, rows),
            lam,
            kappa,
            phi,
            _Z_CLIP,
            _MEAN_ABS_Z,
            self._volume_log_correction,
            st.volume_memory,
        )
        np.exp(volume, out=volume)
        volume *= self._base_volume  # base * exp(.) == exp(.) * base

        result = DayResult(ts, prices[0], high, low, prices[1], volume, regimes)
        if self.spec.anomaly.types:
            self._inject_anomalies(day, rows, result)
        if self.spec.defaults.integer_volume:
            result.volume = np.maximum(np.rint(result.volume), 1.0)
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
        n_i = self._n_instruments
        rng = self._day_rng(day, 1)
        u_spike = rng.random((MINUTES_PER_DAY, n_i))
        u_dir = rng.random((MINUTES_PER_DAY, n_i))
        u_mag = rng.random((MINUTES_PER_DAY, n_i))
        u_crash = np.asarray(rng.random(n_i))[self._inst]
        u_start = np.asarray(rng.random(n_i))[self._inst]

        if AnomalyType.SPIKES in cfg.types:
            lo_m, hi_m = cfg.spike_magnitude_range
            hit = self._select(u_spike, rows) < cfg.spike_probability
            if hit.any():
                mag = lo_m + (hi_m - lo_m) * self._select(u_mag, rows)
                mid = 0.5 * (res.open + res.close)
                up = hit & (self._select(u_dir, rows) < 0.5)
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
                    _apply_envelope(res, int(i), s, envelope)


@cache
def _seasonality(market: MarketType) -> SessionSeasonality:
    """Shared seasonality of a market (normalised once over a reference year)."""
    return SessionSeasonality(get_calendar(market))


@dataclass(frozen=True)
class _Projection:
    """
    How the selected instruments derive from the active factors.

    ``factors`` are the indices (into the market's factors) of the factors that
    are simulated. Instruments are either the factors themselves (crypto,
    stocks), a signed sum of at most two of them with weights +-1 (every
    built-in forex pair), or, for user-defined forex structures beyond that,
    a general projection that falls back to the full matrix product.
    """

    factors: np.ndarray  # (Fa,) indices into the market's factors
    kind: str  # "identity" | "signed" | "matrix"
    index: np.ndarray  # signed: (I, 2) positions in the active factors, -1 = unused
    sign: np.ndarray  # signed: (I, 2)
    weights_t: np.ndarray  # matrix: (F, I_all) full transposed weights
    instruments: np.ndarray  # matrix: (I,) columns of the full product to keep
    anchors: tuple[tuple[int, int], ...]  # (column, active factor position)
    crosses: tuple[tuple[int, np.ndarray, np.ndarray, np.ndarray], ...]
    # crosses: (column, active factor positions, weights, correlation sub-matrix)

    @classmethod
    def build(
        cls, structure: FactorStructure, inst: np.ndarray, correlation: np.ndarray
    ) -> _Projection:
        empty = np.empty((0, 2), dtype=np.int64)
        if structure.is_identity:
            return cls(inst, "identity", empty, empty.astype(float), np.empty((0, 0)), inst, (), ())
        weights = structure.weights[inst]  # (I, F)
        nonzero = [np.nonzero(row)[0] for row in weights]
        simple = all(
            nz.size <= 2 and np.all(np.abs(row[nz]) == 1.0)
            for row, nz in zip(weights, nonzero, strict=True)
        )
        if simple:
            factors = np.unique(np.concatenate(nonzero))
            kind = "signed"
        else:
            factors = np.arange(structure.weights.shape[1])
            kind = "matrix"
        pos = {int(f): p for p, f in enumerate(factors)}
        index = np.full((inst.size, 2), -1, dtype=np.int64)
        sign = np.zeros((inst.size, 2))
        anchors: list[tuple[int, int]] = []
        crosses: list[tuple[int, np.ndarray, np.ndarray, np.ndarray]] = []
        for j, (row, nz) in enumerate(zip(weights, nonzero, strict=True)):
            if kind == "signed":
                index[j, : nz.size] = [pos[int(f)] for f in nz]
                sign[j, : nz.size] = row[nz]
            if nz.size == 1 and row[nz[0]] == 1.0:
                anchors.append((j, pos[int(nz[0])]))
            else:
                local = np.array([pos[int(f)] for f in nz], dtype=np.intp)
                crosses.append((j, local, row[nz], correlation[np.ix_(nz, nz)]))
        return cls(
            factors,
            kind,
            index,
            sign,
            structure.weights.T.copy() if kind == "matrix" else np.empty((0, 0)),
            inst,
            tuple(anchors),
            tuple(crosses),
        )

    def apply(self, x: np.ndarray) -> np.ndarray:
        """Instrument values from active-factor values (rows = minutes)."""
        if self.kind == "identity":
            return x
        if self.kind == "signed":
            return project_signed(x, self.index, self.sign)
        return np.ascontiguousarray((x @ self.weights_t)[:, self.instruments])

    def sigma(self, factor_sigma: np.ndarray) -> np.ndarray:
        """Per-instrument std from active-factor stds (rows = minutes)."""
        if self.kind == "identity":
            return factor_sigma
        out = np.empty((factor_sigma.shape[0], self.instruments.size))
        for j, p in self.anchors:
            out[:, j] = factor_sigma[:, p]
        for j, idx, w, corr in self.crosses:
            s = factor_sigma[:, idx] * w
            out[:, j] = np.sqrt(np.maximum(np.einsum("nj,jk,nk->n", s, corr, s), 0.0))
        return out


@dataclass(frozen=True)
class SessionShape:
    """Where a day's simulated minutes sit inside its whole trading session.

    Row-wise matrix products are evaluated on session-shaped arrays so that
    BLAS sees the same shape for a minute whether or not the requested range
    cuts its day short (see :meth:`MarketSimulator.simulate_day`).
    """

    rows: np.ndarray  # minute-of-day indices of the whole session
    positions: np.ndarray | None  # positions of the simulated minutes in it; None = all

    @classmethod
    def of(cls, session_rows: np.ndarray, simulated_rows: np.ndarray) -> SessionShape:
        if simulated_rows.size == session_rows.size:
            return cls(simulated_rows, None)
        return cls(session_rows, np.searchsorted(session_rows, simulated_rows))

    def rows_of(self, session_values: np.ndarray) -> np.ndarray:
        """The simulated minutes' rows of a session-shaped array."""
        if self.positions is None:
            return session_values
        return np.ascontiguousarray(session_values[self.positions])

    def apply(self, func: Callable[[np.ndarray], np.ndarray], values: np.ndarray) -> np.ndarray:
        """``func(values)``, evaluated with ``values`` embedded in the session's shape."""
        if self.positions is None:
            return func(values)
        padded = np.zeros((self.rows.size, *values.shape[1:]), dtype=values.dtype)
        padded[self.positions] = values
        return self.rows_of(func(padded))


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
