"""Writes the real MarketForge output the landing page is built from.

Every chart, table and terminal line on the landing page comes from
src/samples/landing-samples.json (and hero-sample.json, written by
hero_sample.py), so the page shows what MarketForge produces, never a mock-up.
Regenerate it after a release that changes the model, or the command-line
output, with, from the repository root:

    pip install -e .
    python website/scripts/landing_samples.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

import marketforge as mf

OUT = Path(__file__).resolve().parents[1] / "src" / "samples" / "landing-samples.json"

REGIMES = ("trend_up", "trend_down", "range", "high_volatility", "crash")

# One chart per market, each over a stretch that shows its calendar: crypto
# never closes, forex closes for the weekend, stocks trade the NYSE session.
MARKETS = [
    {
        "instrument": "BTCUSD",
        "market": "crypto",
        "timeframe": "H1",
        "start": "2024-03-01",
        "end": "2024-03-11",
        "seed": 4,
    },
    {
        "instrument": "EURUSD",
        "market": "forex",
        "timeframe": "H1",
        "start": "2024-03-06",
        "end": "2024-03-16",
        "seed": 4,
    },
    {
        "instrument": "AAPL",
        "market": "stocks",
        "timeframe": "m15",
        "start": "2024-03-11",
        "end": "2024-03-16",
        "seed": 4,
    },
]

# A long stretch to cut one clean run of each regime from.
REGIME_SOURCE = {
    "instrument": "BTCUSD",
    "timeframe": "H1",
    "start": "2024-01-01",
    "end": "2024-07-01",
    "seed": 4,
}
REGIME_WINDOW = 48

# The same instrument and range under many seeds: one backtest path versus many.
PATHS = {
    "instrument": "BTCUSD",
    "timeframe": "D1",
    "start": "2024-01-01",
    "end": "2024-07-01",
    "seeds": 32,
}

COMMAND = [sys.executable, "-m", "marketforge"]


def candles(frame) -> list[list]:
    """The rows the chart reads: time, OHLC, volume, spread, regime."""
    has_spread = "spread" in frame.columns
    has_regime = "regime" in frame.columns
    rows = []
    for t, r in zip(frame.index, frame.itertuples(index=False), strict=True):
        rows.append(
            [
                int(t.timestamp()),
                round(float(r.open), 6),
                round(float(r.high), 6),
                round(float(r.low), 6),
                round(float(r.close), 6),
                round(float(r.volume), 2),
                round(float(r.spread), 6) if has_spread else None,
                str(r.regime) if has_regime else None,
            ]
        )
    return rows


def market_charts() -> list[dict]:
    charts = []
    for spec in MARKETS:
        data = mf.generate(
            spec["instrument"],
            start=spec["start"],
            end=spec["end"],
            seed=spec["seed"],
            timeframes=[spec["timeframe"]],
            include_regime=True,
            include_spread=True,
        )
        rows = candles(data[spec["instrument"]][spec["timeframe"]])
        command = (
            f"marketforge generate -o ./data -i {spec['instrument']} --from {spec['start']} --to {spec['end']} "
            f"--seed {spec['seed']} --with-regime --with-spread"
        )
        charts.append({**spec, "command": command, "candles": rows})
    return charts


def regime_runs() -> dict[str, list]:
    """For each regime, the candles of its longest run (at most REGIME_WINDOW)."""
    spec = REGIME_SOURCE
    data = mf.generate(
        spec["instrument"],
        start=spec["start"],
        end=spec["end"],
        seed=spec["seed"],
        timeframes=[spec["timeframe"]],
        include_regime=True,
    )
    rows = candles(data[spec["instrument"]][spec["timeframe"]])
    best: dict[str, tuple[int, int]] = {}
    start = 0
    for i in range(1, len(rows) + 1):
        if i == len(rows) or rows[i][7] != rows[start][7]:
            regime = rows[start][7]
            length = i - start
            if regime not in best or length > best[regime][1] - best[regime][0]:
                best[regime] = (start, i)
            start = i
    missing = [r for r in REGIMES if r not in best]
    if missing:
        raise SystemExit(f"no run of {missing} in the regime source; pick another seed or range")
    runs = {}
    for regime in REGIMES:
        a, b = best[regime]
        middle = (a + b) // 2
        lo = max(a, middle - REGIME_WINDOW // 2)
        hi = min(b, lo + REGIME_WINDOW)
        runs[regime] = rows[lo:hi]
    return {"source": spec, "runs": runs}


def seed_paths() -> dict:
    """Closes of one instrument under every seed, each rebased to 100."""
    spec = PATHS
    paths = []
    for data in mf.generate_many(
        spec["instrument"],
        seeds=range(spec["seeds"]),
        start=spec["start"],
        end=spec["end"],
        timeframes=[spec["timeframe"]],
    ):
        close = data[spec["instrument"]][spec["timeframe"]]["close"].to_numpy()
        paths.append([round(float(v), 3) for v in 100 * close / close[0]])
    drawdowns = []
    for p in paths:
        a = np.asarray(p)
        drawdowns.append(round(float(100 * (1 - (a / np.maximum.accumulate(a))).max()), 1))
    return {**spec, "paths": paths, "max_drawdown_pct": drawdowns}


# One week, Monday to Sunday in UTC, to show which hours each market trades.
WEEK = {"start": "2024-03-11", "end": "2024-03-18", "seed": 4}
WEEK_INSTRUMENTS = {"crypto": "BTCUSD", "forex": "EURUSD", "stocks": "AAPL"}


def week_hours() -> dict:
    """For each market, the hours of one week (0 = Monday 00:00 UTC) that have a candle."""
    start = pd.Timestamp(WEEK["start"], tz="UTC")
    hours = {}
    for market, instrument in WEEK_INSTRUMENTS.items():
        data = mf.generate(
            instrument, start=WEEK["start"], end=WEEK["end"], seed=WEEK["seed"], timeframes=["m1"]
        )
        index = data[instrument]["m1"].index
        hours[market] = sorted({int((t - start) / pd.Timedelta(hours=1)) for t in index})
    return {**WEEK, "instruments": WEEK_INSTRUMENTS, "open_hours": hours}


def run(args: list[str], cwd: Path) -> str:
    done = subprocess.run([*COMMAND, *args], cwd=cwd, capture_output=True, text=True, check=True)
    return done.stdout.strip()


def terminal() -> dict[str, dict[str, str]]:
    """Real command-line output, as a reader would see it."""
    with tempfile.TemporaryDirectory() as tmp:
        cwd = Path(tmp)
        dry = [
            "generate",
            "--from",
            "2024-01-01",
            "--to",
            "2025-01-01",
            "--market",
            "all",
            "--seed",
            "42",
            "--dry-run",
        ]
        gen = [
            "generate",
            "-o",
            "./data",
            "--from",
            "2024-03-01",
            "--days",
            "30",
            "-i",
            "BTCUSD,EURUSD,AAPL",
            "--seed",
            "42",
            "--with-regime",
            "-q",
        ]
        run(gen, cwd)
        ext = ["extend", "./data", "--days", "30", "-q"]
        run(ext, cwd)
        info = run(["info", "./data"], cwd).replace(str(cwd.resolve()), ".").replace(str(cwd), ".")
        ver = ["verify", "./data"]
        return {
            "dry_run": {"command": "marketforge " + " ".join(dry), "output": run(dry, cwd)},
            "generate": {"command": "marketforge " + " ".join(a for a in gen if a != "-q")},
            "extend": {"command": "marketforge " + " ".join(a for a in ext if a != "-q")},
            "info": {"command": "marketforge info ./data", "output": info},
            "verify": {"command": "marketforge " + " ".join(ver), "output": run(ver, cwd)},
        }


def main() -> None:
    sample = {
        "version": mf.__version__,
        "columns": ["time", "open", "high", "low", "close", "volume", "spread", "regime"],
        "markets": market_charts(),
        "regimes": regime_runs(),
        "paths": seed_paths(),
        "week": week_hours(),
        "terminal": terminal(),
    }
    OUT.write_text(json.dumps(sample, separators=(",", ":")) + "\n")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
