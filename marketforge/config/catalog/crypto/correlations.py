# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

"""Correlation matrix of the crypto catalog, built from typical market relationships."""

from __future__ import annotations

import numpy as np

from marketforge.config.catalog.correlation import ensure_positive_semidefinite
from marketforge.config.catalog.crypto.instruments import INSTRUMENTS


def build_correlation_matrix() -> tuple[np.ndarray, list[str]]:
    """
    Build the correlation matrix for crypto instruments.

    Correlations are based on:
    - BTC dominance (all alts correlated with BTC)
    - ETH ecosystem correlation
    - Sector groupings (DeFi, Gaming, L1s)
    - Market cap tiers

    Returns:
        Tuple of (correlation_matrix, symbol_order)
    """
    symbols = list(INSTRUMENTS)
    n = len(symbols)
    symbol_to_idx = {s: i for i, s in enumerate(symbols)}

    # Start with moderate correlation (crypto is highly correlated)
    corr = np.full((n, n), 0.50)
    np.fill_diagonal(corr, 1.0)

    def set_corr(s1: str, s2: str, value: float) -> None:
        if s1 in symbol_to_idx and s2 in symbol_to_idx:
            i, j = symbol_to_idx[s1], symbol_to_idx[s2]
            corr[i, j] = value
            corr[j, i] = value

    # ===================
    # BTC CORRELATIONS (Market Leader)
    # ===================

    # ETH - highest correlation with BTC
    set_corr("BTCUSD", "ETHUSD", 0.88)

    # Large caps - very high correlation with BTC
    set_corr("BTCUSD", "BNBUSD", 0.82)
    set_corr("BTCUSD", "SOLUSD", 0.80)
    set_corr("BTCUSD", "XRPUSD", 0.75)
    set_corr("BTCUSD", "ADAUSD", 0.78)
    set_corr("BTCUSD", "DOGEUSD", 0.72)
    set_corr("BTCUSD", "TRXUSD", 0.70)
    set_corr("BTCUSD", "AVAXUSD", 0.78)
    set_corr("BTCUSD", "DOTUSD", 0.76)
    set_corr("BTCUSD", "LTCUSD", 0.85)
    set_corr("BTCUSD", "BCHUSD", 0.82)

    # Other L1s with BTC
    set_corr("BTCUSD", "MATICUSD", 0.75)
    set_corr("BTCUSD", "LINKUSD", 0.78)
    set_corr("BTCUSD", "ATOMUSD", 0.74)
    set_corr("BTCUSD", "XLMUSD", 0.72)
    set_corr("BTCUSD", "NEARUSD", 0.73)
    set_corr("BTCUSD", "ICPUSD", 0.68)
    set_corr("BTCUSD", "APTUSD", 0.72)
    set_corr("BTCUSD", "ETCUSD", 0.80)

    # DeFi with BTC
    set_corr("BTCUSD", "AAVEUSD", 0.72)
    set_corr("BTCUSD", "UNIUSD", 0.74)
    set_corr("BTCUSD", "MKRUSD", 0.70)

    # Gaming/Metaverse - lower correlation with BTC
    set_corr("BTCUSD", "AXSUSD", 0.62)
    set_corr("BTCUSD", "SANDUSD", 0.60)
    set_corr("BTCUSD", "MANAUSD", 0.60)
    set_corr("BTCUSD", "APEUSD", 0.58)

    # L2s with BTC
    set_corr("BTCUSD", "ARBUSD", 0.75)
    set_corr("BTCUSD", "OPUSD", 0.76)

    # ===================
    # ETH CORRELATIONS (Second Leader)
    # ===================

    # L1 competitors
    set_corr("ETHUSD", "BNBUSD", 0.85)
    set_corr("ETHUSD", "SOLUSD", 0.83)
    set_corr("ETHUSD", "AVAXUSD", 0.82)
    set_corr("ETHUSD", "ADAUSD", 0.80)
    set_corr("ETHUSD", "DOTUSD", 0.78)
    set_corr("ETHUSD", "MATICUSD", 0.85)  # Polygon closely tied to ETH
    set_corr("ETHUSD", "NEARUSD", 0.78)
    set_corr("ETHUSD", "ATOMUSD", 0.76)

    # ETH ecosystem (L2s, DeFi on ETH)
    set_corr("ETHUSD", "ARBUSD", 0.88)
    set_corr("ETHUSD", "OPUSD", 0.87)
    set_corr("ETHUSD", "AAVEUSD", 0.82)
    set_corr("ETHUSD", "UNIUSD", 0.85)
    set_corr("ETHUSD", "LINKUSD", 0.84)
    set_corr("ETHUSD", "MKRUSD", 0.78)
    set_corr("ETHUSD", "SNXUSD", 0.75)
    set_corr("ETHUSD", "COMPUSD", 0.76)
    set_corr("ETHUSD", "CRVUSD", 0.78)
    set_corr("ETHUSD", "LDOUSD", 0.82)  # Lido - ETH staking
    set_corr("ETHUSD", "DYDXUSD", 0.75)

    # ETC - ETH fork
    set_corr("ETHUSD", "ETCUSD", 0.78)

    # ===================
    # LAYER 1 CORRELATIONS
    # ===================

    # SOL ecosystem
    set_corr("SOLUSD", "AVAXUSD", 0.82)
    set_corr("SOLUSD", "NEARUSD", 0.80)
    set_corr("SOLUSD", "APTUSD", 0.82)
    set_corr("SOLUSD", "ADAUSD", 0.75)
    set_corr("SOLUSD", "DOTUSD", 0.74)

    # Cosmos ecosystem
    set_corr("ATOMUSD", "INJUSD", 0.78)
    set_corr("ATOMUSD", "KAVAUSD", 0.72)
    set_corr("ATOMUSD", "RUNEUSD", 0.70)

    # L1 general correlations
    set_corr("AVAXUSD", "NEARUSD", 0.78)
    set_corr("AVAXUSD", "APTUSD", 0.76)
    set_corr("ADAUSD", "DOTUSD", 0.80)
    set_corr("ADAUSD", "XLMUSD", 0.72)
    set_corr("DOTUSD", "KSMUSD", 0.88)  # Kusama is DOT canary network

    # Old school L1s
    set_corr("LTCUSD", "BCHUSD", 0.82)
    set_corr("LTCUSD", "ETCUSD", 0.75)
    set_corr("BCHUSD", "ETCUSD", 0.72)
    set_corr("EOSUSD", "XTZUSD", 0.70)
    set_corr("XLMUSD", "XRPUSD", 0.78)  # Same founder

    # Privacy coins
    set_corr("ZECUSD", "DASHUSD", 0.82)

    # ===================
    # LAYER 2 CORRELATIONS
    # ===================

    set_corr("ARBUSD", "OPUSD", 0.90)  # Both ETH L2s
    set_corr("ARBUSD", "MATICUSD", 0.85)
    set_corr("OPUSD", "MATICUSD", 0.84)

    # ===================
    # DEFI CORRELATIONS
    # ===================

    # DEX tokens
    set_corr("UNIUSD", "SUSHIUSD", 0.85)
    set_corr("UNIUSD", "CRVUSD", 0.80)
    set_corr("SUSHIUSD", "CRVUSD", 0.78)
    set_corr("CAKEUSD", "SUSHIUSD", 0.75)

    # Lending protocols
    set_corr("AAVEUSD", "COMPUSD", 0.85)
    set_corr("AAVEUSD", "MKRUSD", 0.78)
    set_corr("COMPUSD", "MKRUSD", 0.76)

    # Derivatives
    set_corr("SNXUSD", "DYDXUSD", 0.78)

    # Staking
    set_corr("LDOUSD", "RUNEUSD", 0.72)

    # DeFi general
    set_corr("AAVEUSD", "UNIUSD", 0.82)
    set_corr("AAVEUSD", "CRVUSD", 0.78)
    set_corr("UNIUSD", "LINKUSD", 0.80)  # Oracles important for DeFi
    set_corr("AAVEUSD", "LINKUSD", 0.78)

    # ===================
    # GAMING / METAVERSE CORRELATIONS
    # ===================

    set_corr("AXSUSD", "SANDUSD", 0.88)
    set_corr("AXSUSD", "MANAUSD", 0.85)
    set_corr("SANDUSD", "MANAUSD", 0.90)
    set_corr("APEUSD", "SANDUSD", 0.80)
    set_corr("APEUSD", "MANAUSD", 0.78)
    set_corr("APEUSD", "AXSUSD", 0.75)
    set_corr("IMXUSD", "AXSUSD", 0.78)  # IMX - gaming L2
    set_corr("IMXUSD", "SANDUSD", 0.75)
    set_corr("FLOWUSD", "AXSUSD", 0.72)  # Flow - gaming/NFT

    # ===================
    # INFRASTRUCTURE CORRELATIONS
    # ===================

    set_corr("LINKUSD", "GRTUSD", 0.80)
    set_corr("LINKUSD", "FILUSD", 0.72)
    set_corr("GRTUSD", "FILUSD", 0.75)
    set_corr("THETAUSD", "FILUSD", 0.70)
    set_corr("INJUSD", "GRTUSD", 0.72)

    # ===================
    # MEME / HIGH BETA
    # ===================

    set_corr("DOGEUSD", "APEUSD", 0.68)  # Meme coins
    set_corr("DOGEUSD", "SOLUSD", 0.65)  # Popular chains

    # ===================
    # EXCHANGE TOKENS
    # ===================

    set_corr("BNBUSD", "CAKEUSD", 0.82)  # BSC ecosystem

    # Ensure matrix is positive semi-definite
    corr = ensure_positive_semidefinite(corr)

    return corr, symbols
