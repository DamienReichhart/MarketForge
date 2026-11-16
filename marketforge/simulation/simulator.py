# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the GNU Affero General Public License v3.0 or later.
# See the LICENSE file in the project root for full license information.

"""
Whole-market, day-by-day simulator.

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

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from marketforge.calendars.trading_calendar import TradingCalendar, get_calendar
from marketforge.domain.bars import Bars
from marketforge.domain.markets import MarketType
from marketforge.domain.time import MINUTES_PER_DAY, SECONDS_PER_DAY
from marketforge.simulation.annualisation import closure_variance, effective_minutes_per_year
from marketforge.simulation.anomalies import inject_anomalies
from marketforge.simulation.innovations import correlated_shocks
from marketforge.simulation.kernels import (
    bar_arguments,
    factor_paths,
    finish_bars,
    gjr_garch,
    regime_chain,
)
from marketforge.simulation.projection import Projection, SessionShape
from marketforge.simulation.regimes import REGIME_SMOOTHING, normalised_regime_targets
from marketforge.simulation.seasonality import get_seasonality
from marketforge.simulation.spec import MarketSpec
from marketforge.simulation.spread import minutes_since_reopen, quoted_spread

# Stable per-market stream identifiers (part of the reproducibility contract).
_MARKET_STREAM = {MarketType.CRYPTO: 1, MarketType.FOREX: 2, MarketType.STOCKS: 3}
# Max session opens (gaps) a calendar can produce within one UTC day.
_MAX_GAPS_PER_DAY = 4
_MEAN_ABS_Z = float(np.sqrt(2.0 / np.pi))
_VAR_ABS_Z = 1.0 - 2.0 / np.pi
_Z_CLIP = 10.0


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


class MarketSimulator:
    """
    Stateful, day-by-day simulator for one market.

    Every random number is drawn for the whole market with fixed shapes, so an
    instrument's candles never depend on which other instruments are requested.
    The work after the draws is done only for ``instruments`` (default: every
    instrument of the market) and the factors they are built from, and the
    columns of each :class:`Bars` follow the order of ``instruments``.
    """

    def __init__(
        self,
        spec: MarketSpec,
        seed: int,
        instruments: Sequence[str] | None = None,
        spread: bool = False,
    ) -> None:
        if seed < 0:
            raise ValueError(f"seed must be a non-negative integer, got {seed}")
        self.spec = spec
        self.seed = int(seed)
        d = spec.defaults
        self.calendar: TradingCalendar = get_calendar(spec.market)
        self.seasonality = get_seasonality(spec.market)

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

        minutes_per_year = effective_minutes_per_year(
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
        self._regime_drift, self._regime_vol = normalised_regime_targets(
            self._regime_cum,
            np.asarray(rp.drift_multipliers, dtype=float),
            np.asarray(rp.volatility_multipliers, dtype=float),
            r0,
        )

        # ---- active subset: the selected instruments and their factors ----
        self._projection = Projection.build(structure, inst, spec.factor_correlation)
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

        # Typical spread of each selected instrument, as a fraction of its price:
        # its own catalog value, else the market's rule from its annual volatility
        # and its price.
        self._spread = spread
        sp = d.spread_params
        annual = self._sigma_ref * np.sqrt(minutes_per_year)
        self._spread_scale = (
            np.array([by_symbol[s].start_price for s in selected]) if sp.fixed_scale else None
        )
        self._spread_base = 1e-4 * np.array(
            [
                by_symbol[s].spread_bps or sp.default_bps(float(v), by_symbol[s].start_price)
                for s, v in zip(selected, annual, strict=True)
            ]
        )

        self._state = _State(
            log_price=np.log([a.start_price for a in factors])[fa],
            garch_variance=np.ones(fa.size),
            garch_shock=np.zeros(fa.size),
            regime=r0,
            drift_mult=float(self._regime_drift[r0]),
            vol_mult=float(self._regime_vol[r0]),
            volume_memory=np.zeros(inst.size),
        )

    # ---------------------------------------------------------- checkpoint
    def snapshot(self) -> dict[str, Any]:
        """
        The simulator's state between two days, as plain JSON-serialisable values.

        A simulator of the same market, seed and instruments that is given this
        state with :meth:`restore` continues exactly as this one would (floats
        survive JSON unchanged).
        """
        st = self._state
        return {
            "log_price": st.log_price.tolist(),
            "garch_variance": st.garch_variance.tolist(),
            "garch_shock": st.garch_shock.tolist(),
            "regime": int(st.regime),
            "drift_mult": float(st.drift_mult),
            "vol_mult": float(st.vol_mult),
            "volume_memory": st.volume_memory.tolist(),
            "last_timestamp": st.last_timestamp,
        }

    def restore(self, snapshot: dict[str, Any]) -> None:
        """Continue from a state saved by :meth:`snapshot`."""
        st = self._state
        arrays = {
            name: np.asarray(snapshot[name], dtype=float)
            for name in ("log_price", "garch_variance", "garch_shock", "volume_memory")
        }
        for name, values in arrays.items():
            if values.shape != getattr(st, name).shape:
                raise ValueError(
                    f"checkpoint does not match the instruments of this simulator ({name})"
                )
        self._state = _State(
            regime=int(snapshot["regime"]),
            drift_mult=float(snapshot["drift_mult"]),
            vol_mult=float(snapshot["vol_mult"]),
            last_timestamp=snapshot["last_timestamp"],
            **arrays,
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
    def simulate_day(self, day: int, start: int, end: int) -> Bars | None:
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
            REGIME_SMOOTHING,
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
                var_units = closure_variance(closed[gap_rows], self.spec.defaults)
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

        result = Bars(ts, prices[0], high, low, prices[1], volume, regimes)
        if self.spec.anomaly.types:
            inject_anomalies(
                self.spec.anomaly,
                self._day_rng(day, 1),
                result,
                n_market_instruments=self._n_instruments,
                selected=self._inst,
                select=lambda draws: self._select(draws, rows),
                session_size=session.rows.size,
                positions=(
                    np.arange(rows.size) if session.positions is None else session.positions
                ),
            )
        if self.spec.defaults.integer_volume:
            result.volume = np.maximum(np.rint(result.volume), 1.0)
        if self._spread:
            # Its own random stream: asking for spreads changes no candle.
            noise = self._day_rng(day, 2).standard_normal((MINUTES_PER_DAY, n_i))
            result.spread = quoted_spread(
                self.spec.defaults.spread_params,
                self._spread_base,
                result.close if self._spread_scale is None else self._spread_scale,
                level_i,  # holds the log of the turbulence by now
                season,
                minutes_since_reopen(self.calendar, day)[rows],
                self._select(noise, rows),
            )
        return result
