# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

"""Time constants. Timestamps are UTC seconds throughout."""

from __future__ import annotations

MINUTES_PER_DAY = 1440
SECONDS_PER_DAY = 86400

# Calendar year 2023, [start, end) in UTC seconds: the fixed window over which
# volatility is annualised and seasonality is normalised, so neither depends
# on the requested range.
REFERENCE_YEAR = (1672531200, 1704067200)
