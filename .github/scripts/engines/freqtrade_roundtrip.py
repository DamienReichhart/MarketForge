# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

"""Export a dataset for freqtrade and backtest a moving-average crossover on it.

Run from an empty directory with marketforge and freqtrade installed. freqtrade
loads the exchange's market list (Kraken: it lists BTC/USD and ETH/USD), so
this needs the network. Fails unless the backtest trades.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import marketforge as mf

STRATEGY = """
from freqtrade.strategy import IStrategy


class Crossover(IStrategy):
    timeframe = "1h"
    minimal_roi = {"0": 10}
    stoploss = -0.99

    def populate_indicators(self, df, metadata):
        df["fast"] = df["close"].rolling(6).mean()
        df["slow"] = df["close"].rolling(24).mean()
        return df

    def populate_entry_trend(self, df, metadata):
        df.loc[df["fast"] > df["slow"], "enter_long"] = 1
        return df

    def populate_exit_trend(self, df, metadata):
        df.loc[df["fast"] < df["slow"], "exit_long"] = 1
        return df
"""


def main() -> None:
    data = Path("user_data/data/kraken")
    mf.generate_to_disk(
        "dataset", "BTCUSD,ETHUSD", start="2024-03-01", days=30, seed=7, timeframes="m5,H1,D1"
    )
    report = mf.export("freqtrade", "dataset", data)
    print(f"exported {len(report.files)} files:", sorted(p.name for p in report.files))
    Path("user_data/strategies").mkdir(parents=True, exist_ok=True)
    Path("user_data/strategies/crossover.py").write_text(STRATEGY, encoding="utf-8")
    config = {
        "stake_currency": "USD",
        "stake_amount": 100,
        "dry_run": True,
        "dry_run_wallet": 1000,
        "max_open_trades": 2,
        "timeframe": "1h",
        "trading_mode": "spot",
        "entry_pricing": {"price_side": "same"},
        "exit_pricing": {"price_side": "same"},
        "exchange": {"name": "kraken", "pair_whitelist": ["BTC/USD", "ETH/USD"]},
        "pairlists": [{"method": "StaticPairList"}],
        "datadir": str(data),
        "user_data_dir": "user_data",
    }
    Path("config.json").write_text(json.dumps(config), encoding="utf-8")
    run = subprocess.run(
        ["freqtrade", "backtesting", "-c", "config.json", "--strategy", "Crossover",
         "--timerange", "20240302-20240330"],
        capture_output=True, text=True, check=False,
    )  # fmt: skip
    print(run.stdout[-4000:], run.stderr[-4000:], sep="\n")
    trades = re.search(r"Total/Daily Avg Trades\D*(\d+)", run.stdout)
    if run.returncode != 0 or trades is None or int(trades.group(1)) == 0:
        sys.exit("freqtrade did not backtest the exported data (see its output above)")
    print(f"freqtrade backtested {trades.group(1)} trades on the exported candles")


if __name__ == "__main__":
    main()
