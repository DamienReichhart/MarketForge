# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the MIT License. See the LICENSE file in the project
# root for full license information.

"""Stocks catalog: 74 US stocks: start prices, volatilities, drifts and volumes."""

from __future__ import annotations

from marketforge.config.catalog.schema import AssetParams

# All 74 stocks with realistic parameters
# Prices as of late 2024, volatility based on historical behavior
# Volume in thousands of shares

# volume_base is the mean number of shares traded per minute of the session.
INSTRUMENTS = {
    # Technology - Mega Cap
    "AAPL": AssetParams("AAPL", 185.00, 0.25, 0.08, 50000, 0.45),
    "MSFT": AssetParams("MSFT", 415.00, 0.24, 0.10, 25000, 0.45),
    "GOOGL": AssetParams("GOOGL", 165.00, 0.28, 0.08, 25000, 0.48),
    "GOOG": AssetParams("GOOG", 167.00, 0.28, 0.08, 15000, 0.48),
    "AMZN": AssetParams("AMZN", 195.00, 0.30, 0.10, 40000, 0.50),
    "NVDA": AssetParams("NVDA", 875.00, 0.50, 0.15, 45000, 0.55),
    "META": AssetParams("META", 520.00, 0.38, 0.12, 20000, 0.52),
    "TSLA": AssetParams("TSLA", 245.00, 0.55, 0.08, 80000, 0.60),
    # Technology - Software/Cloud
    "ADBE": AssetParams("ADBE", 575.00, 0.32, 0.08, 3000, 0.50),
    "CRM": AssetParams("CRM", 285.00, 0.32, 0.10, 6000, 0.50),
    "ORCL": AssetParams("ORCL", 145.00, 0.28, 0.08, 8000, 0.48),
    "NOW": AssetParams("NOW", 825.00, 0.35, 0.12, 2000, 0.52),
    "PANW": AssetParams("PANW", 315.00, 0.38, 0.12, 3500, 0.52),
    "SNOW": AssetParams("SNOW", 175.00, 0.50, 0.10, 4000, 0.58),
    # Technology - Semiconductors
    "AMD": AssetParams("AMD", 165.00, 0.45, 0.12, 35000, 0.55),
    "QCOM": AssetParams("QCOM", 175.00, 0.35, 0.08, 8000, 0.50),
    "INTC": AssetParams("INTC", 42.00, 0.38, 0.02, 30000, 0.52),
    "AVGO": AssetParams("AVGO", 1450.00, 0.32, 0.10, 3000, 0.48),
    "TXN": AssetParams("TXN", 185.00, 0.28, 0.08, 5000, 0.48),
    "LRCX": AssetParams("LRCX", 960.00, 0.38, 0.10, 2000, 0.52),
    "MU": AssetParams("MU", 115.00, 0.45, 0.08, 15000, 0.55),
    "ADI": AssetParams("ADI", 225.00, 0.30, 0.08, 3500, 0.48),
    # Technology - Internet/Services
    "NFLX": AssetParams("NFLX", 685.00, 0.40, 0.10, 5000, 0.52),
    "UBER": AssetParams("UBER", 72.00, 0.42, 0.10, 20000, 0.55),
    "BKNG": AssetParams("BKNG", 4150.00, 0.32, 0.08, 500, 0.50),
    # Financials - Banks
    "JPM": AssetParams("JPM", 195.00, 0.25, 0.08, 10000, 0.45),
    "GS": AssetParams("GS", 485.00, 0.30, 0.08, 2500, 0.48),
    "MS": AssetParams("MS", 98.00, 0.32, 0.08, 8000, 0.50),
    # Financials - Asset Management/Insurance
    "BLK": AssetParams("BLK", 825.00, 0.28, 0.08, 1000, 0.48),
    "SCHW": AssetParams("SCHW", 72.00, 0.35, 0.06, 8000, 0.52),
    "AXP": AssetParams("AXP", 235.00, 0.28, 0.08, 3000, 0.48),
    "V": AssetParams("V", 285.00, 0.22, 0.10, 7000, 0.42),
    "MA": AssetParams("MA", 475.00, 0.24, 0.10, 3500, 0.44),
    "SPGI": AssetParams("SPGI", 485.00, 0.25, 0.10, 1500, 0.45),
    # Healthcare - Pharma
    "JNJ": AssetParams("JNJ", 158.00, 0.18, 0.05, 7000, 0.38),
    "LLY": AssetParams("LLY", 785.00, 0.32, 0.15, 4000, 0.50),
    "MRK": AssetParams("MRK", 125.00, 0.22, 0.06, 10000, 0.42),
    "ABBV": AssetParams("ABBV", 175.00, 0.24, 0.06, 6000, 0.44),
    "BMY": AssetParams("BMY", 52.00, 0.28, 0.03, 12000, 0.48),
    "AMGN": AssetParams("AMGN", 315.00, 0.24, 0.05, 3000, 0.44),
    "GILD": AssetParams("GILD", 85.00, 0.28, 0.04, 6000, 0.48),
    # Healthcare - Insurance/Services
    "UNH": AssetParams("UNH", 535.00, 0.22, 0.10, 4000, 0.42),
    "ELV": AssetParams("ELV", 515.00, 0.25, 0.08, 1500, 0.45),
    # Healthcare - Devices/Equipment
    "TMO": AssetParams("TMO", 585.00, 0.26, 0.08, 1500, 0.46),
    "ABT": AssetParams("ABT", 115.00, 0.22, 0.06, 6000, 0.42),
    "DHR": AssetParams("DHR", 275.00, 0.26, 0.08, 3000, 0.46),
    "MDT": AssetParams("MDT", 88.00, 0.25, 0.04, 6000, 0.45),
    "ISRG": AssetParams("ISRG", 425.00, 0.30, 0.10, 2000, 0.48),
    # Consumer - Retail
    "WMT": AssetParams("WMT", 165.00, 0.20, 0.08, 8000, 0.40),
    "COST": AssetParams("COST", 725.00, 0.22, 0.10, 2500, 0.42),
    "HD": AssetParams("HD", 365.00, 0.24, 0.08, 4000, 0.44),
    "LOW": AssetParams("LOW", 235.00, 0.26, 0.07, 4000, 0.46),
    # Consumer - Staples
    "PG": AssetParams("PG", 165.00, 0.18, 0.06, 7000, 0.38),
    "KO": AssetParams("KO", 62.00, 0.16, 0.05, 12000, 0.36),
    "PEP": AssetParams("PEP", 175.00, 0.18, 0.06, 5000, 0.38),
    "PM": AssetParams("PM", 115.00, 0.20, 0.06, 5000, 0.40),
    # Consumer - Discretionary
    "MCD": AssetParams("MCD", 295.00, 0.20, 0.08, 4000, 0.40),
    "NKE": AssetParams("NKE", 105.00, 0.32, 0.06, 8000, 0.50),
    "DIS": AssetParams("DIS", 115.00, 0.35, 0.04, 10000, 0.52),
    # Industrials
    "CAT": AssetParams("CAT", 365.00, 0.28, 0.08, 2500, 0.48),
    "DE": AssetParams("DE", 415.00, 0.28, 0.07, 1500, 0.48),
    "HON": AssetParams("HON", 215.00, 0.24, 0.07, 3000, 0.44),
    "UPS": AssetParams("UPS", 145.00, 0.26, 0.05, 3000, 0.46),
    "RTX": AssetParams("RTX", 115.00, 0.25, 0.07, 5000, 0.45),
    "LIN": AssetParams("LIN", 465.00, 0.22, 0.08, 1500, 0.42),
    "ACN": AssetParams("ACN", 365.00, 0.26, 0.09, 2000, 0.46),
    # Communication Services
    "VZ": AssetParams("VZ", 42.00, 0.22, 0.04, 15000, 0.42),
    "CMCSA": AssetParams("CMCSA", 42.00, 0.28, 0.05, 15000, 0.48),
    # Energy
    "XOM": AssetParams("XOM", 115.00, 0.28, 0.06, 15000, 0.48),
    "CVX": AssetParams("CVX", 155.00, 0.26, 0.06, 8000, 0.46),
    # Real Estate
    "PLD": AssetParams("PLD", 135.00, 0.28, 0.06, 4000, 0.48),
    # Utilities
    "NEE": AssetParams("NEE", 75.00, 0.24, 0.06, 8000, 0.44),
    # Conglomerate
    "BRK.B": AssetParams("BRK.B", 415.00, 0.20, 0.08, 4000, 0.40),
    # Technology Hardware
    "IBM": AssetParams("IBM", 185.00, 0.25, 0.05, 4000, 0.45),
}
