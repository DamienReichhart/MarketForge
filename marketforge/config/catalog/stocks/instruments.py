# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the MIT License. See the LICENSE file in the project
# root for full license information.

"""Stocks catalog: 74 US stocks: start prices, volatilities, drifts and volumes."""

from __future__ import annotations

from marketforge.config.catalog.schema import InstrumentParams

# All 74 stocks with realistic parameters
# Prices as of late 2024, volatility based on historical behavior
# Volume in thousands of shares

# volume_base is the mean number of shares traded per minute of the session.
INSTRUMENTS = {
    # Technology - Mega Cap
    "AAPL": InstrumentParams("AAPL", 185.00, 0.25, 0.08, 50000, 0.45),
    "MSFT": InstrumentParams("MSFT", 415.00, 0.24, 0.10, 25000, 0.45),
    "GOOGL": InstrumentParams("GOOGL", 165.00, 0.28, 0.08, 25000, 0.48),
    "GOOG": InstrumentParams("GOOG", 167.00, 0.28, 0.08, 15000, 0.48),
    "AMZN": InstrumentParams("AMZN", 195.00, 0.30, 0.10, 40000, 0.50),
    "NVDA": InstrumentParams("NVDA", 875.00, 0.50, 0.15, 45000, 0.55),
    "META": InstrumentParams("META", 520.00, 0.38, 0.12, 20000, 0.52),
    "TSLA": InstrumentParams("TSLA", 245.00, 0.55, 0.08, 80000, 0.60),
    # Technology - Software/Cloud
    "ADBE": InstrumentParams("ADBE", 575.00, 0.32, 0.08, 3000, 0.50),
    "CRM": InstrumentParams("CRM", 285.00, 0.32, 0.10, 6000, 0.50),
    "ORCL": InstrumentParams("ORCL", 145.00, 0.28, 0.08, 8000, 0.48),
    "NOW": InstrumentParams("NOW", 825.00, 0.35, 0.12, 2000, 0.52),
    "PANW": InstrumentParams("PANW", 315.00, 0.38, 0.12, 3500, 0.52),
    "SNOW": InstrumentParams("SNOW", 175.00, 0.50, 0.10, 4000, 0.58),
    # Technology - Semiconductors
    "AMD": InstrumentParams("AMD", 165.00, 0.45, 0.12, 35000, 0.55),
    "QCOM": InstrumentParams("QCOM", 175.00, 0.35, 0.08, 8000, 0.50),
    "INTC": InstrumentParams("INTC", 42.00, 0.38, 0.02, 30000, 0.52),
    "AVGO": InstrumentParams("AVGO", 1450.00, 0.32, 0.10, 3000, 0.48),
    "TXN": InstrumentParams("TXN", 185.00, 0.28, 0.08, 5000, 0.48),
    "LRCX": InstrumentParams("LRCX", 960.00, 0.38, 0.10, 2000, 0.52),
    "MU": InstrumentParams("MU", 115.00, 0.45, 0.08, 15000, 0.55),
    "ADI": InstrumentParams("ADI", 225.00, 0.30, 0.08, 3500, 0.48),
    # Technology - Internet/Services
    "NFLX": InstrumentParams("NFLX", 685.00, 0.40, 0.10, 5000, 0.52),
    "UBER": InstrumentParams("UBER", 72.00, 0.42, 0.10, 20000, 0.55),
    "BKNG": InstrumentParams("BKNG", 4150.00, 0.32, 0.08, 500, 0.50),
    # Financials - Banks
    "JPM": InstrumentParams("JPM", 195.00, 0.25, 0.08, 10000, 0.45),
    "GS": InstrumentParams("GS", 485.00, 0.30, 0.08, 2500, 0.48),
    "MS": InstrumentParams("MS", 98.00, 0.32, 0.08, 8000, 0.50),
    # Financials - Asset Management/Insurance
    "BLK": InstrumentParams("BLK", 825.00, 0.28, 0.08, 1000, 0.48),
    "SCHW": InstrumentParams("SCHW", 72.00, 0.35, 0.06, 8000, 0.52),
    "AXP": InstrumentParams("AXP", 235.00, 0.28, 0.08, 3000, 0.48),
    "V": InstrumentParams("V", 285.00, 0.22, 0.10, 7000, 0.42),
    "MA": InstrumentParams("MA", 475.00, 0.24, 0.10, 3500, 0.44),
    "SPGI": InstrumentParams("SPGI", 485.00, 0.25, 0.10, 1500, 0.45),
    # Healthcare - Pharma
    "JNJ": InstrumentParams("JNJ", 158.00, 0.18, 0.05, 7000, 0.38),
    "LLY": InstrumentParams("LLY", 785.00, 0.32, 0.15, 4000, 0.50),
    "MRK": InstrumentParams("MRK", 125.00, 0.22, 0.06, 10000, 0.42),
    "ABBV": InstrumentParams("ABBV", 175.00, 0.24, 0.06, 6000, 0.44),
    "BMY": InstrumentParams("BMY", 52.00, 0.28, 0.03, 12000, 0.48),
    "AMGN": InstrumentParams("AMGN", 315.00, 0.24, 0.05, 3000, 0.44),
    "GILD": InstrumentParams("GILD", 85.00, 0.28, 0.04, 6000, 0.48),
    # Healthcare - Insurance/Services
    "UNH": InstrumentParams("UNH", 535.00, 0.22, 0.10, 4000, 0.42),
    "ELV": InstrumentParams("ELV", 515.00, 0.25, 0.08, 1500, 0.45),
    # Healthcare - Devices/Equipment
    "TMO": InstrumentParams("TMO", 585.00, 0.26, 0.08, 1500, 0.46),
    "ABT": InstrumentParams("ABT", 115.00, 0.22, 0.06, 6000, 0.42),
    "DHR": InstrumentParams("DHR", 275.00, 0.26, 0.08, 3000, 0.46),
    "MDT": InstrumentParams("MDT", 88.00, 0.25, 0.04, 6000, 0.45),
    "ISRG": InstrumentParams("ISRG", 425.00, 0.30, 0.10, 2000, 0.48),
    # Consumer - Retail
    "WMT": InstrumentParams("WMT", 165.00, 0.20, 0.08, 8000, 0.40),
    "COST": InstrumentParams("COST", 725.00, 0.22, 0.10, 2500, 0.42),
    "HD": InstrumentParams("HD", 365.00, 0.24, 0.08, 4000, 0.44),
    "LOW": InstrumentParams("LOW", 235.00, 0.26, 0.07, 4000, 0.46),
    # Consumer - Staples
    "PG": InstrumentParams("PG", 165.00, 0.18, 0.06, 7000, 0.38),
    "KO": InstrumentParams("KO", 62.00, 0.16, 0.05, 12000, 0.36),
    "PEP": InstrumentParams("PEP", 175.00, 0.18, 0.06, 5000, 0.38),
    "PM": InstrumentParams("PM", 115.00, 0.20, 0.06, 5000, 0.40),
    # Consumer - Discretionary
    "MCD": InstrumentParams("MCD", 295.00, 0.20, 0.08, 4000, 0.40),
    "NKE": InstrumentParams("NKE", 105.00, 0.32, 0.06, 8000, 0.50),
    "DIS": InstrumentParams("DIS", 115.00, 0.35, 0.04, 10000, 0.52),
    # Industrials
    "CAT": InstrumentParams("CAT", 365.00, 0.28, 0.08, 2500, 0.48),
    "DE": InstrumentParams("DE", 415.00, 0.28, 0.07, 1500, 0.48),
    "HON": InstrumentParams("HON", 215.00, 0.24, 0.07, 3000, 0.44),
    "UPS": InstrumentParams("UPS", 145.00, 0.26, 0.05, 3000, 0.46),
    "RTX": InstrumentParams("RTX", 115.00, 0.25, 0.07, 5000, 0.45),
    "LIN": InstrumentParams("LIN", 465.00, 0.22, 0.08, 1500, 0.42),
    "ACN": InstrumentParams("ACN", 365.00, 0.26, 0.09, 2000, 0.46),
    # Communication Services
    "VZ": InstrumentParams("VZ", 42.00, 0.22, 0.04, 15000, 0.42),
    "CMCSA": InstrumentParams("CMCSA", 42.00, 0.28, 0.05, 15000, 0.48),
    # Energy
    "XOM": InstrumentParams("XOM", 115.00, 0.28, 0.06, 15000, 0.48),
    "CVX": InstrumentParams("CVX", 155.00, 0.26, 0.06, 8000, 0.46),
    # Real Estate
    "PLD": InstrumentParams("PLD", 135.00, 0.28, 0.06, 4000, 0.48),
    # Utilities
    "NEE": InstrumentParams("NEE", 75.00, 0.24, 0.06, 8000, 0.44),
    # Conglomerate
    "BRK.B": InstrumentParams("BRK.B", 415.00, 0.20, 0.08, 4000, 0.40),
    # Technology Hardware
    "IBM": InstrumentParams("IBM", 185.00, 0.25, 0.05, 4000, 0.45),
}
