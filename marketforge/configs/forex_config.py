# MarketForge
# Copyright (C) 2026 REICHHART Damien
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""
Forex market configuration with 82 currency pairs.

Contains realistic start prices, volatilities, drifts, and correlation matrix
based on typical forex market relationships.
"""

from __future__ import annotations

import numpy as np

from marketforge.configs.base import (
    AssetParams,
    MarketConfig,
    MarketType,
    ensure_positive_semidefinite,
)


# =============================================================================
# FOREX ASSET DEFINITIONS
# =============================================================================

# All 82 forex pairs with realistic parameters
# Volatility is annualized, based on typical daily ranges
# Volume base scaled appropriately for each pair type

FOREX_ASSETS_DATA = {
    # Major Pairs (highest liquidity)
    "EURUSD": AssetParams("EURUSD", 1.0850, 0.065, 0.0, 10000000, 0.4, "major"),
    "GBPUSD": AssetParams("GBPUSD", 1.2650, 0.080, 0.0, 8000000, 0.4, "major"),
    "USDJPY": AssetParams("USDJPY", 149.50, 0.085, 0.0, 9000000, 0.4, "major"),
    "USDCHF": AssetParams("USDCHF", 0.8750, 0.070, 0.0, 5000000, 0.4, "major"),
    "AUDUSD": AssetParams("AUDUSD", 0.6550, 0.095, 0.0, 4000000, 0.45, "major"),
    "USDCAD": AssetParams("USDCAD", 1.3650, 0.065, 0.0, 4500000, 0.4, "major"),
    "NZDUSD": AssetParams("NZDUSD", 0.6100, 0.100, 0.0, 2000000, 0.45, "major"),
    
    # EUR Crosses
    "EURCHF": AssetParams("EURCHF", 0.9500, 0.050, 0.0, 3000000, 0.4, "eur_cross"),
    "EURGBP": AssetParams("EURGBP", 0.8580, 0.060, 0.0, 4000000, 0.4, "eur_cross"),
    "EURJPY": AssetParams("EURJPY", 162.20, 0.095, 0.0, 5000000, 0.45, "eur_cross"),
    "EURAUD": AssetParams("EURAUD", 1.6560, 0.100, 0.0, 2000000, 0.45, "eur_cross"),
    "EURCAD": AssetParams("EURCAD", 1.4800, 0.080, 0.0, 2000000, 0.45, "eur_cross"),
    "EURNZD": AssetParams("EURNZD", 1.7800, 0.105, 0.0, 1000000, 0.5, "eur_cross"),
    "EURHUF": AssetParams("EURHUF", 390.00, 0.120, 0.0, 500000, 0.5, "eur_exotic"),
    "EURPLN": AssetParams("EURPLN", 4.3200, 0.100, 0.0, 500000, 0.5, "eur_exotic"),
    "EURCZK": AssetParams("EURCZK", 25.20, 0.060, 0.0, 300000, 0.5, "eur_exotic"),
    "EURSEK": AssetParams("EURSEK", 11.35, 0.085, 0.0, 800000, 0.5, "eur_cross"),
    "EURDKK": AssetParams("EURDKK", 7.4560, 0.015, 0.0, 500000, 0.3, "eur_cross"),
    "EURNOK": AssetParams("EURNOK", 11.65, 0.100, 0.0, 600000, 0.5, "eur_cross"),
    "EURTRY": AssetParams("EURTRY", 32.50, 0.250, 0.02, 400000, 0.6, "eur_exotic"),
    "EURMXN": AssetParams("EURMXN", 18.80, 0.140, 0.0, 300000, 0.55, "eur_exotic"),
    
    # GBP Crosses
    "GBPCHF": AssetParams("GBPCHF", 1.1050, 0.085, 0.0, 1500000, 0.45, "gbp_cross"),
    "GBPJPY": AssetParams("GBPJPY", 189.00, 0.110, 0.0, 3000000, 0.5, "gbp_cross"),
    "GBPAUD": AssetParams("GBPAUD", 1.9300, 0.105, 0.0, 1000000, 0.5, "gbp_cross"),
    "GBPNZD": AssetParams("GBPNZD", 2.0750, 0.115, 0.0, 800000, 0.5, "gbp_cross"),
    "GBPCAD": AssetParams("GBPCAD", 1.7280, 0.090, 0.0, 1000000, 0.45, "gbp_cross"),
    
    # JPY Crosses
    "AUDJPY": AssetParams("AUDJPY", 97.80, 0.110, 0.0, 2000000, 0.5, "jpy_cross"),
    "CHFJPY": AssetParams("CHFJPY", 170.80, 0.090, 0.0, 1500000, 0.45, "jpy_cross"),
    "NZDJPY": AssetParams("NZDJPY", 91.20, 0.115, 0.0, 1000000, 0.5, "jpy_cross"),
    "CADJPY": AssetParams("CADJPY", 109.50, 0.100, 0.0, 1500000, 0.45, "jpy_cross"),
    "SGDJPY": AssetParams("SGDJPY", 111.80, 0.085, 0.0, 500000, 0.45, "jpy_cross"),
    "ZARJPY": AssetParams("ZARJPY", 8.05, 0.150, 0.0, 300000, 0.55, "jpy_exotic"),
    "MXNJPY": AssetParams("MXNJPY", 8.65, 0.130, 0.0, 300000, 0.55, "jpy_exotic"),
    "TRYJPY": AssetParams("TRYJPY", 4.60, 0.280, -0.02, 200000, 0.6, "jpy_exotic"),
    "NOKJPY": AssetParams("NOKJPY", 13.85, 0.110, 0.0, 300000, 0.5, "jpy_cross"),
    "SEKJPY": AssetParams("SEKJPY", 13.15, 0.105, 0.0, 300000, 0.5, "jpy_cross"),
    
    # AUD/NZD Crosses
    "AUDCAD": AssetParams("AUDCAD", 0.8950, 0.090, 0.0, 1000000, 0.45, "commodity"),
    "AUDCHF": AssetParams("AUDCHF", 0.5730, 0.095, 0.0, 800000, 0.45, "commodity"),
    "AUDNZD": AssetParams("AUDNZD", 1.0740, 0.070, 0.0, 1000000, 0.4, "commodity"),
    "NZDCAD": AssetParams("NZDCAD", 0.8340, 0.095, 0.0, 500000, 0.45, "commodity"),
    "NZDCHF": AssetParams("NZDCHF", 0.5340, 0.100, 0.0, 400000, 0.5, "commodity"),
    
    # CAD/CHF Crosses
    "CADCHF": AssetParams("CADCHF", 0.6410, 0.080, 0.0, 600000, 0.45, "cross"),
    "CHFSGD": AssetParams("CHFSGD", 1.5250, 0.070, 0.0, 300000, 0.45, "cross"),
    
    # USD Exotic Pairs
    "USDMXN": AssetParams("USDMXN", 17.35, 0.130, 0.0, 2000000, 0.55, "usd_exotic"),
    "USDTRY": AssetParams("USDTRY", 30.00, 0.250, 0.03, 1500000, 0.6, "usd_exotic"),
    "USDZAR": AssetParams("USDZAR", 18.50, 0.160, 0.0, 1000000, 0.55, "usd_exotic"),
    "USDHKD": AssetParams("USDHKD", 7.8200, 0.008, 0.0, 2000000, 0.3, "usd_pegged"),
    "USDNOK": AssetParams("USDNOK", 10.75, 0.105, 0.0, 800000, 0.5, "usd_cross"),
    "USDSEK": AssetParams("USDSEK", 10.45, 0.095, 0.0, 800000, 0.5, "usd_cross"),
    "USDDKK": AssetParams("USDDKK", 6.8750, 0.065, 0.0, 500000, 0.4, "usd_cross"),
    "USDSGD": AssetParams("USDSGD", 1.3380, 0.050, 0.0, 1500000, 0.4, "usd_cross"),
    "USDHUF": AssetParams("USDHUF", 360.00, 0.130, 0.0, 400000, 0.5, "usd_exotic"),
    "USDPLN": AssetParams("USDPLN", 3.9800, 0.110, 0.0, 500000, 0.5, "usd_exotic"),
    "USDCZK": AssetParams("USDCZK", 23.20, 0.080, 0.0, 300000, 0.5, "usd_exotic"),
    "USDCNH": AssetParams("USDCNH", 7.2500, 0.055, 0.0, 3000000, 0.4, "usd_asia"),
    "USDINR": AssetParams("USDINR", 83.20, 0.045, 0.005, 1000000, 0.4, "usd_asia"),
    "USDIDR": AssetParams("USDIDR", 15650.0, 0.065, 0.0, 500000, 0.5, "usd_asia"),
    "USDTHB": AssetParams("USDTHB", 35.50, 0.060, 0.0, 500000, 0.45, "usd_asia"),
    "USDPHP": AssetParams("USDPHP", 56.20, 0.055, 0.0, 400000, 0.45, "usd_asia"),
    "USDTWD": AssetParams("USDTWD", 31.80, 0.045, 0.0, 600000, 0.4, "usd_asia"),
    "USDILS": AssetParams("USDILS", 3.7200, 0.085, 0.0, 400000, 0.5, "usd_exotic"),
    
    # Precious Metals
    "XAUUSD": AssetParams("XAUUSD", 2350.00, 0.140, 0.005, 5000000, 0.5, "metal"),
    "XAGUSD": AssetParams("XAGUSD", 28.50, 0.220, 0.0, 2000000, 0.55, "metal"),
    "XAUEUR": AssetParams("XAUEUR", 2165.00, 0.135, 0.005, 1500000, 0.5, "metal"),
    "XAUGBP": AssetParams("XAUGBP", 1860.00, 0.140, 0.005, 1000000, 0.5, "metal"),
    "XAUCHF": AssetParams("XAUCHF", 2055.00, 0.130, 0.005, 800000, 0.5, "metal"),
    "XAUAUD": AssetParams("XAUAUD", 3590.00, 0.150, 0.005, 600000, 0.55, "metal"),
    "XPTUSD": AssetParams("XPTUSD", 980.00, 0.200, 0.0, 500000, 0.55, "metal"),
    "XPDUSD": AssetParams("XPDUSD", 1050.00, 0.250, 0.0, 400000, 0.6, "metal"),
    
    # Indices (CFD-style)
    "GRXEUR": AssetParams("GRXEUR", 4250.00, 0.180, 0.0, 200000, 0.5, "index"),
    "FRXEUR": AssetParams("FRXEUR", 7650.00, 0.160, 0.0, 300000, 0.5, "index"),
    "HKXHKD": AssetParams("HKXHKD", 17500.0, 0.180, 0.0, 200000, 0.5, "index"),
    "SPXUSD": AssetParams("SPXUSD", 5150.00, 0.150, 0.008, 500000, 0.45, "index"),
    "NSXUSD": AssetParams("NSXUSD", 18200.0, 0.180, 0.010, 400000, 0.5, "index"),
    "JPXJPY": AssetParams("JPXJPY", 39500.0, 0.170, 0.0, 300000, 0.5, "index"),
    "UKXGBP": AssetParams("UKXGBP", 8150.00, 0.140, 0.003, 300000, 0.45, "index"),
    "ETXEUR": AssetParams("ETXEUR", 4950.00, 0.160, 0.0, 250000, 0.5, "index"),
    "AUXAUD": AssetParams("AUXAUD", 7850.00, 0.160, 0.0, 200000, 0.5, "index"),
    "UDXUSD": AssetParams("UDXUSD", 104.50, 0.070, 0.0, 300000, 0.4, "index"),
    
    # Commodities
    "BCOUSD": AssetParams("BCOUSD", 82.50, 0.280, 0.0, 3000000, 0.55, "commodity_energy"),
    "WTIUSD": AssetParams("WTIUSD", 78.50, 0.300, 0.0, 4000000, 0.55, "commodity_energy"),
}


# =============================================================================
# CORRELATION MATRIX BUILDING
# =============================================================================

def _build_forex_correlation_matrix() -> tuple[np.ndarray, list[str]]:
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
    symbols = list(FOREX_ASSETS_DATA.keys())
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


# =============================================================================
# PUBLIC API
# =============================================================================

def get_forex_config() -> MarketConfig:
    """
    Get the complete forex market configuration.
    
    Returns:
        MarketConfig with 82 forex pairs and correlation matrix.
    """
    correlation_matrix, symbol_order = _build_forex_correlation_matrix()
    
    return MarketConfig(
        market_type=MarketType.FOREX,
        assets=FOREX_ASSETS_DATA,
        correlation_matrix=correlation_matrix,
        asset_order=symbol_order,
    )

