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
_KURTOSIS_BANDS = {
    MarketType.CRYPTO: (2.0, 60.0),
    MarketType.STOCKS: (1.5, 40.0),
    MarketType.FOREX: (1.0, 50.0),
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

    report.metrics["leverage"] = _check(
        "leverage", sf.leverage_correlation(r), None, 0.02)

    return report


def validate_ohlcv(open_, high, low, close, market_type: MarketType) -> ValidationReport:
    """Validate an OHLC series: return-based facts plus range efficiency."""
    report = validate_returns(sf.log_returns(close), market_type)
    report.metrics["range_efficiency"] = _check(
        "range_efficiency", sf.range_efficiency(open_, high, low, close), 1.0, 6.0)
    return report
