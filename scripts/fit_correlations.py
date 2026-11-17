# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

"""Fit every built-in market's correlation matrix and write it into the package.

Run after changing a catalog's stated correlations or volatilities:

    python scripts/fit_correlations.py

It prints how far the fit moved the stated pairs, so a change that the rest
of the catalog contradicts is visible.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from marketforge.config.catalog.correlation import STATED_WEIGHT, implied_correlation
from marketforge.config.catalog.fitted import FILE_NAME, document, fit, fit_problem
from marketforge.domain.markets import MarketType

CATALOG = Path(__file__).resolve().parents[1] / "marketforge" / "config" / "catalog"


def main() -> None:
    for market in MarketType:
        p = fit_problem(market)
        c = fit(market)
        corr, vol = implied_correlation(c, p.structure.weights, p.scales)
        stated = (p.weight == STATED_WEIGHT) & ~np.eye(len(p.symbols), dtype=bool)  # anchors only
        moved = np.abs(corr - p.target)[stated]
        i, j = np.unravel_index(np.argmax(np.where(stated, np.abs(corr - p.target), 0)), corr.shape)
        print(
            f"{market.value}: {stated.sum() // 2} stated pairs, mean shift {moved.mean():.3f}, "
            f"largest {p.symbols[i]}-{p.symbols[j]} {p.target[i, j]:+.2f} -> {corr[i, j]:+.2f}; "
            f"min eigenvalue {np.linalg.eigvalsh(c).min():.2e}"
        )
        derived = p.vol_weight > 0
        if derived.any():
            ratio = vol[derived] / p.vol_target[derived]
            print(f"  crosses: implied / stated volatility {ratio.min():.2f} to {ratio.max():.2f}")
        (CATALOG / market.value / FILE_NAME).write_text(document(market, c), encoding="utf-8")


if __name__ == "__main__":
    main()
