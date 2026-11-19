# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

"""Fit every built-in market's correlation matrices and write them into the package.

Run after changing a catalog's stated correlations or volatilities, or the
model (a new MODEL_REVISION):

    python scripts/fit_correlations.py               # every market, ~15 minutes
    python scripts/fit_correlations.py --markets crypto

Two fits, written to ``fitted_correlation.json`` beside each catalog:

1. **Daily**: the valid matrix closest to the stated correlations (ADR 0012).
   It prints how far the fit moved the stated pairs, so a change that the
   rest of the catalog contradicts is visible.
2. **Minute**: the matrix of the minute shocks whose simulated daily returns
   correlate as the daily matrix says (ADR 0018). The regimes' common trends
   and stress shocks correlate daily returns more than minute shocks, so it
   is found by simulation: simulate years of the market with a candidate,
   measure its daily correlations, move the candidate by the error, repeat.
   The same seeds every time, so the error is a smooth function of the
   candidate and the iteration converges instead of chasing noise.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np

from marketforge.config.catalog.correlation import (
    STATED_WEIGHT,
    implied_correlation,
    nearest_correlation,
)
from marketforge.config.catalog.crypto import instruments as crypto_instruments
from marketforge.config.catalog.fitted import FILE_NAME, document, fit, fit_problem
from marketforge.config.catalog.forex import instruments as forex_instruments
from marketforge.config.catalog.schema import MarketConfig
from marketforge.config.catalog.stocks import instruments as stocks_instruments
from marketforge.domain.markets import MarketType
from marketforge.simulation.simulator import MarketSimulator
from marketforge.simulation.spec import build_market_spec

CATALOG = Path(__file__).resolve().parents[1] / "marketforge" / "config" / "catalog"
_INSTRUMENTS = {
    MarketType.CRYPTO: crypto_instruments.INSTRUMENTS,
    MarketType.FOREX: forex_instruments.INSTRUMENTS,
    MarketType.STOCKS: stocks_instruments.INSTRUMENTS,
}
_FIRST_DAY = 14_610  # 2010-01-01


def daily_correlation(
    market: MarketType, factors: np.ndarray, seeds: int, years: int
) -> np.ndarray:
    """The correlations of daily returns the simulator gives the market's factors."""
    p = fit_problem(market)
    full = (
        factors
        if p.structure.is_identity
        else implied_correlation(factors, p.structure.weights, p.scales)[0]
    )
    spec = build_market_spec(
        MarketConfig(market, _INSTRUMENTS[market], (full + full.T) / 2, list(p.symbols))
    )
    days = range(_FIRST_DAY, _FIRST_DAY + 365 * years)
    start, end = days[0] * 86_400, (days[-1] + 1) * 86_400
    matrices = []
    for seed in range(seeds):
        sim = MarketSimulator(spec, seed, list(p.structure.factors))
        closes = [bars.close[-1] for day in days if (bars := sim.simulate_day(day, start, end))]
        returns = np.diff(np.log(np.array(closes)), axis=0)
        matrices.append(np.corrcoef(returns.T))
    return np.asarray(np.mean(matrices, axis=0))


def fit_minute(
    market: MarketType, daily: np.ndarray, iterations: int, seeds: int, years: int
) -> np.ndarray:
    """The minute matrix whose simulated daily correlations are ``daily``."""
    off = ~np.eye(len(daily), dtype=bool)
    minute = daily.copy()
    best, best_error = minute, np.inf
    for k in range(iterations):
        t = time.time()
        error = daily_correlation(market, minute, seeds, years) - daily
        size = float(np.abs(error[off]).mean())
        print(
            f"  minute fit {k}: daily correlations off by {error[off].mean():+.3f} on average, "
            f"{size:.3f} in absolute value, {np.abs(error[off]).max():.3f} at most ({time.time() - t:.0f}s)",
            flush=True,
        )
        if size < best_error:
            best, best_error = minute, size
        minute, _ = nearest_correlation(minute - error)
    return best


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--markets", default="crypto,forex,stocks")
    parser.add_argument("--iterations", type=int, default=5)
    parser.add_argument("--seeds", type=int, default=3)
    parser.add_argument("--years", type=int, default=10)
    args = parser.parse_args()
    for market in map(MarketType, args.markets.split(",")):
        p = fit_problem(market)
        c = fit(market)
        corr, vol = implied_correlation(c, p.structure.weights, p.scales)
        stated = (p.weight == STATED_WEIGHT) & ~np.eye(len(p.symbols), dtype=bool)  # anchors only
        moved = np.abs(corr - p.target)[stated]
        i, j = np.unravel_index(np.argmax(np.where(stated, np.abs(corr - p.target), 0)), corr.shape)
        print(
            f"{market.value}: {stated.sum() // 2} stated pairs, mean shift {moved.mean():.3f}, "
            f"largest {p.symbols[i]}-{p.symbols[j]} {p.target[i, j]:+.2f} -> {corr[i, j]:+.2f}; "
            f"min eigenvalue {np.linalg.eigvalsh(c).min():.2e}",
            flush=True,
        )
        derived = p.vol_weight > 0
        if derived.any():
            ratio = vol[derived] / p.vol_target[derived]
            print(f"  crosses: implied / stated volatility {ratio.min():.2f} to {ratio.max():.2f}")
        path = CATALOG / market.value / FILE_NAME
        path.write_text(document(market, c), encoding="utf-8")  # loadable while the minute fit runs
        minute = fit_minute(market, c, args.iterations, args.seeds, args.years)
        off = ~np.eye(len(c), dtype=bool)
        print(f"  minute correlations {np.mean(minute[off] - c[off]):+.3f} on average", flush=True)
        path.write_text(document(market, c, minute), encoding="utf-8")


if __name__ == "__main__":
    main()
