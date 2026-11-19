# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

"""
Currencies held near a level by their central bank.

Each entry is the pair whose price is held, ``(centre, half-width, half-life)``:
the centre (None: the catalog's start price), the band as a fraction of it,
inside which a pull towards the centre acts, and the pull's half-life in days.
The price never leaves the band. Free-floating pairs wandered off: USDHKD
reached 8.22 in ten years against the real 7.75-7.85 band.
"""

from __future__ import annotations

PEGS: dict[str, tuple[float | None, float, float]] = {
    # The Hong Kong dollar's convertibility band, 7.75 to 7.85 per dollar.
    "USDHKD": (7.80, 0.0064, 20.0),
    # ERM II: the krone within 2.25% of 7.46038 per euro (in practice far less).
    "EURDKK": (7.46038, 0.0225, 30.0),
    # The yuan is managed, not pegged: a weak pull within a wide band.
    "USDCNH": (None, 0.08, 250.0),
}
