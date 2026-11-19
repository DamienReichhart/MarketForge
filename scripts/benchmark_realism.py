# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

"""
Validate every instrument of every market against the stylized-fact bands.

Usage: python scripts/benchmark_realism.py [--seeds 123,7] [--days 14]
"""

from __future__ import annotations

import argparse

import marketforge as mf
from marketforge.domain.markets import MarketType


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seeds", default="123,7")
    ap.add_argument("--days", type=int, default=14)
    args = ap.parse_args()
    start = 1704067200
    end = start + args.days * 86400
    total = failed = 0
    for seed in (int(s) for s in args.seeds.split(",")):
        for market in MarketType:
            data = mf.generate(markets=[market], start=start, end=end, seed=seed, with_spread=True)
            for symbol, frames in data.items():
                report = mf.validate(frames["m1"], market)
                total += 1
                if not report.passed:
                    failed += 1
                    print(f"seed {seed} {symbol}\n{report.summary()}\n")
    print(f"{total - failed}/{total} instrument checks passed")


if __name__ == "__main__":
    main()
