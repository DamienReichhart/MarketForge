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

import numpy as np

from marketforge.config.settings import MarketType
from marketforge.validation import stylized_facts as sf
from marketforge.validation.reference import bands_for


@dataclass
class MetricResult:
    name: str
    value: float
    low: float | None
    high: float | None
    passed: bool


@dataclass
class ValidationReport:
    market_type: MarketType
    metrics: dict[str, MetricResult] = field(default_factory=dict)

    def get(self, name: str) -> MetricResult | None:
        return self.metrics.get(name)

    @property
    def passed(self) -> bool:
        return all(m.passed for m in self.metrics.values())

    def summary(self) -> str:
        anchored = bands_for(self.market_type).anchored
        lines = [
            f"Validation report ({self.market_type.value}): "
            f"{'PASS' if self.passed else 'FAIL'}"
            + (
                ""
                if anchored
                else "  [provisional bands: no real-data reference for this market yet]"
            )
        ]
        for m in self.metrics.values():
            band = f"[{m.low}, {m.high}]"
            flag = "ok " if m.passed else "FAIL"
            lines.append(f"  {flag} {m.name}={m.value:.4f} target {band}")
        return "\n".join(lines)


def _check(name, value, low, high) -> MetricResult:
    ok = True
    if low is not None and value < low:
        ok = False
    if high is not None and value > high:
        ok = False
    return MetricResult(name=name, value=value, low=low, high=high, passed=ok)


def validate_returns(returns: np.ndarray, market_type: MarketType) -> ValidationReport:
    """Validate a 1-D m1 return series against the market's bands."""
    report = ValidationReport(market_type=market_type)
    r = np.asarray(returns, dtype=float)
    bands = bands_for(market_type)

    report.metrics["excess_kurtosis"] = _check(
        "excess_kurtosis", sf.excess_kurtosis(r), *bands.excess_kurtosis
    )
    report.metrics["vol_clustering"] = _check(
        "vol_clustering", sf.volatility_clustering_strength(r), bands.vol_clustering_min, None
    )
    # Allow two standard errors of sampling noise (~1/sqrt(n)): two weeks of
    # stock minutes is only ~3,900 returns, where noise alone reaches 0.03.
    ceiling = bands.leverage_max + 2.0 / np.sqrt(max(r.size, 1))
    report.metrics["leverage"] = _check(
        "leverage", sf.leverage_correlation(r), None, round(ceiling, 4)
    )
    # Volatility memory beyond GARCH's minutes: |r| autocorrelation at 1 hour,
    # with the same two-standard-error allowance for short samples.
    if r.size > 600:
        floor = bands.long_memory_min - 2.0 / np.sqrt(r.size)
        report.metrics["long_memory"] = _check(
            "long_memory", sf._acf(np.abs(r), 60), round(floor, 4), None
        )
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
        "range_efficiency",
        sf.range_efficiency(open_, high, low, close),
        *bands_for(market_type).range_efficiency,
    )
    return report
