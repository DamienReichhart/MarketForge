"""Writes the real MarketForge output shown on the landing page.

The landing page draws its chart and validation report from
src/samples/hero-sample.json, so it shows what MarketForge actually produces,
never a mock-up. Regenerate it after a release that changes the model (a seed's candles
only change then) with, from the repository root:

    pip install -e .
    python website/scripts/hero_sample.py
"""

import json
from pathlib import Path

import marketforge as mf

INSTRUMENT = "BTCUSD"
MARKET = "crypto"
START, END = "2024-03-01", "2024-03-11"
SEED = 4  # ten days that go through every regime, a crash included
TIMEFRAME = "H1"

OUT = Path(__file__).resolve().parents[1] / "src" / "samples" / "hero-sample.json"


def main() -> None:
    data = mf.generate(
        INSTRUMENT,
        start=START,
        end=END,
        seed=SEED,
        timeframes=["m1", TIMEFRAME],
        include_regime=True,
        include_spread=True,
    )
    candles = data[INSTRUMENT][TIMEFRAME]
    report = mf.validate(data[INSTRUMENT]["m1"], MARKET)
    sample = {
        "version": mf.__version__,
        "instrument": INSTRUMENT,
        "market": MARKET,
        "timeframe": TIMEFRAME,
        "seed": SEED,
        "start": START,
        "end": END,
        "command": (
            f"marketforge generate -o ./data -i {INSTRUMENT} --from {START} --to {END} "
            f"--seed {SEED} --with-regime --with-spread"
        ),
        "columns": ["time", "open", "high", "low", "close", "volume", "spread", "regime"],
        "candles": [
            [
                int(time.timestamp()),
                round(row.open, 2),
                round(row.high, 2),
                round(row.low, 2),
                round(row.close, 2),
                round(row.volume, 2),
                round(row.spread, 4),
                str(row.regime),
            ]
            for time, row in candles.iterrows()
        ],
        "validation": {
            "passed": report.passed,
            "summary": report.summary(),
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(sample, separators=(",", ":")) + "\n")
    print(f"wrote {len(sample['candles'])} candles to {OUT}")


if __name__ == "__main__":
    main()
