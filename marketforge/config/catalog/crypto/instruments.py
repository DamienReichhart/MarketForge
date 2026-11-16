# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the MIT License. See the LICENSE file in the project
# root for full license information.

"""Crypto catalog: 53 cryptocurrency pairs: start prices, volatilities, drifts and volumes."""

from __future__ import annotations

from marketforge.config.catalog.schema import AssetParams

# All 53 crypto pairs with realistic parameters
# Prices as of late 2024, volatility based on historical behavior
# volume_base is the mean traded quantity per minute in BASE-ASSET units (BTC
# for BTCUSD), as on an exchange. Levels follow relative liquidity anchored on
# BTC at ~$1.26M per minute (Binance BTCUSDT, Feb 2024); ETH and SOL land
# within 1.5x of their measured Binance volume.
INSTRUMENTS = {
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
