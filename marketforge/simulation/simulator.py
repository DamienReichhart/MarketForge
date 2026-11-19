# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
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
    g_t, d_t   market-wide regime volatility multiplier / trend strength (docs/adr/0013)
    s_t        intraday seasonality (mean square 1 over a year)
    lambda_f   sigma_f * the factor's loading on the market's main factor
    sigma_t  = sigma_f * sqrt(h_t) * g_t * s_t
    r_t      = mu_f + lambda_f * d_t + sigma_t * z_t      (open -> close log return)

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

import functools
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
from marketforge.simulation.earnings import (
    BOOST_HORIZON,
    EARNINGS_MOVE_DAYS,
    EARNINGS_NU,
    reports_between,
    volatility_boost,
)
from marketforge.simulation.innovations import correlated_shocks, stressed_shocks
from marketforge.simulation.kernels import (
    bar_arguments,
    factor_paths,
    finish_bars,
    gjr_garch,
    pull_to_pegs,
    regime_spells,
)
from marketforge.simulation.macro import (
    STRESSED,
    closure_shock,
    global_mixing,
    global_shocks,
    global_stress_shocks,
    macro_state,
    macro_trends,
)
from marketforge.simulation.pegs import market_pegs, peg_factors
from marketforge.simulation.projection import Projection, SessionShape
from marketforge.simulation.regimes import (
    REGIME_SMOOTHING,
    dollar_portfolio,
    forex_risk_direction,
    main_factor_loadings,
    normalised_spell_targets,
)
from marketforge.simulation.seasonality import get_seasonality
from marketforge.simulation.spec import MarketSpec, tick_grid
from marketforge.simulation.spread import minutes_since_reopen, quoted_spread

