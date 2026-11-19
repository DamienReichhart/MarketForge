# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

"""Pegged currencies: which factor holds each peg, and how hard."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from marketforge.config.catalog.forex.pegs import PEGS
from marketforge.domain.markets import MarketType
from marketforge.domain.time import MINUTES_PER_DAY
from marketforge.simulation.spec import MarketSpec


@dataclass(frozen=True)
class Peg:
    """A pegged pair: its log price is ``vector @ log factors``, moved through ``held``."""

    held: int  # the factor of the pegged currency (market-wide index)
    vector: np.ndarray  # (F,) the pair over the market's factors
    centre: float  # log centre
    half_width: float  # log half-width of the band
    pull: float  # per open minute


def market_pegs(spec: MarketSpec) -> list[Peg]:
    """The pegs of a market's catalog (forex only)."""
    if spec.market != MarketType.FOREX:
        return []
    structure = spec.structure
    by_symbol = {a.symbol: a for a in spec.instruments}
    pegs = []
    for symbol, (centre, half, half_life) in PEGS.items():
        if symbol not in structure.instruments:
            continue
        vector = structure.weights[structure.instruments.index(symbol)]
        code = symbol[3:]  # the pegged currency is quoted against its anchor
        held = next(int(f) for f in np.flatnonzero(vector) if code in structure.factors[int(f)])
        level = centre if centre is not None else by_symbol[symbol].start_price
        pegs.append(
            Peg(
                held=held,
                vector=np.asarray(vector, dtype=float),
                centre=math.log(level),
                half_width=math.log1p(half),
                pull=math.log(2.0) / (half_life * MINUTES_PER_DAY),
            )
        )
    return pegs


def peg_factors(pegs: list[Peg], needed: np.ndarray) -> np.ndarray:
    """The factors that must be simulated with ``needed`` to hold its pegs."""
    extra = [np.flatnonzero(peg.vector) for peg in pegs if peg.held in set(needed.tolist())]
    return np.unique(np.concatenate(extra)) if extra else np.empty(0, dtype=np.int64)
