# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the MIT License. See the LICENSE file in the project
# root for full license information.

"""
Factor structure: which series are simulated, and how instruments derive from them.

For crypto and stocks every instrument is simulated directly. For forex only
one *anchor pair* per code is simulated; every *cross* is the exact signed sum
of anchor log prices, so EURJPY == EURUSD * USDJPY at every minute and no
triangle can be arbitraged (see docs/adr/0002).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

ROOT_CODE = "USD"


@dataclass(frozen=True)
class FactorStructure:
    """
    Mapping from simulated factor series to published instruments.

    Attributes:
        factors: Symbols of the series that are simulated (anchor pairs).
        instruments: Symbols of every published instrument.
        weights: (n_instruments, n_factors) matrix with
            log_price[instrument] = weights @ log_price[factors].
    """

    factors: tuple[str, ...]
    instruments: tuple[str, ...]
    weights: np.ndarray

    @classmethod
    def identity(cls, symbols: list[str]) -> "FactorStructure":
        """Every instrument is its own factor."""
        syms = tuple(symbols)
        return cls(factors=syms, instruments=syms, weights=np.eye(len(syms)))

    @property
    def is_identity(self) -> bool:
        return self.factors == self.instruments

    def factor_index(self, symbol: str) -> int:
        return self.factors.index(symbol)


def split_pair(symbol: str) -> tuple[str, str]:
    """Split a six-character forex symbol into (base, quote) codes."""
    if len(symbol) != 6 or not symbol.isalnum():
        raise ValueError(f"Forex symbol must be six alphanumeric characters, got {symbol!r}")
    return symbol[:3], symbol[3:]


def forex_structure(symbols: list[str]) -> FactorStructure:
    """
    Choose anchor pairs and express every forex instrument in terms of them.

    Anchors form a spanning tree over codes rooted at USD: pairs quoted
    against USD are preferred (in catalog order), then any pair that links a
    new code to one already connected (e.g. GRXEUR for the DAX).

    Raises:
        ValueError: if some code cannot be connected to USD through the list.
    """
    pairs = [split_pair(s) for s in symbols]
    # code -> coefficient vector over anchors, built as anchors are chosen
    coeffs: dict[str, dict[int, int]] = {ROOT_CODE: {}}
    anchors: list[int] = []

    def try_link(i: int) -> bool:
        base, quote = pairs[i]
        if (base in coeffs) == (quote in coeffs):
            return False
        f = len(anchors)
        anchors.append(i)
        # log(pair) = x_base - x_quote  =>  solve for the new code
        if quote in coeffs:  # new base: x_base = log(pair) + x_quote
            vec = dict(coeffs[quote])
            vec[f] = vec.get(f, 0) + 1
            coeffs[base] = vec
        else:  # new quote: x_quote = x_base - log(pair)
            vec = dict(coeffs[base])
            vec[f] = vec.get(f, 0) - 1
            coeffs[quote] = vec
        return True

    for i, (base, quote) in enumerate(pairs):
        if ROOT_CODE in (base, quote):
            try_link(i)
    changed = True
    while changed:
        changed = False
        for i in range(len(pairs)):
            if i not in anchors and try_link(i):
                changed = True

    missing = sorted({c for p in pairs for c in p} - set(coeffs))
    if missing:
        raise ValueError(f"Forex codes {missing} cannot be linked to {ROOT_CODE} by any pair")

    weights = np.zeros((len(symbols), len(anchors)))
    for i, (base, quote) in enumerate(pairs):
        for f, c in coeffs[base].items():
            weights[i, f] += c
        for f, c in coeffs[quote].items():
            weights[i, f] -= c
    return FactorStructure(
        factors=tuple(symbols[i] for i in anchors),
        instruments=tuple(symbols),
        weights=weights,
    )
