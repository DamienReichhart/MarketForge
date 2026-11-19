# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

"""
The fitted correlation matrices of each built-in market, shipped as data.

``fitted_correlation.json`` beside each market's catalog holds two matrices
of the market's factors and a digest of the problem they solve (the stated
correlations, the weights and the volatilities):

- ``daily``: the valid matrix closest to what the catalog states (see
  :mod:`marketforge.config.catalog.correlation`, ADR 0012). The catalog's
  correlations are those of daily returns, as real ones are measured.
- ``matrix``: the minute shocks' matrix the simulator uses, chosen so that
  the daily returns it simulates correlate as ``daily`` says. The regimes'
  common trends and stress shocks correlate daily returns more than minute
  shocks (ADR 0018), so it is the lower of the two.

``horizon`` maps daily correlations to minute ones (:func:`horizon_table`),
which turns an override file's correlations (daily, like the catalog's) into
the minute shocks' that give them. Loading checks the digest and the model revision the minute
matrix was fitted for, so editing a catalog or the model without refitting
(``python scripts/fit_correlations.py``) fails loudly instead of silently
using a stale matrix.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from importlib import resources
from typing import Any

import numpy as np

from marketforge._version import MODEL_REVISION
from marketforge.config.catalog.correlation import (
    DEFAULT_WEIGHT,
    DERIVED_DEFAULT_WEIGHT,
    DERIVED_STATED_WEIGHT,
    STATED_WEIGHT,
    fit_correlation,
    implied_correlation,
)
from marketforge.config.catalog.crypto import correlations as crypto_correlations
from marketforge.config.catalog.crypto import instruments as crypto_instruments
from marketforge.config.catalog.forex import correlations as forex_correlations
from marketforge.config.catalog.forex import instruments as forex_instruments
from marketforge.config.catalog.schema import InstrumentParams
from marketforge.config.catalog.stocks import correlations as stocks_correlations
from marketforge.config.catalog.stocks import instruments as stocks_instruments
from marketforge.config.factors import FactorStructure, forex_structure
from marketforge.domain.markets import MarketType

FILE_NAME = "fitted_correlation.json"

_SOURCES = {
    MarketType.CRYPTO: (crypto_instruments.INSTRUMENTS, crypto_correlations.stated_correlations),
    MarketType.FOREX: (forex_instruments.INSTRUMENTS, forex_correlations.stated_correlations),
    MarketType.STOCKS: (stocks_instruments.INSTRUMENTS, stocks_correlations.stated_correlations),
}


@dataclass(frozen=True)
class FitProblem:
    """What the fit of one market's correlations explains."""

    symbols: list[str]
    structure: FactorStructure
    target: np.ndarray  # (instruments, instruments)
    weight: np.ndarray
    scales: np.ndarray  # the factors' volatilities
    vol_target: np.ndarray  # every instrument's stated volatility
    vol_weight: np.ndarray  # nonzero for derived instruments (forex crosses)

    def digest(self) -> str:
        h = hashlib.sha256()
        h.update(json.dumps(self.symbols).encode())
        for array in (self.target, self.weight, self.scales, self.vol_target, self.vol_weight):
            h.update(np.ascontiguousarray(array, dtype=np.float64).tobytes())
        return h.hexdigest()


def fit_problem(market: MarketType) -> FitProblem:
    instruments, stated_correlations = _SOURCES[market]
    target, stated, symbols = stated_correlations()
    structure = (
        forex_structure(symbols)
        if market == MarketType.FOREX
        else FactorStructure.identity(symbols)
    )
    params: dict[str, InstrumentParams] = instruments
    vols = np.array([params[s].volatility for s in symbols])
    derived = np.array([s not in structure.factors for s in symbols])
    return FitProblem(
        symbols=symbols,
        structure=structure,
        target=target,
        weight=np.where(
            derived[:, None] | derived[None, :],
            np.where(stated, DERIVED_STATED_WEIGHT, DERIVED_DEFAULT_WEIGHT),
            np.where(stated, STATED_WEIGHT, DEFAULT_WEIGHT),
        ),
        scales=np.array([params[s].volatility for s in structure.factors]),
        vol_target=vols,
        vol_weight=derived.astype(float),
    )


