# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

"""
The fitted correlation matrix of each built-in market, shipped as data.

``fitted_correlation.json`` beside each market's catalog holds the factors'
fitted correlation matrix (see :mod:`marketforge.config.catalog.correlation`)
and a digest of the problem it solves: the stated correlations, the weights
and the volatilities. Loading checks the digest, so editing a catalog without
refitting (``python scripts/fit_correlations.py``) fails loudly instead of
silently using a stale matrix.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from importlib import resources

import numpy as np

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


def document(market: MarketType, factor_correlation: np.ndarray) -> str:
    p = fit_problem(market)
    return (
        json.dumps(
            {
                "digest": p.digest(),
                "factors": list(p.structure.factors),
                "matrix": [[float(v) for v in row] for row in factor_correlation],
            },
            indent=0,
        )
        + "\n"
    )


def load_fitted(market: MarketType) -> tuple[np.ndarray, list[str]]:
    """The full instrument correlation matrix of a built-in market, and its symbol order."""
    p = fit_problem(market)
    text = resources.files(f"marketforge.config.catalog.{market.value}").joinpath(FILE_NAME)
    doc = json.loads(text.read_text(encoding="utf-8"))
    if doc["digest"] != p.digest() or doc["factors"] != list(p.structure.factors):
        raise RuntimeError(
            f"The {market.value} catalog changed since its correlations were fitted: "
            "run `python scripts/fit_correlations.py`"
        )
    factor_correlation = np.array(doc["matrix"], dtype=float)
    if p.structure.is_identity:
        return factor_correlation, p.symbols
    corr, _ = implied_correlation(factor_correlation, p.structure.weights, p.scales)
    return corr, p.symbols
