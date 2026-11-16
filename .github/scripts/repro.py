"""Seed-reproducibility gate (ADR 0006, ADR 0007).

Users rely on seeds for reproducible backtests, so any change to the candles
an existing seed produces must ship in a new major version. This script
checks that contract by fingerprinting a fixed set of scenarios with the code
under test and with the latest release, in the same environment (same
dependency versions, same CPU), and comparing them bit for bit.

Subcommands:

    capture OUT.json   Fingerprint the installed `marketforge` (not the
                       checkout: run with `python -I` from outside the repo).
    baseline           Print the version to compare against: $BASELINE_VERSION
                       if set, else the latest stable release on PyPI.
    compare BASE HEAD  Compare two fingerprints. A difference fails unless
                       HEAD's major version is greater than BASE's.

`capture` needs marketforge, numpy and pandas; the rest is stdlib.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import urllib.request
from pathlib import Path
from typing import Any

PACKAGE = "marketforge"

# Each scenario uses only the stable public API (`generate`, `generate_to_disk`)
# so the same file can fingerprint both the release and the code under test.
# Together they cover all three markets (and every instrument once), derived
# forex crosses, both anomaly kinds, regime labels, every timeframe, the US
# and EU DST transitions, a leap day, CSV formatting and the in-memory frames.
DISK_SCENARIOS: dict[str, dict[str, Any]] = {
    "disk-all-markets-us-dst": {
        "start": "2024-03-08",
        "end": "2024-03-12",
        "seed": 11,
        "timeframes": ["m1", "H1", "D1"],
        "anomalies": ["spikes", "flash_crash"],
        "include_regime": True,
    },
}
MEMORY_SCENARIOS: dict[str, dict[str, Any]] = {
    "mem-mixed-eu-dst": {
        "assets": ["EURUSD", "GBPJPY", "EURGBP", "BTCUSD", "ETHUSD", "AAPL", "MSFT"],
        "start": "2024-10-24",
        "end": "2024-11-06",
        "seed": 42,
        "timeframes": ["m1", "m5", "m15", "m30", "H1", "H4", "D1", "W1"],
    },
    "mem-crypto-leap-day": {
        "markets": ["crypto"],
        "start": "2024-02-19",
        "end": "2024-03-04",
        "seed": 0,
        "timeframes": ["m1", "W1"],
        "anomalies": ["flash_crash"],
        "include_regime": True,
    },
}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _frame_digest(frame: Any) -> str:
    """Digest of a DataFrame's index, column names, dtypes and exact values."""
    import numpy as np

    h = hashlib.sha256()
    h.update(repr(list(frame.columns)).encode())
    h.update(np.ascontiguousarray(frame.index.asi8).tobytes())
    for name in frame.columns:
        column = frame[name]
        h.update(f"{name}:{column.dtype}".encode())
        if column.dtype == object or str(column.dtype) in {"category", "string", "str"}:
            h.update("\x1f".join(map(str, column.tolist())).encode())
        else:
            h.update(np.ascontiguousarray(column.to_numpy()).tobytes())
    return h.hexdigest()


def capture(out: Path) -> None:
    import marketforge as mf

    origin = Path(mf.__file__).resolve()
    if "site-packages" not in origin.parts:
        sys.exit(f"::error::imported {origin}, not an installed package; run with `python -I`")

    digests: dict[str, str] = {}
    for name, kwargs in DISK_SCENARIOS.items():
        with tempfile.TemporaryDirectory() as tmp:
            mf.generate_to_disk(tmp, fmt="csv", jobs=1, **kwargs)
            files = sorted(p for p in Path(tmp).rglob("*") if p.is_file())
            if not files:
                sys.exit(f"::error::scenario {name} wrote no files")
            for path in files:
                digests[f"{name}/{path.relative_to(tmp).as_posix()}"] = _sha256(path.read_bytes())
    for name, kwargs in MEMORY_SCENARIOS.items():
        data = mf.generate(**kwargs)
        for symbol in sorted(data):
            for timeframe in sorted(data[symbol]):
                frame = data[symbol][timeframe]
                if len(frame) == 0:
                    sys.exit(f"::error::scenario {name} returned no {symbol} {timeframe} candles")
                digests[f"{name}/{symbol}/{timeframe}"] = _frame_digest(frame)

    out.write_text(
        json.dumps({"version": mf.__version__, "digests": digests}, indent=1, sort_keys=True),
        encoding="utf-8",
    )
    print(f"{mf.__version__}: {len(digests)} fingerprints -> {out}")


def latest_release() -> str:
    if version := os.environ.get("BASELINE_VERSION", "").strip():
        return version
    url = f"https://pypi.org/pypi/{PACKAGE}/json"
    with urllib.request.urlopen(url, timeout=30) as response:
        return str(json.load(response)["info"]["version"])


def _major(version: str) -> int:
    match = re.match(r"\d+", version)
    if not match:
        raise ValueError(f"cannot read the major version of '{version}'")
    return int(match.group())


def compare(base: dict[str, Any], head: dict[str, Any]) -> tuple[bool, list[str]]:
    """Return (identical, report lines)."""
    b, h = base["digests"], head["digests"]
    lines = []
    for key in sorted(b.keys() | h.keys()):
        if key not in h:
            lines.append(f"missing in {head['version']}: {key}")
        elif key not in b:
            lines.append(f"new in {head['version']}: {key}")
        elif b[key] != h[key]:
            lines.append(f"changed: {key}")
    return not lines, lines


def _summary(markdown: str) -> None:
    if path := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(markdown + "\n")


def cmd_compare(base_path: Path, head_path: Path) -> int:
    base = json.loads(base_path.read_text(encoding="utf-8"))
    head = json.loads(head_path.read_text(encoding="utf-8"))
    identical, lines = compare(base, head)
    title = f"{head['version']} vs released {base['version']}"
    if identical:
        print(f"Seeds reproduce exactly: {title} ({len(head['digests'])} fingerprints)")
        _summary(f"### Seed reproducibility: identical\n\n{title}, {len(head['digests'])} outputs.")
        return 0

    shown = lines[:50] + ([f"... and {len(lines) - 50} more"] if len(lines) > 50 else [])
    print("\n".join(shown))
    _summary(
        f"### Seed reproducibility: {len(lines)} outputs differ ({title})\n\n```\n"
        + "\n".join(shown)
        + "\n```"
    )
    if _major(head["version"]) > _major(base["version"]):
        print(
            f"::notice title=Seed output changed::{len(lines)} outputs differ from "
            f"{base['version']}; allowed because {head['version']} is a new major version"
        )
        return 0
    print(
        f"::error title=Seed output changed::{len(lines)} outputs differ from release "
        f"{base['version']}. Existing seeds must keep producing the same candles "
        "(docs/adr/0006). If the change is intended, bump the major version in pyproject.toml"
    )
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("capture").add_argument("out", type=Path)
    sub.add_parser("baseline")
    cmp = sub.add_parser("compare")
    cmp.add_argument("base", type=Path)
    cmp.add_argument("head", type=Path)
    args = parser.parse_args(argv)

    if args.command == "capture":
        capture(args.out)
        return 0
    if args.command == "baseline":
        print(latest_release())
        return 0
    return cmd_compare(args.base, args.head)


if __name__ == "__main__":
    sys.exit(main())
