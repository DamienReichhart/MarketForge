# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

"""
Validation report: run stylized-fact metrics against per-market target bands.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from marketforge.domain.markets import MarketType
from marketforge.validation import stylized_facts as sf
from marketforge.validation.reference import bands_for


@dataclass
class MetricResult:
    name: str
    value: float
    low: float | None
    high: float | None
    passed: bool
    provisional: bool = False  # its band is not anchored to real data


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
            flag = "ok  " if m.passed else "FAIL"
            note = ", provisional" if m.provisional and anchored else ""
            lines.append(
                f"  {flag} {m.name} = {m.value:.4f}  (expected {_band(m.low, m.high)}{note})"
            )
        return "\n".join(lines)


def _band(low: float | None, high: float | None) -> str:
    if low is None:
        return f"at most {high:g}"
    if high is None:
        return f"at least {low:g}"
    return f"{low:g} to {high:g}"


def _check(name, value, low, high, provisional: bool = False) -> MetricResult:
    ok = True
    if low is not None and not value >= low:
        ok = False
    if high is not None and not value <= high:
        ok = False
    return MetricResult(
        name=name, value=value, low=low, high=high, passed=ok, provisional=provisional
    )


def validate_returns(returns: np.ndarray, market_type: MarketType) -> ValidationReport:
    """Validate a 1-D m1 return series against the market's bands."""
    report = ValidationReport(market_type=market_type)
    r = np.asarray(returns, dtype=float)
    bands = bands_for(market_type)

    # Every band allows two standard errors of sampling noise on the side
    # where a short sample can fall out by chance. The standard errors come
    # from the sample's own moments, not from the normal-data formulas: two
    # weeks of stock minutes are only ~3,900 heavy-tailed returns.
    kurtosis_floor, kurtosis_ceiling = bands.excess_kurtosis
    if kurtosis_floor is not None:
        allowance = 2.0 * sf.excess_kurtosis_standard_error(r)
        kurtosis_floor = round(max(0.0, kurtosis_floor - allowance), 4)
    report.metrics["excess_kurtosis"] = _check(
        "excess_kurtosis", sf.excess_kurtosis(r), kurtosis_floor, kurtosis_ceiling
    )
    report.metrics["vol_clustering"] = _check(
        "vol_clustering", sf.volatility_clustering_strength(r), bands.vol_clustering_min, None
    )
    ceiling = bands.leverage_max + 2.0 * sf.leverage_standard_error(r)
    report.metrics["leverage"] = _check(
        "leverage", sf.leverage_correlation(r), None, round(ceiling, 4)
    )
    # Volatility memory beyond GARCH's minutes: |r| autocorrelation at 1 hour.
    if r.size > 600:
        floor = bands.long_memory_min - 2.0 * sf.abs_autocorrelation_standard_error(r, 60)
        report.metrics["long_memory"] = _check(
            "long_memory", sf._acf(np.abs(r), 60), round(floor, 4), None
        )
    return report


def validate_ohlcv(
    open_,
    high,
    low,
    close,
    market_type: MarketType,
    spread=None,
    volume=None,
    gaps=None,
    regime=None,
) -> ValidationReport:
    """
    Validate an OHLC series: return-based facts plus range efficiency, and the
    level and behaviour of the quoted spread when one is given. With
    ``volume``, the link between volume and the size of moves; with ``gaps``
    (the log moves over closures: overnight, weekend), their share of the
    variance; with ``regime`` codes, the spread of spell lengths.

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
    bands = bands_for(market_type)
    loose = not bands.extra_anchored
    if r.size > 1000:
        allowance = 2.0 / np.sqrt(r.size)
        low, high = bands.return_autocorrelation
        report.metrics["return_autocorrelation"] = _check(
            "return_autocorrelation",
            sf.return_autocorrelation(r),
            round(low - allowance, 4),
            round(high + allowance, 4),
            provisional=loose,
        )
        # A fortnight holds only ~70 stock hours: their kurtosis gets the
        # same two-standard-error allowance as the minutes' (ADR 0010), and
        # may fall below 0 by chance where the band's floor is 0.
        hours = sf.aggregated(r, 60)
        floor, ceiling = bands.hourly_kurtosis
        if hours.size >= 20:
            floor = round(floor - 2.0 * sf.excess_kurtosis_standard_error(hours), 4)
        report.metrics["hourly_kurtosis"] = _check(
            "hourly_kurtosis",
            sf.aggregated_kurtosis(r, 60),
            floor,
            ceiling,
            provisional=loose,
        )
    if volume is not None and np.mean(np.asarray(volume) > 0) > 0.95:
        report.metrics["volume_volatility"] = _check(
            "volume_volatility",
            sf.volume_volatility_link(r, volume),
            bands.volume_volatility_min,
            None,
            provisional=loose,
        )
    if gaps is not None and np.asarray(gaps).size >= 5:
        report.metrics["gap_variance_share"] = _check(
            "gap_variance_share",
            sf.gap_variance_share(r, gaps),
            *bands.gap_variance_share,
            provisional=True,
        )
    if regime is not None:
        variation = sf.spell_variation(regime)
        if np.isfinite(variation):
            spells = np.count_nonzero(np.diff(np.asarray(regime)) != 0)
            allowance = 2.0 * variation / np.sqrt(2.0 * spells)  # standard error of a CV
            low, high = bands.spell_variation
            report.metrics["spell_variation"] = _check(
                "spell_variation",
                variation,
                round(low - allowance, 4),
                round(high + allowance, 4),
                provisional=True,
            )
    if spread is not None:
        provisional = not bands.spread_anchored
        report.metrics["spread_bps"] = _check(
            "spread_bps",
            sf.median_spread_bps(spread, close),
            *bands.spread_bps,
            provisional=provisional,
        )
        report.metrics["spread_widening"] = _check(
            "spread_widening",
            sf.spread_widening(spread, r),
            *bands.spread_widening,
            provisional=provisional,
        )
    return report
