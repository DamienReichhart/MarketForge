# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the GNU Affero General Public License v3.0 or later.
# See the LICENSE file in the project root for full license information.

"""Correlation matrix of the forex catalog, built from typical market relationships."""

from __future__ import annotations

import numpy as np

from marketforge.config.catalog.correlation import ensure_positive_semidefinite
from marketforge.config.catalog.forex.instruments import INSTRUMENTS


def build_correlation_matrix() -> tuple[np.ndarray, list[str]]:
    """
    Build the correlation matrix for forex pairs.

    Correlations are based on:
    - Shared currencies (high positive/negative)
    - Safe haven dynamics
    - Risk-on/risk-off behavior
    - Commodity currency relationships

    Returns:
        Tuple of (correlation_matrix, symbol_order)
    """
    symbols = list(INSTRUMENTS)
    n = len(symbols)
    symbol_to_idx = {s: i for i, s in enumerate(symbols)}

    # Start with moderate base correlation
    corr = np.full((n, n), 0.25)
    np.fill_diagonal(corr, 1.0)

    # Define correlation rules based on currency relationships
    def set_corr(s1: str, s2: str, value: float) -> None:
        if s1 in symbol_to_idx and s2 in symbol_to_idx:
            i, j = symbol_to_idx[s1], symbol_to_idx[s2]
            corr[i, j] = value
            corr[j, i] = value

    # ===================
    # MAJOR PAIRS
    # ===================

    # EURUSD relationships
    set_corr("EURUSD", "EURCHF", 0.85)
    set_corr("EURUSD", "EURGBP", 0.65)
    set_corr("EURUSD", "EURJPY", 0.75)
    set_corr("EURUSD", "GBPUSD", 0.82)
    set_corr("EURUSD", "USDCHF", -0.92)
    set_corr("EURUSD", "USDJPY", -0.55)
    set_corr("EURUSD", "AUDUSD", 0.65)
    set_corr("EURUSD", "NZDUSD", 0.60)
    set_corr("EURUSD", "USDCAD", -0.70)

    # GBPUSD relationships
    set_corr("GBPUSD", "EURGBP", -0.45)
    set_corr("GBPUSD", "GBPJPY", 0.80)
    set_corr("GBPUSD", "GBPCHF", 0.88)
    set_corr("GBPUSD", "USDCHF", -0.85)
    set_corr("GBPUSD", "USDJPY", -0.50)
    set_corr("GBPUSD", "AUDUSD", 0.60)
    set_corr("GBPUSD", "USDCAD", -0.65)

    # USDJPY relationships
    set_corr("USDJPY", "EURJPY", 0.88)
    set_corr("USDJPY", "GBPJPY", 0.85)
    set_corr("USDJPY", "AUDJPY", 0.80)
    set_corr("USDJPY", "CHFJPY", 0.75)
    set_corr("USDJPY", "CADJPY", 0.82)
    set_corr("USDJPY", "NZDJPY", 0.78)
    set_corr("USDJPY", "USDCHF", 0.55)

    # USDCHF relationships
    set_corr("USDCHF", "EURCHF", -0.78)
    set_corr("USDCHF", "GBPCHF", -0.75)
    set_corr("USDCHF", "CHFJPY", -0.70)
    set_corr("USDCHF", "USDCAD", 0.60)

    # Commodity currencies (AUD, NZD, CAD)
    set_corr("AUDUSD", "NZDUSD", 0.88)
    set_corr("AUDUSD", "USDCAD", -0.72)
    set_corr("AUDUSD", "AUDJPY", 0.82)
    set_corr("AUDUSD", "AUDCAD", 0.75)
    set_corr("AUDUSD", "AUDCHF", 0.85)
    set_corr("AUDUSD", "AUDNZD", 0.40)
    set_corr("AUDUSD", "EURAUD", -0.78)
    set_corr("AUDUSD", "GBPAUD", -0.75)

    set_corr("NZDUSD", "USDCAD", -0.68)
    set_corr("NZDUSD", "NZDJPY", 0.80)
    set_corr("NZDUSD", "NZDCAD", 0.72)
    set_corr("NZDUSD", "NZDCHF", 0.82)
    set_corr("NZDUSD", "AUDNZD", -0.55)
    set_corr("NZDUSD", "EURNZD", -0.75)
    set_corr("NZDUSD", "GBPNZD", -0.72)

    set_corr("USDCAD", "CADJPY", -0.75)
    set_corr("USDCAD", "AUDCAD", -0.65)
    set_corr("USDCAD", "NZDCAD", -0.62)
    set_corr("USDCAD", "CADCHF", -0.78)
    set_corr("USDCAD", "EURCAD", 0.72)
    set_corr("USDCAD", "GBPCAD", 0.68)

    # ===================
    # EUR CROSSES
    # ===================

    set_corr("EURCHF", "EURGBP", 0.55)
    set_corr("EURCHF", "EURJPY", 0.70)
    set_corr("EURCHF", "EURAUD", 0.55)
    set_corr("EURCHF", "EURCAD", 0.65)
    set_corr("EURCHF", "EURNZD", 0.50)
    set_corr("EURCHF", "GBPCHF", 0.75)
    set_corr("EURCHF", "CHFJPY", -0.65)

    set_corr("EURGBP", "EURJPY", 0.45)
    set_corr("EURGBP", "EURAUD", 0.50)
    set_corr("EURGBP", "EURCAD", 0.52)
    set_corr("EURGBP", "GBPJPY", -0.40)
    set_corr("EURGBP", "GBPCHF", -0.35)

    set_corr("EURJPY", "GBPJPY", 0.88)
    set_corr("EURJPY", "AUDJPY", 0.82)
    set_corr("EURJPY", "CHFJPY", 0.80)
    set_corr("EURJPY", "CADJPY", 0.85)
    set_corr("EURJPY", "NZDJPY", 0.80)
    set_corr("EURJPY", "EURAUD", 0.45)
    set_corr("EURJPY", "EURCAD", 0.55)

    set_corr("EURAUD", "EURNZD", 0.85)
    set_corr("EURAUD", "EURCAD", 0.70)
    set_corr("EURAUD", "GBPAUD", 0.80)
    set_corr("EURAUD", "AUDNZD", -0.50)

    set_corr("EURCAD", "EURNZD", 0.72)
    set_corr("EURCAD", "GBPCAD", 0.78)
    set_corr("EURCAD", "AUDCAD", -0.45)

    set_corr("EURNZD", "GBPNZD", 0.82)
    set_corr("EURNZD", "AUDNZD", 0.55)

    # EUR exotic pairs - high correlation within group
    set_corr("EURHUF", "EURPLN", 0.85)
    set_corr("EURHUF", "EURCZK", 0.75)
    set_corr("EURPLN", "EURCZK", 0.78)
    set_corr("EURSEK", "EURNOK", 0.82)
    set_corr("EURTRY", "EURMXN", 0.55)

    # ===================
    # GBP CROSSES
    # ===================

    set_corr("GBPCHF", "GBPJPY", 0.72)
    set_corr("GBPCHF", "GBPAUD", 0.68)
    set_corr("GBPCHF", "GBPNZD", 0.65)
    set_corr("GBPCHF", "GBPCAD", 0.70)
    set_corr("GBPCHF", "CHFJPY", -0.60)

    set_corr("GBPJPY", "GBPAUD", 0.65)
    set_corr("GBPJPY", "GBPNZD", 0.62)
    set_corr("GBPJPY", "GBPCAD", 0.68)
    set_corr("GBPJPY", "AUDJPY", 0.78)
    set_corr("GBPJPY", "CHFJPY", 0.75)
    set_corr("GBPJPY", "CADJPY", 0.80)
    set_corr("GBPJPY", "NZDJPY", 0.76)

    set_corr("GBPAUD", "GBPNZD", 0.88)
    set_corr("GBPAUD", "GBPCAD", 0.75)

    set_corr("GBPNZD", "GBPCAD", 0.72)

    # ===================
    # JPY CROSSES
    # ===================

    set_corr("AUDJPY", "NZDJPY", 0.90)
    set_corr("AUDJPY", "CADJPY", 0.85)
    set_corr("AUDJPY", "CHFJPY", 0.72)

    set_corr("NZDJPY", "CADJPY", 0.82)
    set_corr("NZDJPY", "CHFJPY", 0.70)

    set_corr("CADJPY", "CHFJPY", 0.68)

    set_corr("SGDJPY", "USDJPY", 0.75)
    set_corr("SGDJPY", "CHFJPY", 0.60)

    # Exotic JPY pairs
    set_corr("ZARJPY", "MXNJPY", 0.72)
    set_corr("ZARJPY", "TRYJPY", 0.55)
    set_corr("MXNJPY", "TRYJPY", 0.50)
    set_corr("NOKJPY", "SEKJPY", 0.85)

    # ===================
    # COMMODITY CURRENCY CROSSES
    # ===================

    set_corr("AUDCAD", "NZDCAD", 0.85)
    set_corr("AUDCAD", "AUDCHF", 0.72)
    set_corr("AUDCAD", "AUDNZD", 0.60)

    set_corr("AUDCHF", "NZDCHF", 0.88)
    set_corr("AUDCHF", "CADCHF", 0.75)

    set_corr("NZDCAD", "NZDCHF", 0.72)
    set_corr("NZDCAD", "AUDNZD", -0.55)

    set_corr("NZDCHF", "CADCHF", 0.70)

    # ===================
    # USD EXOTIC PAIRS
    # ===================

    set_corr("USDMXN", "USDTRY", 0.55)
    set_corr("USDMXN", "USDZAR", 0.68)
    set_corr("USDTRY", "USDZAR", 0.52)

    set_corr("USDNOK", "USDSEK", 0.85)
    set_corr("USDNOK", "USDDKK", 0.72)
    set_corr("USDSEK", "USDDKK", 0.75)

    set_corr("USDHUF", "USDPLN", 0.82)
    set_corr("USDHUF", "USDCZK", 0.75)
    set_corr("USDPLN", "USDCZK", 0.78)

    # Asian pairs
    set_corr("USDCNH", "USDSGD", 0.60)
    set_corr("USDCNH", "USDINR", 0.45)
    set_corr("USDINR", "USDTHB", 0.55)
    set_corr("USDTHB", "USDPHP", 0.65)
    set_corr("USDPHP", "USDIDR", 0.60)
    set_corr("USDTWD", "USDSGD", 0.55)

    # ===================
    # PRECIOUS METALS
    # ===================

    # Gold pairs highly correlated
    set_corr("XAUUSD", "XAGUSD", 0.85)
    set_corr("XAUUSD", "XAUEUR", 0.95)
    set_corr("XAUUSD", "XAUGBP", 0.92)
    set_corr("XAUUSD", "XAUCHF", 0.90)
    set_corr("XAUUSD", "XAUAUD", 0.88)
    set_corr("XAUUSD", "XPTUSD", 0.72)
    set_corr("XAUUSD", "XPDUSD", 0.55)

    set_corr("XAGUSD", "XAUEUR", 0.82)
    set_corr("XAGUSD", "XAUGBP", 0.80)
    set_corr("XAGUSD", "XAUCHF", 0.78)
    set_corr("XAGUSD", "XPTUSD", 0.70)
    set_corr("XAGUSD", "XPDUSD", 0.50)

    set_corr("XAUEUR", "XAUGBP", 0.90)
    set_corr("XAUEUR", "XAUCHF", 0.92)
    set_corr("XAUEUR", "XAUAUD", 0.85)

    set_corr("XAUGBP", "XAUCHF", 0.88)
    set_corr("XAUGBP", "XAUAUD", 0.82)

    set_corr("XAUCHF", "XAUAUD", 0.80)

    set_corr("XPTUSD", "XPDUSD", 0.75)

    # Gold vs USD (inverse)
    set_corr("XAUUSD", "UDXUSD", -0.72)
    set_corr("XAGUSD", "UDXUSD", -0.65)

    # Gold positive with risk-off
    set_corr("XAUUSD", "USDJPY", -0.40)
    set_corr("XAUUSD", "USDCHF", -0.55)

    # ===================
    # INDICES
    # ===================

    # US indices correlated
    set_corr("SPXUSD", "NSXUSD", 0.92)

    # European indices correlated
    set_corr("GRXEUR", "FRXEUR", 0.88)
    set_corr("GRXEUR", "ETXEUR", 0.85)
    set_corr("FRXEUR", "ETXEUR", 0.90)
    set_corr("UKXGBP", "FRXEUR", 0.78)
    set_corr("UKXGBP", "GRXEUR", 0.75)

    # Cross-region
    set_corr("SPXUSD", "UKXGBP", 0.72)
    set_corr("SPXUSD", "FRXEUR", 0.70)
    set_corr("SPXUSD", "JPXJPY", 0.65)

    # Indices vs currencies
    set_corr("SPXUSD", "USDJPY", 0.55)
    set_corr("SPXUSD", "AUDUSD", 0.50)

    # DXY relationships
    set_corr("UDXUSD", "EURUSD", -0.95)
    set_corr("UDXUSD", "GBPUSD", -0.65)
    set_corr("UDXUSD", "USDCHF", 0.70)
    set_corr("UDXUSD", "USDJPY", 0.55)
    set_corr("UDXUSD", "USDCAD", 0.50)

    # ===================
    # ENERGY COMMODITIES
    # ===================

    set_corr("BCOUSD", "WTIUSD", 0.95)

    # Oil vs CAD (oil exporter)
    set_corr("WTIUSD", "USDCAD", -0.55)
    set_corr("BCOUSD", "USDCAD", -0.52)
    set_corr("WTIUSD", "CADJPY", 0.48)

    # Oil vs risk sentiment
    set_corr("WTIUSD", "AUDUSD", 0.45)
    set_corr("WTIUSD", "SPXUSD", 0.35)

    # Ensure matrix is positive semi-definite
    corr = ensure_positive_semidefinite(corr)

    return corr, symbols
