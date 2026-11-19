# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

"""
Model parameter types shared by every market.

Per-market values live in :mod:`marketforge.config.defaults`; per-instrument
values (start price, volatility, drift, volume) live in the catalogs.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from marketforge.domain.anomalies import AnomalyType
from marketforge.domain.regimes import RegimeType


@dataclass(frozen=True)
class GARCHParams:
    """
    GJR-GARCH(1,1) parameters of the per-minute volatility multiplier.

        h_t = (1 - p) + (alpha + gamma * 1[e_{t-1} < 0]) * e_{t-1}^2 + beta * h_{t-1}

    with persistence p = alpha + beta + gamma / 2 < 1, so h has mean 1 and
    the configured annual volatility is preserved. ``gamma`` is the leverage
    effect: down-moves raise volatility more than up-moves.
    """

    alpha: float = 0.05
    beta: float = 0.90
    gamma: float = 0.0

    def __post_init__(self) -> None:
        for name in ("alpha", "beta", "gamma"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be non-negative, got {getattr(self, name)}")
        if self.persistence >= 1:
            raise ValueError(
                f"alpha + beta + gamma/2 must be < 1 for stationarity, got {self.persistence}"
            )

    @property
    def persistence(self) -> float:
        return self.alpha + self.beta + self.gamma / 2.0


@dataclass(frozen=True)
class RegimeParams:
    """
    Regime-switching parameters: a semi-Markov chain of spells.

    The transition matrix applies once per ``minutes_per_step`` open minutes:
    regime *i* lasts ``minutes_per_step / (1 - P[i][i])`` open minutes on
    average, and leaves for *j* with probability ``P[i][j] / (1 - P[i][i])``.
    A spell's length is that mean times a Gamma(``spell_shape``) draw of mean
    1: a typical length rather than the memoryless one of a Markov chain
    (shape 1), so a regime detector cannot assume every minute is as likely
    as the last to end a spell. While the macro state is stressed, the next
    regime is drawn with ``stressed_tilt`` weighing each destination, and a
    calm spell ends early with a per-minute probability of 1 /
    ``minutes_per_step``. Volatility multipliers are rescaled by the simulator so that their
    long-run mean square is 1, and trends so that their long-run mean is 0:
    regimes reshape *when* volatility and returns happen, not how much, so the
    catalog's annual volatility and drift are what you get.

    A regime's trend is the expected log return over an average spell of the
    regime, divided by the spell's own volatility: +1.0 means a spell of
    ``trend_up`` ends higher about 84% of the time (Phi(1)), before the
    centering that keeps the long-run drift at the catalog's. It moves the
    market's main factor, so instruments trend together in the direction of
    their correlation with it (in forex, EURUSD and USDCHF trend opposite ways).

    Attributes:
        transition_matrix: Rows = current regime, columns = next regime, in
            :class:`RegimeType` order.
        minutes_per_step: Open minutes per transition step (time scale).
        trend_strength: Expected return of an average spell of each regime, in
            units of that spell's volatility, along the market's main factor.
        stress: Weight of a common shock on the market's main factor, added to
            every shock in each regime: correlations intensify (diversification
            fails in sell-offs). 0 keeps the catalog correlations.
        volatility_multipliers: Volatility scaling per regime.
        initial_regime: Regime at the first simulated minute.
    """

    transition_matrix: tuple[tuple[float, ...], ...] = (
        (0.85, 0.03, 0.08, 0.03, 0.01),
        (0.03, 0.85, 0.08, 0.03, 0.01),
        (0.10, 0.10, 0.70, 0.08, 0.02),
        (0.05, 0.10, 0.15, 0.65, 0.05),
        (0.05, 0.05, 0.10, 0.30, 0.50),
    )
    trend_strength: tuple[float, ...] = (1.0, -1.4, 0.0, -0.3, -1.5)
    volatility_multipliers: tuple[float, ...] = (0.8, 0.8, 0.6, 2.0, 4.0)
    initial_regime: RegimeType = RegimeType.RANGE
    minutes_per_step: float = 1.0
    stress: tuple[float, ...] = (0.0, 0.0, 0.0, 0.4, 0.75)
    spell_shape: float = 2.0
    # Weight of each next regime while the macro state is stressed: sell-offs.
    stressed_tilt: tuple[float, ...] = (0.5, 1.5, 0.7, 3.0, 4.0)

    def __post_init__(self) -> None:
        if self.minutes_per_step < 1.0:
            raise ValueError(f"minutes_per_step must be >= 1, got {self.minutes_per_step}")
        if self.spell_shape <= 0.0:
            raise ValueError(f"spell_shape must be positive, got {self.spell_shape}")

    def mean_minutes(self) -> list[float]:
        """Mean spell length of each regime, in open minutes."""
        p, m = self.transition_matrix, self.minutes_per_step
        return [m / max(1.0 - p[i][i], 1e-12) for i in range(len(p))]

    def jump_rows(self, stressed: bool = False) -> list[list[float]]:
        """Cumulative rows of the next regime once a spell ends (zero diagonal)."""
        p = self.transition_matrix
        tilt = self.stressed_tilt if stressed else (1.0,) * len(p)
        rows = []
        for i in range(len(p)):
            weights = [0.0 if j == i else p[i][j] * tilt[j] for j in range(len(p))]
            total = sum(weights) or 1.0
            cumulative, running = [], 0.0
            for w in weights:
                running += w / total
                cumulative.append(running)
            cumulative[-1] = 1.0
            rows.append(cumulative)
        return rows

    def per_minute_matrix(self) -> list[list[float]]:
        """Transition matrix for one open minute."""
        p, m = self.transition_matrix, self.minutes_per_step
        return [
            [
                (1.0 if i == j else 0.0) + (p[i][j] - (1.0 if i == j else 0.0)) / m
                for j in range(len(p))
            ]
            for i in range(len(p))
        ]

    def get_regime_index(self, regime: RegimeType) -> int:
        return list(RegimeType).index(regime)


@dataclass(frozen=True)
class VolumeParams:
    """
    Log-volume AR(1) parameters:

        log V_t = log base + phi * y_{t-1} + lam * (|z_t| - E|z|)
                  + kappa * log(turbulence_t) + log s(t) + sigma_eta * eta_t

    where sigma_eta = volume_volatility * sqrt(1 - phi^2) uses each instrument's
    catalog ``volume_volatility`` (the lognormal sigma of its volume noise).

    Attributes:
        phi: Persistence of log-volume (volume clustering), 0 <= phi < 1.
        lam: Response to the size of the current standardized move.
        kappa: Elasticity to the volatility level (GARCH x regime): volume
            rises while the market is turbulent, not only on the big minute.
    """

    phi: float = 0.7
    lam: float = 0.3
    kappa: float = 0.5

    def __post_init__(self) -> None:
        if not (0.0 <= self.phi < 1.0):
            raise ValueError(f"phi must be in [0, 1), got {self.phi}")
        if self.lam < 0:
            raise ValueError(f"lam must be non-negative, got {self.lam}")
        if self.kappa < 0:
            raise ValueError(f"kappa must be non-negative, got {self.kappa}")


@dataclass(frozen=True)
class SpreadParams:
    """
    Quoted bid-ask spread around the mid price (see docs/adr/0008).

    Per minute and instrument, as a fraction of the price:

        spread_t = base * turbulence_t ** turbulence_exponent
                   / s(t) ** liquidity_exponent
                   * (1 + reopen_widening * exp(-(m_t - 1) / reopen_minutes))
                   * lognormal noise

    where m_t counts the open minutes since the market last reopened, and the
    result is never below one ``tick`` in price units. With ``fixed_scale`` the
    fraction applies to the instrument's start price instead of its current
    price: the spread is a number of price increments that does not shrink
    when the price falls.

    ``base`` is the instrument's catalog ``spread_bps``. Instruments without
    one get ``reference_bps * (volatility / reference_volatility) **
    volatility_exponent * price ** price_exponent``, at least ``minimum_bps``.
    In forex and stocks the more volatile instruments are the less liquid
    ones, and the levels are estimates, not measurements. In crypto the spread
    is pinned to the exchange's tick, which is coarser, relative to the price,
    the cheaper the coin; that rule is fitted to measured quotes.

    Attributes:
        reference_bps: Default spread, in basis points of the price, of an
            instrument whose annual volatility is ``reference_volatility``.
        reference_volatility: See ``reference_bps``.
        volatility_exponent: How fast the default spread grows with volatility.
        price_exponent: How the default spread, in basis points, depends on
            the instrument's price (negative: cheap instruments are wider).
        minimum_bps: Floor of the default spread.
        tick: Smallest quoted spread in price units (one cent for US stocks).
        fixed_scale: Quote the spread against the start price, not the current one.
        turbulence_exponent: Elasticity to the volatility level (GARCH x regime).
        liquidity_exponent: Elasticity to intraday seasonality: spreads widen
            in the quiet hours.
        reopen_widening: Extra width, as a multiple, in the first minute after
            a closure.
        reopen_minutes: Decay time of that extra width, in minutes.
        noise: Lognormal sigma of the minute-to-minute noise.
    """

    reference_bps: float
    reference_volatility: float
    volatility_exponent: float
    minimum_bps: float
    price_exponent: float = 0.0
    tick: float = 0.0
    fixed_scale: bool = False
    turbulence_exponent: float = 0.5
    liquidity_exponent: float = 0.5
    reopen_widening: float = 0.0
    reopen_minutes: float = 1.0
    noise: float = 0.25

    def __post_init__(self) -> None:
        for name in ("reference_bps", "reference_volatility", "minimum_bps", "reopen_minutes"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive, got {getattr(self, name)}")
        for name in ("tick", "reopen_widening", "noise"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be non-negative, got {getattr(self, name)}")

    def default_bps(self, volatility: float, price: float) -> float:
        """Spread, in basis points, of an instrument that does not set its own."""
        scaled = (
            self.reference_bps
            * (volatility / self.reference_volatility) ** self.volatility_exponent
            * price**self.price_exponent
        )
        return float(max(self.minimum_bps, scaled))


@dataclass(frozen=True)
class AnomalyConfig:
    """
    Anomaly settings for a market.

    Attributes:
        types: Anomalies to inject (none by default).
        spike_probability: Chance per candle and instrument of a long wick.
        spike_magnitude_range: Wick length as a fraction of price.
        flash_crash_probability: Chance per day and instrument of a flash crash.
        flash_crash_magnitude: Depth of the crash as a fraction of price.
        flash_crash_recovery_candles: Duration of drop + floor + recovery.
    """

    types: frozenset[AnomalyType] = field(default_factory=frozenset)
    spike_probability: float = 0.0005
    spike_magnitude_range: tuple[float, float] = (0.02, 0.10)
    flash_crash_probability: float = 0.001
    flash_crash_magnitude: float = 0.15
    flash_crash_recovery_candles: int = 30
