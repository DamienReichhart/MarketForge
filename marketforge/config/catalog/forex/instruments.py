# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the MIT License. See the LICENSE file in the project
# root for full license information.

"""Forex catalog: 81 instruments (currency pairs plus metal, index and oil CFDs): start prices, volatilities, drifts and volumes."""

from __future__ import annotations

from marketforge.config.catalog.schema import InstrumentParams

# All 81 forex instruments with realistic parameters
# Volatility is annualized, based on typical daily ranges
# volume_base is TICK VOLUME: mean number of price updates per minute, as
# reported by retail FX/CFD platforms (FX has no consolidated traded volume).
# Estimated, not measured: EURUSD ~60/min, other pairs scaled by the square
# root of their relative liquidity, at least 5. Generated values are integers.
INSTRUMENTS = {
    # Major Pairs (highest liquidity)
    "EURUSD": InstrumentParams("EURUSD", 1.0850, 0.065, 0.0, 60, 0.4),
    "GBPUSD": InstrumentParams("GBPUSD", 1.2650, 0.080, 0.0, 54, 0.4),
    "USDJPY": InstrumentParams("USDJPY", 149.50, 0.085, 0.0, 57, 0.4),
    "USDCHF": InstrumentParams("USDCHF", 0.8750, 0.070, 0.0, 42, 0.4),
    "AUDUSD": InstrumentParams("AUDUSD", 0.6550, 0.095, 0.0, 38, 0.45),
    "USDCAD": InstrumentParams("USDCAD", 1.3650, 0.065, 0.0, 40, 0.4),
    "NZDUSD": InstrumentParams("NZDUSD", 0.6100, 0.100, 0.0, 27, 0.45),
    # EUR Crosses
    "EURCHF": InstrumentParams("EURCHF", 0.9500, 0.050, 0.0, 33, 0.4),
    "EURGBP": InstrumentParams("EURGBP", 0.8580, 0.060, 0.0, 38, 0.4),
    "EURJPY": InstrumentParams("EURJPY", 162.20, 0.095, 0.0, 42, 0.45),
    "EURAUD": InstrumentParams("EURAUD", 1.6560, 0.100, 0.0, 27, 0.45),
    "EURCAD": InstrumentParams("EURCAD", 1.4800, 0.080, 0.0, 27, 0.45),
    "EURNZD": InstrumentParams("EURNZD", 1.7800, 0.105, 0.0, 19, 0.5),
    "EURHUF": InstrumentParams("EURHUF", 390.00, 0.120, 0.0, 13, 0.5),
    "EURPLN": InstrumentParams("EURPLN", 4.3200, 0.100, 0.0, 13, 0.5),
    "EURCZK": InstrumentParams("EURCZK", 25.20, 0.060, 0.0, 10, 0.5),
    "EURSEK": InstrumentParams("EURSEK", 11.35, 0.085, 0.0, 17, 0.5),
    "EURDKK": InstrumentParams("EURDKK", 7.4560, 0.015, 0.0, 13, 0.3),
    "EURNOK": InstrumentParams("EURNOK", 11.65, 0.100, 0.0, 15, 0.5),
    "EURTRY": InstrumentParams("EURTRY", 32.50, 0.250, 0.02, 12, 0.6),
    "EURMXN": InstrumentParams("EURMXN", 18.80, 0.140, 0.0, 10, 0.55),
    # GBP Crosses
    "GBPCHF": InstrumentParams("GBPCHF", 1.1050, 0.085, 0.0, 23, 0.45),
    "GBPJPY": InstrumentParams("GBPJPY", 189.00, 0.110, 0.0, 33, 0.5),
    "GBPAUD": InstrumentParams("GBPAUD", 1.9300, 0.105, 0.0, 19, 0.5),
    "GBPNZD": InstrumentParams("GBPNZD", 2.0750, 0.115, 0.0, 17, 0.5),
    "GBPCAD": InstrumentParams("GBPCAD", 1.7280, 0.090, 0.0, 19, 0.45),
    # JPY Crosses
    "AUDJPY": InstrumentParams("AUDJPY", 97.80, 0.110, 0.0, 27, 0.5),
    "CHFJPY": InstrumentParams("CHFJPY", 170.80, 0.090, 0.0, 23, 0.45),
    "NZDJPY": InstrumentParams("NZDJPY", 91.20, 0.115, 0.0, 19, 0.5),
    "CADJPY": InstrumentParams("CADJPY", 109.50, 0.100, 0.0, 23, 0.45),
    "SGDJPY": InstrumentParams("SGDJPY", 111.80, 0.085, 0.0, 13, 0.45),
    "ZARJPY": InstrumentParams("ZARJPY", 8.05, 0.150, 0.0, 10, 0.55),
    "MXNJPY": InstrumentParams("MXNJPY", 8.65, 0.130, 0.0, 10, 0.55),
    "TRYJPY": InstrumentParams("TRYJPY", 4.60, 0.280, -0.02, 8, 0.6),
    "NOKJPY": InstrumentParams("NOKJPY", 13.85, 0.110, 0.0, 10, 0.5),
    "SEKJPY": InstrumentParams("SEKJPY", 13.15, 0.105, 0.0, 10, 0.5),
    # AUD/NZD Crosses
    "AUDCAD": InstrumentParams("AUDCAD", 0.8950, 0.090, 0.0, 19, 0.45),
    "AUDCHF": InstrumentParams("AUDCHF", 0.5730, 0.095, 0.0, 17, 0.45),
    "AUDNZD": InstrumentParams("AUDNZD", 1.0740, 0.070, 0.0, 19, 0.4),
    "NZDCAD": InstrumentParams("NZDCAD", 0.8340, 0.095, 0.0, 13, 0.45),
    "NZDCHF": InstrumentParams("NZDCHF", 0.5340, 0.100, 0.0, 12, 0.5),
    # CAD/CHF Crosses
    "CADCHF": InstrumentParams("CADCHF", 0.6410, 0.080, 0.0, 15, 0.45),
    "CHFSGD": InstrumentParams("CHFSGD", 1.5250, 0.070, 0.0, 10, 0.45),
    # USD Exotic Pairs
    "USDMXN": InstrumentParams("USDMXN", 17.35, 0.130, 0.0, 27, 0.55),
    "USDTRY": InstrumentParams("USDTRY", 30.00, 0.250, 0.03, 23, 0.6),
    "USDZAR": InstrumentParams("USDZAR", 18.50, 0.160, 0.0, 19, 0.55),
    "USDHKD": InstrumentParams("USDHKD", 7.8200, 0.008, 0.0, 27, 0.3),
    "USDNOK": InstrumentParams("USDNOK", 10.75, 0.105, 0.0, 17, 0.5),
    "USDSEK": InstrumentParams("USDSEK", 10.45, 0.095, 0.0, 17, 0.5),
    "USDDKK": InstrumentParams("USDDKK", 6.8750, 0.065, 0.0, 13, 0.4),
    "USDSGD": InstrumentParams("USDSGD", 1.3380, 0.050, 0.0, 23, 0.4),
    "USDHUF": InstrumentParams("USDHUF", 360.00, 0.130, 0.0, 12, 0.5),
    "USDPLN": InstrumentParams("USDPLN", 3.9800, 0.110, 0.0, 13, 0.5),
    "USDCZK": InstrumentParams("USDCZK", 23.20, 0.080, 0.0, 10, 0.5),
    "USDCNH": InstrumentParams("USDCNH", 7.2500, 0.055, 0.0, 33, 0.4),
    "USDINR": InstrumentParams("USDINR", 83.20, 0.045, 0.005, 19, 0.4),
    "USDIDR": InstrumentParams("USDIDR", 15650.0, 0.065, 0.0, 13, 0.5),
    "USDTHB": InstrumentParams("USDTHB", 35.50, 0.060, 0.0, 13, 0.45),
    "USDPHP": InstrumentParams("USDPHP", 56.20, 0.055, 0.0, 12, 0.45),
    "USDTWD": InstrumentParams("USDTWD", 31.80, 0.045, 0.0, 15, 0.4),
    "USDILS": InstrumentParams("USDILS", 3.7200, 0.085, 0.0, 12, 0.5),
    # Precious Metals
    "XAUUSD": InstrumentParams("XAUUSD", 2350.00, 0.140, 0.005, 42, 0.5),
    "XAGUSD": InstrumentParams("XAGUSD", 28.50, 0.220, 0.0, 27, 0.55),
    "XAUEUR": InstrumentParams("XAUEUR", 2165.00, 0.135, 0.005, 23, 0.5),
    "XAUGBP": InstrumentParams("XAUGBP", 1860.00, 0.140, 0.005, 19, 0.5),
    "XAUCHF": InstrumentParams("XAUCHF", 2055.00, 0.130, 0.005, 17, 0.5),
    "XAUAUD": InstrumentParams("XAUAUD", 3590.00, 0.150, 0.005, 15, 0.55),
    "XPTUSD": InstrumentParams("XPTUSD", 980.00, 0.200, 0.0, 13, 0.55),
    "XPDUSD": InstrumentParams("XPDUSD", 1050.00, 0.250, 0.0, 12, 0.6),
    # Indices (CFD-style)
    "GRXEUR": InstrumentParams("GRXEUR", 4250.00, 0.180, 0.0, 8, 0.5),
    "FRXEUR": InstrumentParams("FRXEUR", 7650.00, 0.160, 0.0, 10, 0.5),
    "HKXHKD": InstrumentParams("HKXHKD", 17500.0, 0.180, 0.0, 8, 0.5),
    "SPXUSD": InstrumentParams("SPXUSD", 5150.00, 0.150, 0.008, 13, 0.45),
    "NSXUSD": InstrumentParams("NSXUSD", 18200.0, 0.180, 0.010, 12, 0.5),
    "JPXJPY": InstrumentParams("JPXJPY", 39500.0, 0.170, 0.0, 10, 0.5),
    "UKXGBP": InstrumentParams("UKXGBP", 8150.00, 0.140, 0.003, 10, 0.45),
    "ETXEUR": InstrumentParams("ETXEUR", 4950.00, 0.160, 0.0, 9, 0.5),
    "AUXAUD": InstrumentParams("AUXAUD", 7850.00, 0.160, 0.0, 8, 0.5),
    "UDXUSD": InstrumentParams("UDXUSD", 104.50, 0.070, 0.0, 10, 0.4),
    # Commodities
    "BCOUSD": InstrumentParams("BCOUSD", 82.50, 0.280, 0.0, 33, 0.55),
    "WTIUSD": InstrumentParams("WTIUSD", 78.50, 0.300, 0.0, 38, 0.55),
}