# Stable per-market stream identifiers (part of the reproducibility contract).
_MARKET_STREAM = {MarketType.CRYPTO: 1, MarketType.FOREX: 2, MarketType.STOCKS: 3}
# Max session opens (gaps) a calendar can produce within one UTC day.
_MAX_GAPS_PER_DAY = 4
# Loading of the most exposed series on the main factor in stressed regimes.
STRESS_LOADING = 0.95
# Below 1, pulls weakly exposed series towards that loading too: in a crash
# even a loosely correlated coin moves with BTC.
STRESS_COMPRESSION = 0.3
# Open minutes in a typical day of each market (the regimes' macro clock).
_OPEN_MINUTES_PER_DAY = {MarketType.CRYPTO: 1440, MarketType.FOREX: 1440, MarketType.STOCKS: 390}
_MEAN_ABS_Z = float(np.sqrt(2.0 / np.pi))
_UNIT_UNIFORM = float(np.sqrt(12.0))  # scales U(-1/2, 1/2) to unit variance
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
    spell_left: float = 0.0  # open minutes left in the current regime spell
    noise: np.ndarray | None = None  # (Fa,) microstructure noise of the last close
    slow: np.ndarray | None = None  # (Fa,) log slow volatility of each active factor


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
        self._next_calm = np.asarray(rp.jump_rows(False))
        self._next_stressed = np.asarray(rp.jump_rows(True))
        self._spell_minutes = np.asarray(rp.mean_minutes())
        self._spell_shape = float(rp.spell_shape)
        self._break_hazard = 1.0 / float(rp.minutes_per_step)
        r0 = rp.get_regime_index(rp.initial_regime)
        self._regime_drift, self._regime_vol = normalised_spell_targets(
            rp, _OPEN_MINUTES_PER_DAY[spec.market]
        )

        # ---- active subset: the selected instruments and their factors ----
        pegs = market_pegs(spec)
        self._projection = Projection.build(
            structure, inst, spec.factor_correlation, extra=lambda needed: peg_factors(pegs, needed)
        )
        fa = self._projection.factors
        self._factors = fa
        self._all_factors = fa.size == self._n_factors and bool(np.all(fa == np.arange(fa.size)))
        self._inst = inst
        self._all_instruments = inst.size == self._n_instruments and bool(
            np.all(inst == np.arange(inst.size))
        )
        self._sigma = sigma[fa]
        self._mu = mu[fa]
        # The pegs whose currency is simulated, in active-factor positions.
        position = {int(f): k for k, f in enumerate(fa)}
        live = [peg for peg in pegs if peg.held in position]
        self._pegs = (
            np.array([position[peg.held] for peg in live], dtype=np.int64),
            np.array([peg.vector[fa] for peg in live]).reshape(len(live), fa.size),
            np.array([peg.centre for peg in live]),
            np.array([peg.half_width for peg in live]),
            np.array([peg.pull for peg in live]),
        )
        # A trend moves the market's main factor: each series by its volatility
        # times its loading on that factor (ADR 0013).
        # In forex the main factor is the dollar: trend_up is the dollar falling.
        portfolio = dollar_portfolio(structure.factors) if spec.market == MarketType.FOREX else None
        loadings = main_factor_loadings(spec.factor_correlation, portfolio)
        self._trend = (sigma * loadings)[fa]
        # Stress pulls shocks onto the same factor, with loadings stretched
        # towards 0.95 for every series: co-movement intensifies.
        self._stress = np.asarray(rp.stress, dtype=float)
        relative = loadings / np.max(np.abs(loadings))
        self._stress_loading = (
            STRESS_LOADING * np.sign(relative) * np.abs(relative) ** STRESS_COMPRESSION
        )[fa]
        # The world: the market's global direction tied to the global shock
        # (ADR 0016), its main factor for coins and stocks, risk for forex.
        direction = (
            forex_risk_direction(structure.factors) if spec.market == MarketType.FOREX else loadings
        )
        self._mixing = global_mixing(spec.factor_correlation, direction, d.global_coupling)
        self._noise = float(d.microstructure_noise)
        self._slow_std = float(d.slow_volatility)
        self._slow_phi = 0.5 ** (1.0 / float(d.slow_volatility_days))
        # The world's bull and bear markets move each factor along its share
        # of the global direction, by as much as the market is coupled to it.
        calm, bear = macro_trends(_OPEN_MINUTES_PER_DAY[spec.market])
        along = sigma * self._mixing.covariance * d.global_coupling[0]
        self._macro_mu = (along * calm)[fa], (along * bear)[fa]
        # Earnings events (stocks): the jump of each active factor's reports.
        self._reports = spec.market == MarketType.STOCKS
        daily = np.array([a.volatility for a in factors]) / np.sqrt(252.0)
        moves = np.array(
            [
                EARNINGS_MOVE_DAYS * v if a.earnings_move is None else a.earnings_move
                for a, v in zip(factors, daily, strict=True)
            ]
        )
        self._report_symbols = [structure.factors[i] for i in fa]
        self._report_days: dict[tuple[str, int], np.ndarray] = {}
        self._report_moves = moves[fa]
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

        # Prices are published on each instrument's tick.
        self.ticks = tick_grid(spec, selected)

        self._state = _State(
            log_price=np.log([a.start_price for a in factors])[fa],
            garch_variance=np.ones(fa.size),
            garch_shock=np.zeros(fa.size),
            regime=r0,
            drift_mult=float(self._regime_drift[r0]),
            vol_mult=float(self._regime_vol[r0]),
            volume_memory=np.zeros(inst.size),
            spell_left=float(self._spell_minutes[r0]),
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
            "spell_left": float(st.spell_left),
            "noise": None if st.noise is None else st.noise.tolist(),
            "slow": None if st.slow is None else st.slow.tolist(),
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
            spell_left=float(snapshot["spell_left"]),
            noise=None
            if snapshot.get("noise") is None
            else np.asarray(snapshot["noise"], dtype=float),
            slow=None
            if snapshot.get("slow") is None
            else np.asarray(snapshot["slow"], dtype=float),
            **arrays,
        )

    # ------------------------------------------------------------- helpers
    def _correlated(
        self, z: np.ndarray, chi2: np.ndarray, world: np.ndarray, stressed: bool
    ) -> np.ndarray:
        """Correlated shocks of the active factors, tied to the global shock ``world``.

        Always computed market-wide, then the active factors are taken.
        """
        full = correlated_shocks(z, chi2, self._cholesky, self._nu)
        full = self._mixing.apply(full, world, np.full(world.shape, stressed))
        return full if self._all_factors else np.ascontiguousarray(full[:, self._factors])

    def _select_factors(self, draws: np.ndarray, rows: np.ndarray) -> np.ndarray:
        """Rows ``rows`` and the active factors' columns of a market-wide draw."""
        if self._all_factors:
            return np.asarray(draws[rows])
        return np.asarray(draws[np.ix_(rows, self._factors)])

    def _select(self, draws: np.ndarray, rows: np.ndarray) -> np.ndarray:
        """Rows ``rows`` and the selected instruments' columns of a market-wide draw."""
        if self._all_instruments:
            return np.asarray(draws[rows])
        return np.asarray(draws[np.ix_(rows, self._inst)])

    def _day_rng(self, day: int, stream: int) -> np.random.Generator:
        seq = np.random.SeedSequence([self.seed, _MARKET_STREAM[self.spec.market], day, stream])
        return np.random.Generator(np.random.PCG64(seq))

    def _earnings(
        self,
        day: int,
        ts: np.ndarray,
        gap_rows: np.ndarray,
        gap: np.ndarray,
        prev_close_day: int | None,
    ) -> tuple[np.ndarray, np.ndarray]:
        """The day's volatility and gaps with earnings events: a jump at the
        first open after a report, and raised volatility for a few days."""
        today = int(self.calendar.local_minutes(ts[:1])[0] // 1440)
        boost = np.ones(self._sigma.size)
        jumps = np.zeros(self._sigma.size)
        draws = None
        for f, (symbol, move) in enumerate(
            zip(self._report_symbols, self._report_moves, strict=True)
        ):
            if move <= 0.0:
                continue
            last = self._last_report(symbol, today)
            if last is None:
                continue
            recent = [last]
            opened = self._next_session(recent[-1])
            boost[f] = float(volatility_boost(np.array([today - opened]))[0])
            if prev_close_day is not None and gap_rows.size and prev_close_day <= recent[-1]:
                if draws is None:  # one t draw per market factor, fixed shape
                    t = self._day_rng(day, 3).standard_t(EARNINGS_NU, self._n_factors)
                    draws = t[self._factors] * np.sqrt((EARNINGS_NU - 2.0) / EARNINGS_NU)
                jumps[f] = move * draws[f]
        if jumps.any():
            gap = gap.copy()
            gap[0] += jumps  # the session's first open is its first gap
        return boost, gap

    def _slow_volatility(self, day: int) -> np.ndarray:
        """Advance each factor's slow log volatility by a day; its multiplier, of mean square 1."""
        st = self._state
        if self._slow_std == 0.0:
            return np.ones(self._sigma.size)
        shock = self._day_rng(day, 5).standard_normal(self._n_factors)[self._factors]
        x = np.zeros(self._sigma.size) if st.slow is None else st.slow
        x = self._slow_phi * x + np.sqrt(1.0 - self._slow_phi**2) * self._slow_std * shock
        st.slow = x
        return np.asarray(np.exp(x - self._slow_std**2))

    def _last_report(self, symbol: str, today: int) -> int | None:
        """The latest report of ``symbol`` in the days before ``today`` whose effects last."""
        year = (today - 365) // 365
        key = (symbol, year)
        days = self._report_days.get(key)
        if days is None:  # three years of reports around this one, once
            first = (year * 365) - 400
            days = np.array(reports_between(symbol, first, first + 1600, self.calendar))
            self._report_days[key] = days
        k = int(np.searchsorted(days, today, side="left")) - 1
        if k < 0 or days[k] < today - BOOST_HORIZON - 4:
            return None
        return int(days[k])

    @functools.cache  # noqa: B019 - one simulator per market and run
    def _next_session(self, local_day: int) -> int:
        """The local day of the first session after ``local_day``."""
        nxt = local_day + 1
        while self.calendar.session_close_minute(np.array([nxt]))[0] == 0:
            nxt += 1
        return nxt

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
        m_stress = rng.standard_normal(MINUTES_PER_DAY)
        spell_lengths = rng.gamma(self._spell_shape, 1.0 / self._spell_shape, MINUTES_PER_DAY)

        stressed = macro_state(self.seed, day) == STRESSED
        world = global_shocks(self.seed, day)
        z = session.rows_of(
            self._correlated(
                z_all[session.rows], chi_all[session.rows], world[session.rows], stressed
            )
        )

        (
            regimes,
            drift_m,
            vol_m,
            st.regime,
            st.spell_left,
            st.drift_mult,
            st.vol_mult,
        ) = regime_spells(
            u_regime[rows],
            spell_lengths[rows],
            self._next_calm,
            self._next_stressed,
            self._spell_minutes,
            np.full(rows.size, stressed, dtype=np.int8),
            self._break_hazard,
            self._regime_drift,
            self._regime_vol,
            REGIME_SMOOTHING,
            st.regime,
            st.spell_left,
            st.drift_mult,
            st.vol_mult,
        )
        stress = self._stress[regimes]
        if stress.any():  # a day of calm regimes needs no stress shocks at all
            scale = (
                np.sqrt((nu - 2.0) / nu) / np.sqrt(chi_all[rows] / nu)
                if self._nu is not None
                else np.ones(rows.size)
            )
            # The stress shock is the world's as much as the market's own: in
            # a sell-off, every market's common move is partly the same move.
            c = self._mixing.coupling[STRESSED if stressed else 0]
            shared = global_stress_shocks(self.seed, day)[rows]
            common = c * shared + np.sqrt(1.0 - c * c) * m_stress[rows]
            z = stressed_shocks(z, stress, scale, common, self._stress_loading)
        h, st.garch_variance, st.garch_shock = gjr_garch(
            z, *self._garch, st.garch_variance, st.garch_shock
        )
        season, volume_season = self.seasonality.factor_and_volume_log(ts)

        # Gaps after closures: at most a few rows a day.
        # intp, not int64: it is what np.nonzero returns below, so both paths
        # hand factor_paths the same dtype. The explicit annotation keeps mypy
        # from pinning the narrower type inferred from this placeholder.
        gap_rows: np.ndarray = np.empty(0, dtype=np.intp)
        gap = np.empty((0, self._sigma.size))
        prev_close_day = (
            None
            if st.last_timestamp is None
            else int(self.calendar.local_minutes(np.array([st.last_timestamp]))[0] // 1440)
        )
        if st.last_timestamp is not None:
            prev = np.concatenate(([st.last_timestamp], ts[:-1]))
            closed = (ts - prev) // 60 - 1
            gap_rows = np.nonzero(closed > 0)[0]
            if gap_rows.size > _MAX_GAPS_PER_DAY:
                raise RuntimeError("calendar produced more session opens in a day than supported")
            if gap_rows.size:
                k = gap_rows.size
                # What the world did while the market was shut reaches its gap.
                closed_world = np.array(
                    [
                        closure_shock(self.seed, int(p // 60) + 1, int(t // 60) - 1)
                        for p, t in zip(prev[gap_rows], ts[gap_rows], strict=True)
                    ]
                )
                zg = self._correlated(z_gap[:k], chi_gap[:k], closed_world, stressed)
                var_units = closure_variance(closed[gap_rows], self.spec.defaults)
                level = np.sqrt(h[gap_rows]) * vol_m[gap_rows, None]
                gap = (
                    self._sigma * level * np.sqrt(var_units)[:, None] * zg
                    + self._mu * var_units[:, None]
                )

        start_log_price = st.log_price
        sigma = self._sigma * self._slow_volatility(day)
        if self._reports:
            boost, gap = self._earnings(day, ts, gap_rows, gap, prev_close_day)
            sigma = sigma * boost
        # Factor paths, then instruments.
        sigma_f, returns_f, log_open_f, log_close_f = factor_paths(
            h,
            vol_m,
            drift_m,
            season,
            z,
            sigma,
            self._mu + self._macro_mu[int(stressed)],
            self._trend,
            gap_rows,
            gap,
            st.log_price,
        )
        if self._pegs[0].size:
            pull_to_pegs(log_open_f, log_close_f, returns_f, start_log_price, *self._pegs)
        st.log_price = log_close_f[-1].copy()  # the efficient price carries on
        if self._noise > 0.0:
            # Quotes jitter around the efficient price; each open is still
            # the previous close (plus any gap).
            # Uniform of unit variance, in float32: a quote's jitter needs no
            # normal tail nor double precision, and this costs a tenth of a
            # market-wide day of normals.
            draw = self._day_rng(day, 4).random((MINUTES_PER_DAY, self._n_factors), np.float32)
            eta = (self._noise * _UNIT_UNIFORM) * sigma_f * (self._select_factors(draw, rows) - 0.5)
            before = np.empty_like(eta)
            before[0] = 0.0 if st.noise is None else st.noise
            before[1:] = eta[:-1]
            log_close_f = log_close_f + eta
            log_open_f = log_open_f + before
            returns_f = returns_f + (eta - before)
            st.noise = eta[-1].copy()
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
            self.spec.defaults.intrabar_body_share,
            np.log(1.0 - self._select(u_high, rows)),
            np.log(1.0 - self._select(u_low, rows)),
            self._sigma_ref,
            season,
            prices,
            level_i,
        )
        np.exp(prices, out=prices)  # open, close, bridge high, bridge low
        log_volume_season = np.log(season) + volume_season
        np.log(level_i, out=level_i)
        phi, lam, kappa = self._volume
        high, low, volume = finish_bars(
            prices,
            body,
            sigma_i,
            level_i,
            log_volume_season,
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
        # On the tick grid: rounding is monotone, so high and low still bound
        # open and close, and each open still equals the previous close.
        for name in ("open", "high", "low", "close"):
            setattr(result, name, self.ticks.round(getattr(result, name)))
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
