# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the MIT License. See the LICENSE file in the project
# root for full license information.

"""
Validation report: run stylized-fact metrics against per-market target bands.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
import numpy as np

from marketforge.config.settings import MarketType
from marketforge.validation import stylized_facts as sf


@dataclass
class MetricResult:
    name: str
    value: float
    low: Optional[float]
    high: Optional[float]
    passed: bool


@dataclass
class ValidationReport:
    market_type: MarketType
    metrics: dict[str, MetricResult] = field(default_factory=dict)

    def get(self, name: str) -> Optional[MetricResult]:
        return self.metrics.get(name)

    @property
    def passed(self) -> bool:
        return all(m.passed for m in self.metrics.values())

    def summary(self) -> str:
        lines = [f"Validation report ({self.market_type.value}): "
                 f"{'PASS' if self.passed else 'FAIL'}"]
        for m in self.metrics.values():
            band = f"[{m.low}, {m.high}]"
            flag = "ok " if m.passed else "FAIL"
            lines.append(f"  {flag} {m.name}={m.value:.4f} target {band}")
        return "\n".join(lines)


# Per-market target bands for m1 log-returns.
# (low, high); None = unbounded on that side.
# The lower bound is the meaningful fat-tail check (tails must be heavy enough);
# the upper bound only guards against pathological blow-ups. Sample excess
# kurtosis grows with sample length, and real high-frequency FX/m1 returns are
# strongly leptokurtic, so the ceilings are deliberately generous.
# Crypto shocks are Student-t with 5 degrees of freedom, whose sample kurtosis
# is dominated by a handful of minutes; real BTC m1 data routinely shows
# excess kurtosis near 100 over a few weeks.
_KURTOSIS_BANDS = {
    MarketType.CRYPTO: (2.0, 150.0),
    MarketType.STOCKS: (1.5, 40.0),
    MarketType.FOREX: (1.0, 50.0),
}


# Equities and crypto show a clear leverage effect (down-moves raise
# volatility). FX has no natural "down": EURAUD rises when AUD sells off, so
# crosses legitimately show mildly positive values. Only strong positive
# leverage is rejected there.
_LEVERAGE_CEILING = {
    MarketType.CRYPTO: 0.02,
    MarketType.STOCKS: 0.02,
    MarketType.FOREX: 0.08,
}


def _check(name, value, low, high) -> MetricResult:
    ok = True
    if low is not None and value < low:
        ok = False
    if high is not None and value > high:
        ok = False
    return MetricResult(name=name, value=value, low=low, high=high, passed=ok)


def validate_returns(returns: np.ndarray, market_type: MarketType) -> ValidationReport:
    """Validate a 1-D return series against the market's target bands."""
    report = ValidationReport(market_type=market_type)
    r = np.asarray(returns, dtype=float)

    k_low, k_high = _KURTOSIS_BANDS[market_type]
    report.metrics["excess_kurtosis"] = _check(
        "excess_kurtosis", sf.excess_kurtosis(r), k_low, k_high)

    report.metrics["vol_clustering"] = _check(
        "vol_clustering", sf.volatility_clustering_strength(r), 0.02, None)

    # Allow two standard errors of sampling noise (~1/sqrt(n)): two weeks of
    # stock minutes is only ~3,900 returns, where noise alone reaches 0.03.
    ceiling = _LEVERAGE_CEILING[market_type] + 2.0 / np.sqrt(max(r.size, 1))
    report.metrics["leverage"] = _check(
        "leverage", sf.leverage_correlation(r), None, round(ceiling, 4))

    return report


def validate_ohlcv(open_, high, low, close, market_type: MarketType) -> ValidationReport:
    """
    Validate an OHLC series: return-based facts plus range efficiency.

    Return-based facts use each candle's open-to-close log return. Within a
    session that equals the close-to-close return; across a market closure it
    leaves out the overnight/weekend gap, which would otherwise dominate the
    kurtosis of minute data (one gap ~10 minute-sizes wide per session).
    """
    r = np.log(np.asarray(close, dtype=float) / np.asarray(open_, dtype=float))
    report = validate_returns(r, market_type)
    report.metrics["range_efficiency"] = _check(
        "range_efficiency", sf.range_efficiency(open_, high, low, close), 1.0, 6.0)
    return report
