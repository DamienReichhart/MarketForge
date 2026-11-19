# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

"""
How each forex code moves with the global shock (risk on), ADR 0016.

A code's value rises by its loading when the world takes risk: equity
indices most, then commodity and emerging-market currencies; the havens
(JPY, CHF, the dollar, gold) fall. A pair's loading is its base's minus its
quote's, so SPXUSD rises with stocks, USDJPY rises (the yen weakens) and
AUDUSD rises. Only the direction matters: the simulator scales it to what
the catalog's correlations allow. Codes not listed load 0.
"""

from __future__ import annotations

RISK_LOADINGS: dict[str, float] = {
    # Havens
    "USD": -0.15,
    "UDX": -0.15,  # the dollar index
    "JPY": -0.35,
    "CHF": -0.25,
    "XAU": -0.1,
    "HKD": -0.15,  # pegged to the dollar
    # Majors and commodity currencies
    "EUR": 0.0,
    "DKK": 0.0,  # pegged to the euro
    "GBP": 0.1,
    "AUD": 0.45,
    "NZD": 0.4,
    "CAD": 0.25,
    "NOK": 0.3,
    "SEK": 0.25,
    # Emerging markets
    "MXN": 0.4,
    "ZAR": 0.45,
    "TRY": 0.2,
    "HUF": 0.25,
    "PLN": 0.25,
    "CZK": 0.15,
    "SGD": 0.1,
    "CNH": 0.05,
    "INR": 0.1,
    "IDR": 0.2,
    "THB": 0.1,
    "PHP": 0.1,
    "TWD": 0.2,
    "ILS": 0.15,
    # Metals and oil
    "XAG": 0.15,
    "XPT": 0.25,
    "XPD": 0.25,
    "BCO": 0.45,
    "WTI": 0.45,
    # Equity indices: the stock market itself, which the direction is mostly
    "SPX": 2.0,
    "NSX": 2.0,
    "GRX": 1.6,
    "FRX": 1.6,
    "ETX": 1.6,
    "UKX": 1.4,
    "HKX": 1.2,
    "JPX": 1.2,
    "AUX": 1.3,
}

# The equity index codes: their CFDs also follow the stock market's own
# regime trends (bull and bear spells), each by its risk loading relative to
# the S&P 500's, the stock market the catalog simulates.
STOCK_INDICES = frozenset({"SPX", "NSX", "GRX", "FRX", "ETX", "UKX", "HKX", "JPX", "AUX"})
