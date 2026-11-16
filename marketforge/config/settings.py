# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the MIT License. See the LICENSE file in the project
# root for full license information.

"""
Model parameter types shared by every market.

Per-market values live in :mod:`marketforge.config.defaults`; per-instrument
values (start price, volatility, drift, volume) live in the catalogs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class MarketType(StrEnum):
    """A market: a family of instruments sharing one calendar and one regime path."""

    CRYPTO = "crypto"
    FOREX = "forex"
    STOCKS = "stocks"


class AnomalyType(StrEnum):
    """Optional, deliberately unrealistic events layered on the simulation."""

    SPIKES = "spikes"
    FLASH_CRASH = "flash_crash"


class RegimeType(StrEnum):
    """Market-wide regimes, in the order used by regime parameters and labels."""

    TREND_UP = "trend_up"
    TREND_DOWN = "trend_down"
    RANGE = "range"
    HIGH_VOLATILITY = "high_volatility"
    CRASH = "crash"


_REGIME_ORDER = list(RegimeType)


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
    Markov regime-switching parameters.

    The transition matrix applies once per ``minutes_per_step`` open minutes;
    the engine runs the equivalent per-minute chain, I + (P - I) / minutes_per_step,
    so regime *i* lasts ``minutes_per_step / (1 - P[i][i])`` open minutes on
    average. Multipliers are rescaled by the engine so that, over the long run,
    the mean drift multiplier is 1 and the mean squared volatility multiplier
    is 1: regimes reshape *when* drift and volatility happen, not how much.

    Attributes:
        transition_matrix: Rows = current regime, columns = next regime, in
            :class:`RegimeType` order.
        minutes_per_step: Open minutes per transition step (time scale).
        drift_multipliers: Drift scaling per regime.
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
    drift_multipliers: tuple[float, ...] = (2.0, -2.0, 0.0, 0.0, -5.0)
    volatility_multipliers: tuple[float, ...] = (0.8, 0.8, 0.6, 2.0, 4.0)
    initial_regime: RegimeType = RegimeType.RANGE
    minutes_per_step: float = 1.0

    def __post_init__(self) -> None:
        if self.minutes_per_step < 1.0:
            raise ValueError(f"minutes_per_step must be >= 1, got {self.minutes_per_step}")

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
        return _REGIME_ORDER.index(regime)


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
