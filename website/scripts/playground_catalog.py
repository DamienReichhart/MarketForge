"""Writes the instrument catalog the playground's form is built from.

The form has to show markets, instruments and timeframes before the visitor
has downloaded the Python runtime, so they come from
src/samples/playground-catalog.json, written by this script from the package
itself. tests/tooling/test_playground_catalog.py fails when it is stale;
regenerate it from the repository root with:

    pip install -e .
    python website/scripts/playground_catalog.py
"""

import json
from pathlib import Path

import marketforge as mf
from marketforge.domain.anomalies import AnomalyType
from marketforge.domain.markets import MarketType
from marketforge.domain.timeframes import Timeframe

OUT = Path(__file__).resolve().parents[1] / "src" / "samples" / "playground-catalog.json"


def catalog() -> dict[str, object]:
    """Markets with their instruments, timeframes and anomalies, in catalog order."""
    table = mf.instruments()
    return {
        "markets": {
            market.value: table.index[table["market"] == market.value].tolist()
            for market in MarketType
        },
        "timeframes": [timeframe.name for timeframe in Timeframe],
        "anomalies": [anomaly.value for anomaly in AnomalyType],
    }


def main() -> None:
    OUT.write_text(json.dumps(catalog(), indent=1) + "\n")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
