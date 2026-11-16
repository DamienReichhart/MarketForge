# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the GNU Affero General Public License v3.0 or later.
# See the LICENSE file in the project root for full license information.

"""Correlation matrix of the stocks catalog, built from typical market relationships."""

from __future__ import annotations

import numpy as np

from marketforge.config.catalog.correlation import ensure_positive_semidefinite
from marketforge.config.catalog.stocks.instruments import INSTRUMENTS


def build_correlation_matrix() -> tuple[np.ndarray, list[str]]:
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
    symbols = list(INSTRUMENTS)
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
