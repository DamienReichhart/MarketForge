# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the MIT License. See the LICENSE file in the project
# root for full license information.

"""Forex catalog: 81 instruments (currency pairs plus metal, index and oil CFDs): start prices, volatilities, drifts and volumes."""

from __future__ import annotations

from marketforge.config.catalog.schema import AssetParams

# All 81 forex instruments with realistic parameters
# Volatility is annualized, based on typical daily ranges
# volume_base is TICK VOLUME: mean number of price updates per minute, as
# reported by retail FX/CFD platforms (FX has no consolidated traded volume).
# Estimated, not measured: EURUSD ~60/min, other pairs scaled by the square
# root of their relative liquidity, at least 5. Generated values are integers.
INSTRUMENTS = {
    # Major Pairs (highest liquidity)
    "EURUSD": AssetParams("EURUSD", 1.0850, 0.065, 0.0, 60, 0.4),
    "GBPUSD": AssetParams("GBPUSD", 1.2650, 0.080, 0.0, 54, 0.4),
    "USDJPY": AssetParams("USDJPY", 149.50, 0.085, 0.0, 57, 0.4),
    "USDCHF": AssetParams("USDCHF", 0.8750, 0.070, 0.0, 42, 0.4),
    "AUDUSD": AssetParams("AUDUSD", 0.6550, 0.095, 0.0, 38, 0.45),
    "USDCAD": AssetParams("USDCAD", 1.3650, 0.065, 0.0, 40, 0.4),
    "NZDUSD": AssetParams("NZDUSD", 0.6100, 0.100, 0.0, 27, 0.45),
    # EUR Crosses
    "EURCHF": AssetParams("EURCHF", 0.9500, 0.050, 0.0, 33, 0.4),
    "EURGBP": AssetParams("EURGBP", 0.8580, 0.060, 0.0, 38, 0.4),
    "EURJPY": AssetParams("EURJPY", 162.20, 0.095, 0.0, 42, 0.45),
    "EURAUD": AssetParams("EURAUD", 1.6560, 0.100, 0.0, 27, 0.45),
    "EURCAD": AssetParams("EURCAD", 1.4800, 0.080, 0.0, 27, 0.45),
    "EURNZD": AssetParams("EURNZD", 1.7800, 0.105, 0.0, 19, 0.5),
    "EURHUF": AssetParams("EURHUF", 390.00, 0.120, 0.0, 13, 0.5),
    "EURPLN": AssetParams("EURPLN", 4.3200, 0.100, 0.0, 13, 0.5),
    "EURCZK": AssetParams("EURCZK", 25.20, 0.060, 0.0, 10, 0.5),
    "EURSEK": AssetParams("EURSEK", 11.35, 0.085, 0.0, 17, 0.5),
    "EURDKK": AssetParams("EURDKK", 7.4560, 0.015, 0.0, 13, 0.3),
    "EURNOK": AssetParams("EURNOK", 11.65, 0.100, 0.0, 15, 0.5),
    "EURTRY": AssetParams("EURTRY", 32.50, 0.250, 0.02, 12, 0.6),
    "EURMXN": AssetParams("EURMXN", 18.80, 0.140, 0.0, 10, 0.55),
    # GBP Crosses
    "GBPCHF": AssetParams("GBPCHF", 1.1050, 0.085, 0.0, 23, 0.45),
    "GBPJPY": AssetParams("GBPJPY", 189.00, 0.110, 0.0, 33, 0.5),
    "GBPAUD": AssetParams("GBPAUD", 1.9300, 0.105, 0.0, 19, 0.5),
    "GBPNZD": AssetParams("GBPNZD", 2.0750, 0.115, 0.0, 17, 0.5),
    "GBPCAD": AssetParams("GBPCAD", 1.7280, 0.090, 0.0, 19, 0.45),
    # JPY Crosses
    "AUDJPY": AssetParams("AUDJPY", 97.80, 0.110, 0.0, 27, 0.5),
    "CHFJPY": AssetParams("CHFJPY", 170.80, 0.090, 0.0, 23, 0.45),
    "NZDJPY": AssetParams("NZDJPY", 91.20, 0.115, 0.0, 19, 0.5),
    "CADJPY": AssetParams("CADJPY", 109.50, 0.100, 0.0, 23, 0.45),
    "SGDJPY": AssetParams("SGDJPY", 111.80, 0.085, 0.0, 13, 0.45),
    "ZARJPY": AssetParams("ZARJPY", 8.05, 0.150, 0.0, 10, 0.55),
    "MXNJPY": AssetParams("MXNJPY", 8.65, 0.130, 0.0, 10, 0.55),
    "TRYJPY": AssetParams("TRYJPY", 4.60, 0.280, -0.02, 8, 0.6),
    "NOKJPY": AssetParams("NOKJPY", 13.85, 0.110, 0.0, 10, 0.5),
    "SEKJPY": AssetParams("SEKJPY", 13.15, 0.105, 0.0, 10, 0.5),
    # AUD/NZD Crosses
    "AUDCAD": AssetParams("AUDCAD", 0.8950, 0.090, 0.0, 19, 0.45),
    "AUDCHF": AssetParams("AUDCHF", 0.5730, 0.095, 0.0, 17, 0.45),
    "AUDNZD": AssetParams("AUDNZD", 1.0740, 0.070, 0.0, 19, 0.4),
    "NZDCAD": AssetParams("NZDCAD", 0.8340, 0.095, 0.0, 13, 0.45),
    "NZDCHF": AssetParams("NZDCHF", 0.5340, 0.100, 0.0, 12, 0.5),
    # CAD/CHF Crosses
    "CADCHF": AssetParams("CADCHF", 0.6410, 0.080, 0.0, 15, 0.45),
    "CHFSGD": AssetParams("CHFSGD", 1.5250, 0.070, 0.0, 10, 0.45),
    # USD Exotic Pairs
    "USDMXN": AssetParams("USDMXN", 17.35, 0.130, 0.0, 27, 0.55),
    "USDTRY": AssetParams("USDTRY", 30.00, 0.250, 0.03, 23, 0.6),
    "USDZAR": AssetParams("USDZAR", 18.50, 0.160, 0.0, 19, 0.55),
    "USDHKD": AssetParams("USDHKD", 7.8200, 0.008, 0.0, 27, 0.3),
    "USDNOK": AssetParams("USDNOK", 10.75, 0.105, 0.0, 17, 0.5),
    "USDSEK": AssetParams("USDSEK", 10.45, 0.095, 0.0, 17, 0.5),
    "USDDKK": AssetParams("USDDKK", 6.8750, 0.065, 0.0, 13, 0.4),
    "USDSGD": AssetParams("USDSGD", 1.3380, 0.050, 0.0, 23, 0.4),
    "USDHUF": AssetParams("USDHUF", 360.00, 0.130, 0.0, 12, 0.5),
    "USDPLN": AssetParams("USDPLN", 3.9800, 0.110, 0.0, 13, 0.5),
    "USDCZK": AssetParams("USDCZK", 23.20, 0.080, 0.0, 10, 0.5),
    "USDCNH": AssetParams("USDCNH", 7.2500, 0.055, 0.0, 33, 0.4),
    "USDINR": AssetParams("USDINR", 83.20, 0.045, 0.005, 19, 0.4),
    "USDIDR": AssetParams("USDIDR", 15650.0, 0.065, 0.0, 13, 0.5),
    "USDTHB": AssetParams("USDTHB", 35.50, 0.060, 0.0, 13, 0.45),
    "USDPHP": AssetParams("USDPHP", 56.20, 0.055, 0.0, 12, 0.45),
    "USDTWD": AssetParams("USDTWD", 31.80, 0.045, 0.0, 15, 0.4),
    "USDILS": AssetParams("USDILS", 3.7200, 0.085, 0.0, 12, 0.5),
    # Precious Metals
    "XAUUSD": AssetParams("XAUUSD", 2350.00, 0.140, 0.005, 42, 0.5),
    "XAGUSD": AssetParams("XAGUSD", 28.50, 0.220, 0.0, 27, 0.55),
    "XAUEUR": AssetParams("XAUEUR", 2165.00, 0.135, 0.005, 23, 0.5),
    "XAUGBP": AssetParams("XAUGBP", 1860.00, 0.140, 0.005, 19, 0.5),
    "XAUCHF": AssetParams("XAUCHF", 2055.00, 0.130, 0.005, 17, 0.5),
    "XAUAUD": AssetParams("XAUAUD", 3590.00, 0.150, 0.005, 15, 0.55),
    "XPTUSD": AssetParams("XPTUSD", 980.00, 0.200, 0.0, 13, 0.55),
    "XPDUSD": AssetParams("XPDUSD", 1050.00, 0.250, 0.0, 12, 0.6),
    # Indices (CFD-style)
    "GRXEUR": AssetParams("GRXEUR", 4250.00, 0.180, 0.0, 8, 0.5),
    "FRXEUR": AssetParams("FRXEUR", 7650.00, 0.160, 0.0, 10, 0.5),
    "HKXHKD": AssetParams("HKXHKD", 17500.0, 0.180, 0.0, 8, 0.5),
    "SPXUSD": AssetParams("SPXUSD", 5150.00, 0.150, 0.008, 13, 0.45),
    "NSXUSD": AssetParams("NSXUSD", 18200.0, 0.180, 0.010, 12, 0.5),
    "JPXJPY": AssetParams("JPXJPY", 39500.0, 0.170, 0.0, 10, 0.5),
    "UKXGBP": AssetParams("UKXGBP", 8150.00, 0.140, 0.003, 10, 0.45),
    "ETXEUR": AssetParams("ETXEUR", 4950.00, 0.160, 0.0, 9, 0.5),
    "AUXAUD": AssetParams("AUXAUD", 7850.00, 0.160, 0.0, 8, 0.5),
    "UDXUSD": AssetParams("UDXUSD", 104.50, 0.070, 0.0, 10, 0.4),
    # Commodities
    "BCOUSD": AssetParams("BCOUSD", 82.50, 0.280, 0.0, 33, 0.55),
    "WTIUSD": AssetParams("WTIUSD", 78.50, 0.300, 0.0, 38, 0.55),
}
