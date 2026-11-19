# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

"""Export a dataset for LEAN and run an algorithm on it in LEAN's own engine.

    python lean_roundtrip.py prepare WORKDIR   # dataset, export, algorithm
    (run the quantconnect/lean image on WORKDIR, see engines.yml)
    python lean_roundtrip.py check WORKDIR     # the algorithm saw every market

The algorithm subscribes to a stock, a currency pair and a coin at minute
resolution, buys each once, and logs how many bars of each it received.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import marketforge as mf

ALGORITHM = """
from AlgorithmImports import *


class Main(QCAlgorithm):
    def initialize(self):
        self.set_start_date(2024, 3, 5)
        self.set_end_date(2024, 3, 8)
        self.set_cash(100000)
        self.symbols = {
            "AAPL": self.add_equity("AAPL", Resolution.MINUTE).symbol,
            "EURUSD": self.add_forex("EURUSD", Resolution.MINUTE, Market.OANDA).symbol,
            "BTCUSD": self.add_crypto("BTCUSD", Resolution.MINUTE, Market.COINBASE).symbol,
        }
        self.counts = {name: 0 for name in self.symbols}

    def on_data(self, data):
        for name, symbol in self.symbols.items():
            if data.contains_key(symbol) and data[symbol] is not None:
                self.counts[name] += 1
                if not self.portfolio[symbol].invested:
                    self.set_holdings(symbol, 0.1)

    def on_end_of_algorithm(self):
        self.log("MF-ROUNDTRIP " + " ".join(f"{k}={v}" for k, v in self.counts.items()))
"""


def prepare(work: Path) -> None:
    mf.generate_to_disk(
        work / "dataset", "AAPL,EURUSD,BTCUSD", start="2024-03-04", days=6, seed=7,
        timeframes="m1", with_bid_ask=True,
    )  # fmt: skip
    report = mf.export("lean", work / "dataset", work / "data")
    print(f"exported {len(report.files)} files")
    (work / "algorithm").mkdir(parents=True, exist_ok=True)
    (work / "algorithm" / "main.py").write_text(ALGORITHM, encoding="utf-8")
    (work / "results").mkdir(exist_ok=True)


def check(work: Path) -> None:
    logs = "\n".join(p.read_text(errors="replace") for p in (work / "results").rglob("*log*.txt"))
    found = re.search(r"MF-ROUNDTRIP (.*)", logs)
    if found is None:
        sys.exit("LEAN did not finish the algorithm: no MF-ROUNDTRIP line in its log")
    counts = dict(pair.split("=") for pair in found.group(1).split())
    print("bars LEAN read per instrument:", counts)
    empty = [name for name, n in counts.items() if int(n) == 0]
    if empty:
        sys.exit(f"LEAN read no bars of {', '.join(empty)} from the export")


if __name__ == "__main__":
    {"prepare": prepare, "check": check}[sys.argv[1]](Path(sys.argv[2]))
