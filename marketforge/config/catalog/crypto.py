# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the MIT License. See the LICENSE file in the project
# root for full license information.

"""
Crypto market configuration with 53 cryptocurrency pairs.

Contains realistic start prices, volatilities, drifts, and correlation matrix
based on typical crypto market relationships and sector groupings.
"""

from __future__ import annotations

import numpy as np

from marketforge.config.catalog.base import (
    AssetParams,
    MarketConfig,
    ensure_positive_semidefinite,
)
from marketforge.config.settings import MarketType

# =============================================================================
# CRYPTO ASSET DEFINITIONS
# =============================================================================

# All 53 crypto pairs with realistic parameters
# Prices as of late 2024, volatility based on historical behavior
# volume_base is the mean traded quantity per minute in BASE-ASSET units (BTC
# for BTCUSD), as on an exchange. Levels follow relative liquidity anchored on
# BTC at ~$1.26M per minute (Binance BTCUSDT, Feb 2024); ETH and SOL land
# within 1.5x of their measured Binance volume.
# Categories: large_cap, layer1, layer2, defi, gaming, infrastructure

CRYPTO_ASSETS_DATA = {
    # Large Cap (Top 10 by market cap)
    "BTCUSD": AssetParams("BTCUSD", 67500.00, 0.55, 0.05, 18.7, 0.6),
    "ETHUSD": AssetParams("ETHUSD", 3450.00, 0.65, 0.04, 292, 0.6),
    "BNBUSD": AssetParams("BNBUSD", 580.00, 0.60, 0.03, 652, 0.55),
    "SOLUSD": AssetParams("SOLUSD", 175.00, 0.85, 0.06, 2880, 0.65),
    "XRPUSD": AssetParams("XRPUSD", 0.62, 0.70, 0.02, 1016129, 0.6),
    "ADAUSD": AssetParams("ADAUSD", 0.58, 0.75, 0.02, 782069, 0.6),
    "DOGEUSD": AssetParams("DOGEUSD", 0.165, 0.90, 0.01, 4581818, 0.7),
    "TRXUSD": AssetParams("TRXUSD", 0.125, 0.60, 0.02, 2419200, 0.55),
    "AVAXUSD": AssetParams("AVAXUSD", 42.50, 0.80, 0.04, 7115, 0.65),
    "DOTUSD": AssetParams("DOTUSD", 7.80, 0.75, 0.02, 32308, 0.6),
    # Layer 1 Platforms
    "MATICUSD": AssetParams("MATICUSD", 0.72, 0.80, 0.03, 525000, 0.65),
    "LTCUSD": AssetParams("LTCUSD", 85.00, 0.65, 0.01, 2372, 0.55),
    "BCHUSD": AssetParams("BCHUSD", 485.00, 0.70, 0.01, 260, 0.6),
    "LINKUSD": AssetParams("LINKUSD", 18.50, 0.75, 0.04, 16346, 0.6),
    "ATOMUSD": AssetParams("ATOMUSD", 10.20, 0.80, 0.03, 19765, 0.65),
    "XLMUSD": AssetParams("XLMUSD", 0.128, 0.70, 0.01, 1968750, 0.6),
    "NEARUSD": AssetParams("NEARUSD", 7.50, 0.85, 0.05, 26880, 0.65),
    "ICPUSD": AssetParams("ICPUSD", 14.20, 0.90, 0.03, 8873, 0.7),
    "APTUSD": AssetParams("APTUSD", 11.80, 0.85, 0.04, 12814, 0.65),
    "ETCUSD": AssetParams("ETCUSD", 28.50, 0.75, 0.01, 5305, 0.6),
    "EOSUSD": AssetParams("EOSUSD", 0.82, 0.70, 0.0, 153659, 0.6),
    "XTZUSD": AssetParams("XTZUSD", 1.05, 0.75, 0.01, 96000, 0.6),
    "EGLDUSD": AssetParams("EGLDUSD", 42.00, 0.80, 0.02, 1800, 0.65),
    "ALGOUSD": AssetParams("ALGOUSD", 0.22, 0.75, 0.01, 572727, 0.6),
    "THETAUSD": AssetParams("THETAUSD", 2.15, 0.85, 0.02, 46884, 0.65),
    "FLOWUSD": AssetParams("FLOWUSD", 0.95, 0.85, 0.02, 79579, 0.65),
    "NEOUSD": AssetParams("NEOUSD", 14.50, 0.75, 0.01, 5214, 0.6),
    "WAVESUSD": AssetParams("WAVESUSD", 2.45, 0.90, 0.0, 25714, 0.7),
    "KAVAUSD": AssetParams("KAVAUSD", 0.58, 0.80, 0.02, 86897, 0.65),
    # Layer 2 / Scaling
    "ARBUSD": AssetParams("ARBUSD", 1.25, 0.85, 0.05, 161280, 0.65),
    "OPUSD": AssetParams("OPUSD", 2.85, 0.85, 0.05, 61895, 0.65),
    # DeFi
    "AAVEUSD": AssetParams("AAVEUSD", 168.00, 0.80, 0.04, 600, 0.65),
    "UNIUSD": AssetParams("UNIUSD", 11.50, 0.80, 0.03, 13148, 0.65),
    "MKRUSD": AssetParams("MKRUSD", 2850.00, 0.75, 0.03, 13.3, 0.6),
    "SNXUSD": AssetParams("SNXUSD", 3.25, 0.90, 0.02, 23262, 0.7),
    "SUSHIUSD": AssetParams("SUSHIUSD", 1.45, 0.95, 0.01, 52138, 0.7),
    "COMPUSD": AssetParams("COMPUSD", 62.00, 0.80, 0.02, 813, 0.65),
    "CRVUSD": AssetParams("CRVUSD", 0.52, 0.90, 0.02, 193846, 0.7),
    "LDOUSD": AssetParams("LDOUSD", 2.15, 0.85, 0.04, 58605, 0.65),
    "DYDXUSD": AssetParams("DYDXUSD", 2.45, 0.90, 0.03, 30857, 0.7),
    "CAKEUSD": AssetParams("CAKEUSD", 2.75, 0.85, 0.02, 27491, 0.65),
    # Infrastructure / Oracle
    "GRTUSD": AssetParams("GRTUSD", 0.28, 0.85, 0.03, 450000, 0.65),
    "FILUSD": AssetParams("FILUSD", 6.20, 0.85, 0.02, 20323, 0.65),
    "INJUSD": AssetParams("INJUSD", 35.00, 0.90, 0.05, 2880, 0.7),
    "IMXUSD": AssetParams("IMXUSD", 2.45, 0.90, 0.04, 41143, 0.7),
    # Gaming / Metaverse
    "AXSUSD": AssetParams("AXSUSD", 8.50, 0.95, 0.01, 11859, 0.7),
    "SANDUSD": AssetParams("SANDUSD", 0.48, 0.95, 0.02, 262500, 0.7),
    "MANAUSD": AssetParams("MANAUSD", 0.52, 0.95, 0.01, 242308, 0.7),
    "APEUSD": AssetParams("APEUSD", 1.55, 1.00, 0.0, 65032, 0.75),
    # Other
    "RUNEUSD": AssetParams("RUNEUSD", 5.80, 0.90, 0.03, 13034, 0.7),
    "KSMUSD": AssetParams("KSMUSD", 32.00, 0.90, 0.02, 1575, 0.7),
    "ZECUSD": AssetParams("ZECUSD", 28.00, 0.75, 0.0, 2250, 0.6),
    "DASHUSD": AssetParams("DASHUSD", 32.00, 0.70, 0.0, 1575, 0.6),
}


# =============================================================================
# CORRELATION MATRIX BUILDING
# =============================================================================


def _build_crypto_correlation_matrix() -> tuple[np.ndarray, list[str]]:
    """
    Build the correlation matrix for crypto assets.

    Correlations are based on:
    - BTC dominance (all alts correlated with BTC)
    - ETH ecosystem correlation
    - Sector groupings (DeFi, Gaming, L1s)
    - Market cap tiers

    Returns:
        Tuple of (correlation_matrix, symbol_order)
    """
    symbols = list(CRYPTO_ASSETS_DATA.keys())
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


# =============================================================================
# PUBLIC API
# =============================================================================


def get_crypto_config() -> MarketConfig:
    """
    Get the complete crypto market configuration.

    Returns:
        MarketConfig with 53 crypto assets and correlation matrix.
    """
    correlation_matrix, symbol_order = _build_crypto_correlation_matrix()

    return MarketConfig(
        market_type=MarketType.CRYPTO,
        assets=CRYPTO_ASSETS_DATA,
        correlation_matrix=correlation_matrix,
        asset_order=symbol_order,
    )
