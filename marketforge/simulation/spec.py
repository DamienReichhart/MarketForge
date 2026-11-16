# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the MIT License. See the LICENSE file in the project
# root for full license information.

"""What a market simulation needs: instruments, factor structure, correlations, parameters."""

from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np

from marketforge.config.catalog.schema import InstrumentParams, MarketConfig
from marketforge.config.defaults import MarketDefaults, get_market_defaults
from marketforge.config.model_params import AnomalyConfig
from marketforge.domain.anomalies import AnomalyType
from marketforge.domain.markets import MarketType
from marketforge.simulation.factors import FactorStructure, forex_structure


@dataclass(frozen=True)
class MarketSpec:
    """Everything needed to simulate one market."""

    market: MarketType
    instruments: tuple[InstrumentParams, ...]
    structure: FactorStructure
    factor_correlation: np.ndarray
    defaults: MarketDefaults
    anomaly: AnomalyConfig = field(default_factory=lambda: AnomalyConfig(types=frozenset()))

    @property
    def symbols(self) -> tuple[str, ...]:
        return self.structure.instruments


def build_market_spec(
    config: MarketConfig,
    anomalies: frozenset[AnomalyType] = frozenset(),
    defaults: MarketDefaults | None = None,
) -> MarketSpec:
    """Turn a catalog market configuration into a simulation spec."""
    market = MarketType(config.market_type)
    defaults = defaults or get_market_defaults(market)
    symbols = list(config.symbols)
    if market == MarketType.FOREX:
        structure = forex_structure(symbols)
    else:
        structure = FactorStructure.identity(symbols)
    idx = [symbols.index(s) for s in structure.factors]
    corr = np.asarray(config.correlation_matrix)[np.ix_(idx, idx)]
    anomaly = replace(defaults.anomaly_config, types=frozenset(anomalies))
    return MarketSpec(
        market=market,
        instruments=tuple(config.get_instrument(s) for s in symbols),
        structure=structure,
        factor_correlation=corr,
        defaults=defaults,
        anomaly=anomaly,
    )
