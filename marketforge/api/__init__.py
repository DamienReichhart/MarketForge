# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the GNU Affero General Public License v3.0 or later.
# See the LICENSE file in the project root for full license information.

"""
Public Python API.

    >>> import marketforge as mf
    >>> data = mf.generate(["EURUSD", "AAPL"], start="2024-01-01", end="2024-02-01",
    ...                    seed=42, timeframes=["m1", "H1", "D1"])
    >>> data["EURUSD"]["H1"].head()

:func:`generate` returns candles in memory as pandas DataFrames;
:func:`generate_to_disk` streams them to CSV or Parquet files. Both simulate
whole markets (see docs/adr/0001): asking for one instrument costs as much as
asking for its whole market, and returns exactly the same candles.
"""
