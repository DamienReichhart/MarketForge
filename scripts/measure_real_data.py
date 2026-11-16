# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the MIT License. See the LICENSE file in the project
# root for full license information.

"""
Measure stylized facts on real m1 data, as reference for the validation bands.

The statistics are exactly those of marketforge.validation (open-to-close m1
log returns), computed on non-overlapping windows of the same length the
benchmark uses (14 days by default), plus longer-horizon diagnostics used for
calibration: |r| autocorrelation at 15 min-1 day, and volume behaviour.

Only derived statistics are kept in the repository
(marketforge/validation/reference.py); raw market data is not redistributed.

Inputs (one instrument per invocation, files concatenated in time order):
- Binance kline archives from https://data.binance.vision (.zip or .csv,
  no header, millisecond timestamps), e.g. spot/daily/klines/BTCUSDT/1m/
- any CSV/Parquet with columns timestamp (Unix s), open, high, low, close, volume

Usage:
    python scripts/measure_real_data.py --name BTCUSDT data/BTCUSDT-1m-2024-02-*.zip
"""

from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from marketforge.validation import stylized_facts as sf

_BINANCE_COLS = [
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "quote_volume",
    "trades",
    "taker_base",
    "taker_quote",
    "ignore",
]


def load(path: Path) -> pd.DataFrame:
    """Load one file into timestamp/open/high/low/close/volume[/trades]."""
    if path.suffix == ".parquet":
        df = pd.read_parquet(path)
    elif path.suffix == ".zip":
        with zipfile.ZipFile(path) as z:
            with z.open(z.namelist()[0]) as fh:
                df = pd.read_csv(fh, header=None, names=_BINANCE_COLS)
    else:
        head = path.read_text(encoding="ascii", errors="ignore").split("\n", 1)[0]
        df = (
            pd.read_csv(path)
            if head.startswith("timestamp")
            else pd.read_csv(path, header=None, names=_BINANCE_COLS)
        )
    if "open_time" in df.columns:
        ts = df["open_time"].astype("int64")
        df["timestamp"] = np.where(ts > 1e14, ts // 1_000_000, ts // 1000)  # us or ms
    keep = [
        c
        for c in ("timestamp", "open", "high", "low", "close", "volume", "trades")
        if c in df.columns
    ]
    return df[keep]


def window_stats(df: pd.DataFrame) -> dict[str, float]:
    o, h, l, c = (df[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    r = np.log(c / o)
    a = np.abs(r)
    out = {
        "excess_kurtosis": sf.excess_kurtosis(r),
        "vol_clustering": sf.volatility_clustering_strength(r),
        "leverage": sf.leverage_correlation(r),
        "range_efficiency": sf.range_efficiency(o, h, l, c),
        "zero_return_share": float(np.mean(r == 0)),
    }
    for lag in (15, 60, 240, 1440):
        if a.size > lag * 4:
            out[f"abs_acf_{lag}"] = sf._acf(a, lag)
    v = df["volume"].to_numpy(float)
    pos = v > 0
    if pos.mean() > 0.95:
        lv = np.log(v[pos])
        out.update(
            {
                "log_volume_std": float(lv.std()),
                "log_volume_acf1": sf._acf(lv, 1),
                "corr_abs_return_log_volume": float(np.corrcoef(a[pos], lv)[0, 1]),
                "max_minute_volume_share": float(v.max() / v.sum()),
            }
        )
    if "trades" in df.columns:
        out["median_trades_per_minute"] = float(np.median(df["trades"]))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--name", required=True)
    ap.add_argument("--window-days", type=int, default=14)
    args = ap.parse_args()

    df = pd.concat([load(p) for p in sorted(args.files)], ignore_index=True)
    df = df.sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)
    df = df[(df[["open", "high", "low", "close"]] > 0).all(axis=1)]
    span = args.window_days * 86400
    start = int(df["timestamp"].iloc[0])
    windows = [
        g
        for _, g in df.groupby((df["timestamp"] - start) // span)
        if len(g) > 0.5 * args.window_days * 390
    ]
    stats = [window_stats(w) for w in windows]
    keys = sorted({k for s in stats for k in s})
    summary = {
        "name": args.name,
        "first": pd.to_datetime(start, unit="s", utc=True).isoformat(),
        "minutes": int(len(df)),
        "windows": len(stats),
        "window_days": args.window_days,
        "metrics": {
            k: {
                "median": float(np.median([s[k] for s in stats if k in s])),
                "min": float(np.min([s[k] for s in stats if k in s])),
                "max": float(np.max([s[k] for s in stats if k in s])),
            }
            for k in keys
        },
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
