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
US Stocks market configuration with 73 major stocks.

Contains realistic start prices, volatilities, drifts, and correlation matrix
based on typical stock market relationships and sector groupings.
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
# STOCKS ASSET DEFINITIONS
# =============================================================================

# All 73 stocks with realistic parameters
# Prices as of late 2024, volatility based on historical behavior
# Volume in thousands of shares

STOCKS_ASSETS_DATA = {
    # Technology - Mega Cap
    "AAPL": AssetParams("AAPL", 185.00, 0.25, 0.08, 50000, 0.45, "tech_mega"),
    "MSFT": AssetParams("MSFT", 415.00, 0.24, 0.10, 25000, 0.45, "tech_mega"),
    "GOOGL": AssetParams("GOOGL", 165.00, 0.28, 0.08, 25000, 0.48, "tech_mega"),
    "GOOG": AssetParams("GOOG", 167.00, 0.28, 0.08, 15000, 0.48, "tech_mega"),
    "AMZN": AssetParams("AMZN", 195.00, 0.30, 0.10, 40000, 0.50, "tech_mega"),
    "NVDA": AssetParams("NVDA", 875.00, 0.50, 0.15, 45000, 0.55, "tech_semi"),
    "META": AssetParams("META", 520.00, 0.38, 0.12, 20000, 0.52, "tech_mega"),
    "TSLA": AssetParams("TSLA", 245.00, 0.55, 0.08, 80000, 0.60, "tech_auto"),
    
    # Technology - Software/Cloud
    "ADBE": AssetParams("ADBE", 575.00, 0.32, 0.08, 3000, 0.50, "tech_software"),
    "CRM": AssetParams("CRM", 285.00, 0.32, 0.10, 6000, 0.50, "tech_software"),
    "ORCL": AssetParams("ORCL", 145.00, 0.28, 0.08, 8000, 0.48, "tech_software"),
    "NOW": AssetParams("NOW", 825.00, 0.35, 0.12, 2000, 0.52, "tech_software"),
    "PANW": AssetParams("PANW", 315.00, 0.38, 0.12, 3500, 0.52, "tech_software"),
    "SNOW": AssetParams("SNOW", 175.00, 0.50, 0.10, 4000, 0.58, "tech_software"),
    
    # Technology - Semiconductors
    "AMD": AssetParams("AMD", 165.00, 0.45, 0.12, 35000, 0.55, "tech_semi"),
    "QCOM": AssetParams("QCOM", 175.00, 0.35, 0.08, 8000, 0.50, "tech_semi"),
    "INTC": AssetParams("INTC", 42.00, 0.38, 0.02, 30000, 0.52, "tech_semi"),
    "AVGO": AssetParams("AVGO", 1450.00, 0.32, 0.10, 3000, 0.48, "tech_semi"),
    "TXN": AssetParams("TXN", 185.00, 0.28, 0.08, 5000, 0.48, "tech_semi"),
    "LRCX": AssetParams("LRCX", 960.00, 0.38, 0.10, 2000, 0.52, "tech_semi"),
    "MU": AssetParams("MU", 115.00, 0.45, 0.08, 15000, 0.55, "tech_semi"),
    "ADI": AssetParams("ADI", 225.00, 0.30, 0.08, 3500, 0.48, "tech_semi"),
    
    # Technology - Internet/Services
    "NFLX": AssetParams("NFLX", 685.00, 0.40, 0.10, 5000, 0.52, "tech_internet"),
    "UBER": AssetParams("UBER", 72.00, 0.42, 0.10, 20000, 0.55, "tech_internet"),
    "BKNG": AssetParams("BKNG", 4150.00, 0.32, 0.08, 500, 0.50, "tech_internet"),
    
    # Financials - Banks
    "JPM": AssetParams("JPM", 195.00, 0.25, 0.08, 10000, 0.45, "financial_bank"),
    "GS": AssetParams("GS", 485.00, 0.30, 0.08, 2500, 0.48, "financial_bank"),
    "MS": AssetParams("MS", 98.00, 0.32, 0.08, 8000, 0.50, "financial_bank"),
    
    # Financials - Asset Management/Insurance
    "BLK": AssetParams("BLK", 825.00, 0.28, 0.08, 1000, 0.48, "financial_am"),
    "SCHW": AssetParams("SCHW", 72.00, 0.35, 0.06, 8000, 0.52, "financial_am"),
    "AXP": AssetParams("AXP", 235.00, 0.28, 0.08, 3000, 0.48, "financial_cc"),
    "V": AssetParams("V", 285.00, 0.22, 0.10, 7000, 0.42, "financial_cc"),
    "MA": AssetParams("MA", 475.00, 0.24, 0.10, 3500, 0.44, "financial_cc"),
    "SPGI": AssetParams("SPGI", 485.00, 0.25, 0.10, 1500, 0.45, "financial_data"),
    
    # Healthcare - Pharma
    "JNJ": AssetParams("JNJ", 158.00, 0.18, 0.05, 7000, 0.38, "health_pharma"),
    "LLY": AssetParams("LLY", 785.00, 0.32, 0.15, 4000, 0.50, "health_pharma"),
    "MRK": AssetParams("MRK", 125.00, 0.22, 0.06, 10000, 0.42, "health_pharma"),
    "ABBV": AssetParams("ABBV", 175.00, 0.24, 0.06, 6000, 0.44, "health_pharma"),
    "BMY": AssetParams("BMY", 52.00, 0.28, 0.03, 12000, 0.48, "health_pharma"),
    "AMGN": AssetParams("AMGN", 315.00, 0.24, 0.05, 3000, 0.44, "health_pharma"),
    "GILD": AssetParams("GILD", 85.00, 0.28, 0.04, 6000, 0.48, "health_pharma"),
    
    # Healthcare - Insurance/Services
    "UNH": AssetParams("UNH", 535.00, 0.22, 0.10, 4000, 0.42, "health_insurance"),
    "ELV": AssetParams("ELV", 515.00, 0.25, 0.08, 1500, 0.45, "health_insurance"),
    
    # Healthcare - Devices/Equipment
    "TMO": AssetParams("TMO", 585.00, 0.26, 0.08, 1500, 0.46, "health_device"),
    "ABT": AssetParams("ABT", 115.00, 0.22, 0.06, 6000, 0.42, "health_device"),
    "DHR": AssetParams("DHR", 275.00, 0.26, 0.08, 3000, 0.46, "health_device"),
    "MDT": AssetParams("MDT", 88.00, 0.25, 0.04, 6000, 0.45, "health_device"),
    "ISRG": AssetParams("ISRG", 425.00, 0.30, 0.10, 2000, 0.48, "health_device"),
    
    # Consumer - Retail
    "WMT": AssetParams("WMT", 165.00, 0.20, 0.08, 8000, 0.40, "consumer_retail"),
    "COST": AssetParams("COST", 725.00, 0.22, 0.10, 2500, 0.42, "consumer_retail"),
    "HD": AssetParams("HD", 365.00, 0.24, 0.08, 4000, 0.44, "consumer_retail"),
    "LOW": AssetParams("LOW", 235.00, 0.26, 0.07, 4000, 0.46, "consumer_retail"),
    
    # Consumer - Staples
    "PG": AssetParams("PG", 165.00, 0.18, 0.06, 7000, 0.38, "consumer_staples"),
    "KO": AssetParams("KO", 62.00, 0.16, 0.05, 12000, 0.36, "consumer_staples"),
    "PEP": AssetParams("PEP", 175.00, 0.18, 0.06, 5000, 0.38, "consumer_staples"),
    "PM": AssetParams("PM", 115.00, 0.20, 0.06, 5000, 0.40, "consumer_staples"),
    
    # Consumer - Discretionary
    "MCD": AssetParams("MCD", 295.00, 0.20, 0.08, 4000, 0.40, "consumer_disc"),
    "NKE": AssetParams("NKE", 105.00, 0.32, 0.06, 8000, 0.50, "consumer_disc"),
    "DIS": AssetParams("DIS", 115.00, 0.35, 0.04, 10000, 0.52, "consumer_disc"),
    
    # Industrials
    "CAT": AssetParams("CAT", 365.00, 0.28, 0.08, 2500, 0.48, "industrial"),
    "DE": AssetParams("DE", 415.00, 0.28, 0.07, 1500, 0.48, "industrial"),
    "HON": AssetParams("HON", 215.00, 0.24, 0.07, 3000, 0.44, "industrial"),
    "UPS": AssetParams("UPS", 145.00, 0.26, 0.05, 3000, 0.46, "industrial"),
    "RTX": AssetParams("RTX", 115.00, 0.25, 0.07, 5000, 0.45, "industrial_defense"),
    "LIN": AssetParams("LIN", 465.00, 0.22, 0.08, 1500, 0.42, "industrial"),
    "ACN": AssetParams("ACN", 365.00, 0.26, 0.09, 2000, 0.46, "industrial_services"),
    
    # Communication Services
    "VZ": AssetParams("VZ", 42.00, 0.22, 0.04, 15000, 0.42, "telecom"),
    "CMCSA": AssetParams("CMCSA", 42.00, 0.28, 0.05, 15000, 0.48, "telecom"),
    
    # Energy
    "XOM": AssetParams("XOM", 115.00, 0.28, 0.06, 15000, 0.48, "energy"),
    "CVX": AssetParams("CVX", 155.00, 0.26, 0.06, 8000, 0.46, "energy"),
    
    # Real Estate
    "PLD": AssetParams("PLD", 135.00, 0.28, 0.06, 4000, 0.48, "real_estate"),
    
    # Utilities
    "NEE": AssetParams("NEE", 75.00, 0.24, 0.06, 8000, 0.44, "utilities"),
    
    # Conglomerate
    "BRK.B": AssetParams("BRK.B", 415.00, 0.20, 0.08, 4000, 0.40, "conglomerate"),
    
    # Technology Hardware
    "IBM": AssetParams("IBM", 185.00, 0.25, 0.05, 4000, 0.45, "tech_hardware"),
}