def fit(market: MarketType) -> np.ndarray:
    """Fit a market's factor correlation matrix (offline: needs scipy, takes seconds)."""
    p = fit_problem(market)
    factors = [p.symbols.index(s) for s in p.structure.factors]
    return fit_correlation(
        p.target,
        p.weight,
        loadings=p.structure.weights,
        scales=p.scales,
        vol_target=p.vol_target,
        vol_weight=p.vol_weight,
        start=p.target[np.ix_(factors, factors)],
    )


def document(
    market: MarketType,
    daily: np.ndarray,
    minute: np.ndarray | None = None,
    horizon: tuple[list[float], list[float]] | None = None,
) -> str:
    """The JSON file of a market's fit: ``daily`` and the ``minute`` matrix that gives it."""
    p = fit_problem(market)
    minute = daily if minute is None else minute
    days, minutes = horizon_table(daily, minute) if horizon is None else horizon
    return (
        json.dumps(
            {
                "digest": p.digest(),
                "model_revision": MODEL_REVISION,
                "factors": list(p.structure.factors),
                "horizon": {"daily": days, "minute": minutes},
                "daily": [[float(v) for v in row] for row in daily],
                "matrix": [[float(v) for v in row] for row in minute],
            },
            indent=0,
        )
        + "\n"
    )


def _document(market: MarketType) -> dict[str, Any]:
    p = fit_problem(market)
    text = resources.files(f"marketforge.config.catalog.{market.value}").joinpath(FILE_NAME)
    doc: dict[str, Any] = json.loads(text.read_text(encoding="utf-8"))
    if doc["digest"] != p.digest() or doc["factors"] != list(p.structure.factors):
        raise RuntimeError(
            f"The {market.value} catalog changed since its correlations were fitted: "
            "run `python scripts/fit_correlations.py`"
        )
    if doc.get("model_revision") != MODEL_REVISION:
        raise RuntimeError(
            f"The {market.value} correlations were fitted for model revision "
            f"{doc.get('model_revision')}, not {MODEL_REVISION}: run `python scripts/fit_correlations.py`"
        )
    return doc


def horizon_table(
    daily: np.ndarray, minute: np.ndarray, bins: int = 12
) -> tuple[list[float], list[float]]:
    """A monotone table from daily to minute correlations, over a market's pairs.

    The pairs are binned by their daily correlation and each bin's means
    kept, then (-1, -1), (0, 0) and (1, 1) are added: a pair the market's
    common moves do not touch keeps its correlation at every horizon. A
    straight line fitted to the catalog's pairs, all positive in crypto and
    stocks, would have sent a daily 0 to a minute -0.3.
    """
    off = ~np.eye(len(daily), dtype=bool)
    d, m = np.asarray(daily)[off], np.asarray(minute)[off]
    order = np.argsort(d)
    groups = np.array_split(order, min(bins, d.size))
    points = {(-1.0, -1.0), (0.0, 0.0), (1.0, 1.0)}
    points |= {(float(d[g].mean()), float(m[g].mean())) for g in groups if g.size}
    table = np.array(sorted(points))
    # Monotone: a higher daily correlation never needs a lower minute one.
    minutes = np.maximum.accumulate(table[:, 1])
    return [round(float(x), 6) for x in table[:, 0]], [round(float(y), 6) for y in minutes]


def minute_correlation(market: MarketType, daily: float) -> float:
    """The minute shocks' correlation that gives a pair the daily correlation ``daily``."""
    table = _document(market)["horizon"]
    rho = np.interp(float(daily), table["daily"], table["minute"])
    return float(np.clip(rho, -0.99, 0.99))


def load_fitted(market: MarketType) -> tuple[np.ndarray, list[str]]:
    """The full instrument correlation matrix of a built-in market, and its symbol order."""
    p = fit_problem(market)
    doc = _document(market)
    factor_correlation = np.array(doc["matrix"], dtype=float)
    if p.structure.is_identity:
        return factor_correlation, p.symbols
    corr, _ = implied_correlation(factor_correlation, p.structure.weights, p.scales)
    return corr, p.symbols