# =============================================================================
# CORRELATION MATRIX BUILDING
# =============================================================================

def _build_stocks_correlation_matrix() -> tuple[np.ndarray, list[str]]:
    """
    Build the correlation matrix for US stocks.
    
    Correlations are based on:
    - Sector groupings (tech, financials, healthcare, etc.)
    - Market cap tiers
    - Business model similarities
    - Supply chain relationships
    
    Returns:
        Tuple of (correlation_matrix, symbol_order)
    """
    symbols = list(STOCKS_ASSETS_DATA.keys())
    n = len(symbols)
    symbol_to_idx = {s: i for i, s in enumerate(symbols)}
    
    # Start with moderate market correlation
    corr = np.full((n, n), 0.40)
    np.fill_diagonal(corr, 1.0)
    
    def set_corr(s1: str, s2: str, value: float) -> None:
        if s1 in symbol_to_idx and s2 in symbol_to_idx:
            i, j = symbol_to_idx[s1], symbol_to_idx[s2]
            corr[i, j] = value
            corr[j, i] = value
    
    # ===================
    # TECH MEGA CAPS
    # ===================
    
    # FAANG+ correlations
    set_corr("AAPL", "MSFT", 0.78)
    set_corr("AAPL", "GOOGL", 0.72)
    set_corr("AAPL", "GOOG", 0.72)
    set_corr("AAPL", "AMZN", 0.68)
    set_corr("AAPL", "META", 0.65)
    set_corr("AAPL", "NVDA", 0.70)
    
    set_corr("MSFT", "GOOGL", 0.75)
    set_corr("MSFT", "GOOG", 0.75)
    set_corr("MSFT", "AMZN", 0.72)
    set_corr("MSFT", "META", 0.68)
    set_corr("MSFT", "NVDA", 0.72)
    
    set_corr("GOOGL", "GOOG", 0.99)  # Same company
    set_corr("GOOGL", "AMZN", 0.70)
    set_corr("GOOGL", "META", 0.75)  # Ad competitors
    set_corr("GOOG", "META", 0.75)
    
    set_corr("AMZN", "META", 0.62)
    set_corr("AMZN", "NFLX", 0.58)
    
    # TSLA correlations
    set_corr("TSLA", "NVDA", 0.65)  # AI/Tech
    set_corr("TSLA", "AAPL", 0.55)
    set_corr("TSLA", "AMD", 0.58)
    
    # ===================
    # SEMICONDUCTORS
    # ===================
    
    # NVDA ecosystem
    set_corr("NVDA", "AMD", 0.82)
    set_corr("NVDA", "AVGO", 0.75)
    set_corr("NVDA", "QCOM", 0.72)
    set_corr("NVDA", "INTC", 0.65)
    set_corr("NVDA", "TXN", 0.68)
    set_corr("NVDA", "LRCX", 0.75)
    set_corr("NVDA", "MU", 0.78)
    set_corr("NVDA", "ADI", 0.70)
    
    # AMD correlations
    set_corr("AMD", "INTC", 0.75)
    set_corr("AMD", "AVGO", 0.72)
    set_corr("AMD", "QCOM", 0.70)
    set_corr("AMD", "MU", 0.78)
    set_corr("AMD", "LRCX", 0.72)
    
    # Memory/Equipment
    set_corr("MU", "LRCX", 0.75)
    set_corr("MU", "TXN", 0.68)
    set_corr("LRCX", "AVGO", 0.70)
    
    # Analog/Mixed signal
    set_corr("TXN", "ADI", 0.82)
    set_corr("TXN", "AVGO", 0.72)
    set_corr("ADI", "AVGO", 0.70)
    
    set_corr("INTC", "AVGO", 0.65)
    set_corr("INTC", "QCOM", 0.68)
    set_corr("QCOM", "AVGO", 0.72)
    
    # ===================
    # SOFTWARE/CLOUD
    # ===================
    
    set_corr("CRM", "NOW", 0.80)
    set_corr("CRM", "ADBE", 0.75)
    set_corr("CRM", "ORCL", 0.70)
    set_corr("NOW", "ADBE", 0.72)
    set_corr("ADBE", "ORCL", 0.65)
    
    set_corr("PANW", "CRM", 0.68)
    set_corr("PANW", "NOW", 0.70)
    set_corr("SNOW", "CRM", 0.72)
    set_corr("SNOW", "NOW", 0.70)
    set_corr("SNOW", "PANW", 0.68)
    
    # Cloud/Software with mega caps
    set_corr("MSFT", "CRM", 0.72)
    set_corr("MSFT", "NOW", 0.70)
    set_corr("MSFT", "ADBE", 0.68)
    set_corr("AMZN", "CRM", 0.65)
    set_corr("GOOGL", "CRM", 0.62)
    
    # ===================
    # FINANCIALS - BANKS
    # ===================
    
    set_corr("JPM", "GS", 0.85)
    set_corr("JPM", "MS", 0.82)
    set_corr("GS", "MS", 0.88)
    
    # Banks with asset managers
    set_corr("JPM", "BLK", 0.72)
    set_corr("JPM", "SCHW", 0.70)
    set_corr("GS", "BLK", 0.75)
    set_corr("MS", "BLK", 0.78)
    
    # ===================
    # FINANCIALS - PAYMENTS
    # ===================
    
    set_corr("V", "MA", 0.92)
    set_corr("V", "AXP", 0.78)
    set_corr("MA", "AXP", 0.75)
    
    # Payments with banks
    set_corr("V", "JPM", 0.65)
    set_corr("MA", "JPM", 0.62)
    
    # ===================
    # HEALTHCARE - PHARMA
    # ===================
    
    set_corr("JNJ", "MRK", 0.75)
    set_corr("JNJ", "ABBV", 0.72)
    set_corr("JNJ", "BMY", 0.70)
    set_corr("JNJ", "AMGN", 0.68)
    
    set_corr("LLY", "MRK", 0.72)
    set_corr("LLY", "ABBV", 0.70)
    set_corr("LLY", "AMGN", 0.68)
    
    set_corr("MRK", "ABBV", 0.78)
    set_corr("MRK", "BMY", 0.75)
    set_corr("MRK", "AMGN", 0.72)
    
    set_corr("ABBV", "BMY", 0.75)
    set_corr("ABBV", "AMGN", 0.72)
    set_corr("ABBV", "GILD", 0.70)
    
    set_corr("BMY", "GILD", 0.72)
    set_corr("AMGN", "GILD", 0.75)
    
    # ===================
    # HEALTHCARE - INSURANCE
    # ===================
    
    set_corr("UNH", "ELV", 0.85)
    
    # Insurance with pharma (negative healthcare cost relationship)
    set_corr("UNH", "LLY", 0.55)
    set_corr("UNH", "JNJ", 0.58)
    
    # ===================
    # HEALTHCARE - DEVICES
    # ===================
    
    set_corr("TMO", "DHR", 0.82)
    set_corr("TMO", "ABT", 0.75)
    set_corr("DHR", "ABT", 0.78)
    set_corr("ABT", "MDT", 0.72)
    set_corr("ISRG", "MDT", 0.70)
    set_corr("ISRG", "ABT", 0.68)
    
    # Devices with pharma
    set_corr("JNJ", "ABT", 0.70)
    set_corr("JNJ", "MDT", 0.65)
    
    # ===================
    # CONSUMER - RETAIL
    # ===================
    
    set_corr("WMT", "COST", 0.75)
    set_corr("WMT", "HD", 0.65)
    set_corr("COST", "HD", 0.62)
    set_corr("HD", "LOW", 0.88)
    
    # ===================
    # CONSUMER - STAPLES
    # ===================
    
    set_corr("PG", "KO", 0.78)
    set_corr("PG", "PEP", 0.80)
    set_corr("KO", "PEP", 0.85)
    set_corr("PG", "PM", 0.65)
    set_corr("KO", "PM", 0.62)
    
    # Staples with retail
    set_corr("PG", "WMT", 0.65)
    set_corr("PG", "COST", 0.62)
    set_corr("KO", "WMT", 0.60)
    
    # ===================
    # CONSUMER - DISCRETIONARY
    # ===================
    
    set_corr("MCD", "NKE", 0.62)
    set_corr("MCD", "DIS", 0.55)
    set_corr("NKE", "DIS", 0.58)
    
    # ===================
    # INDUSTRIALS
    # ===================
    
    set_corr("CAT", "DE", 0.85)
    set_corr("CAT", "HON", 0.72)
    set_corr("DE", "HON", 0.70)
    set_corr("HON", "RTX", 0.72)
    set_corr("CAT", "UPS", 0.62)
    set_corr("UPS", "HON", 0.65)
    set_corr("LIN", "HON", 0.68)
    
    # Industrial services
    set_corr("ACN", "IBM", 0.70)
    set_corr("ACN", "MSFT", 0.65)
    
    # ===================
    # TELECOM
    # ===================
    
    set_corr("VZ", "CMCSA", 0.75)
    
    # ===================
    # ENERGY
    # ===================
    
    set_corr("XOM", "CVX", 0.92)
    
    # Energy negative with tech/growth
    set_corr("XOM", "TSLA", 0.25)
    set_corr("CVX", "TSLA", 0.28)
    
    # ===================
    # CONGLOMERATE
    # ===================
    
    # BRK.B broad market correlation
    set_corr("BRK.B", "JPM", 0.72)
    set_corr("BRK.B", "AAPL", 0.68)  # Large AAPL holding
    set_corr("BRK.B", "KO", 0.65)  # Large KO holding
    set_corr("BRK.B", "AXP", 0.70)
    
    # ===================
    # CROSS-SECTOR (lower correlations)
    # ===================
    
    # Tech vs Healthcare (moderate)
    set_corr("AAPL", "JNJ", 0.45)
    set_corr("MSFT", "UNH", 0.48)
    
    # Tech vs Consumer Staples (lower)
    set_corr("AAPL", "PG", 0.42)
    set_corr("GOOGL", "KO", 0.38)
    
    # Financials vs Healthcare (moderate)
    set_corr("JPM", "JNJ", 0.50)
    set_corr("JPM", "UNH", 0.55)
    
    # Utilities/REITs vs others (lower - defensive)
    set_corr("NEE", "AAPL", 0.35)
    set_corr("NEE", "JPM", 0.40)
    set_corr("PLD", "AMZN", 0.45)  # Warehousing connection
    
    # Ensure matrix is positive semi-definite
    corr = ensure_positive_semidefinite(corr)
    
    return corr, symbols


# =============================================================================
# PUBLIC API
# =============================================================================

def get_stocks_config() -> MarketConfig:
    """
    Get the complete US stocks market configuration.
    
    Returns:
        MarketConfig with 73 stocks and correlation matrix.
    """
    correlation_matrix, symbol_order = _build_stocks_correlation_matrix()
    
    return MarketConfig(
        market_type=MarketType.STOCKS,
        assets=STOCKS_ASSETS_DATA,
        correlation_matrix=correlation_matrix,
        asset_order=symbol_order,
    )

