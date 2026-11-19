"""Seed-reproducibility gate (ADR 0006, ADR 0007).

Realism comes before seed stability (ADR 0011): a release may change the
candles an existing seed produces, but only on purpose. This script
fingerprints a fixed set of scenarios with the code under test and with the
latest release, in the same environment (same dependency versions, same CPU),
and compares them bit for bit. A difference passes only when the code under
test increments `MODEL_REVISION` and CHANGELOG.md has an "Output changes"
section for its version.

Subcommands:

    capture OUT.json   Fingerprint the installed `marketforge` (not the
                       checkout: run with `python -I` from outside the repo).
    baseline           Print the version to compare against: $BASELINE_VERSION
                       if set, else the latest stable release on PyPI.
    compare BASE HEAD [--changelog CHANGELOG.md]
                       Compare two fingerprints. A difference fails unless
                       HEAD's model revision is greater than BASE's and the
                       changelog announces Output changes for HEAD's version.

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
from inspect import signature
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
        "instruments": ["EURUSD", "GBPJPY", "EURGBP", "BTCUSD", "ETHUSD", "AAPL", "MSFT"],
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
            # Candle files only: the manifest names the version that wrote it.
            files = sorted(p for p in Path(tmp).rglob("*.csv") if p.is_file())
            if not files:
                sys.exit(f"::error::scenario {name} wrote no files")
            for path in files:
                digests[f"{name}/{path.relative_to(tmp).as_posix()}"] = _sha256(path.read_bytes())
    for name, scenario in MEMORY_SCENARIOS.items():
        kwargs = dict(scenario)
        # Releases before 4.0 call the instruments parameter `assets`. Drop this
        # once the baseline release is 4.0 or newer.
        if "instruments" in kwargs and "instruments" not in signature(mf.generate).parameters:
            kwargs["assets"] = kwargs.pop("instruments")
        data = mf.generate(**kwargs)
        for symbol in sorted(data):
            for timeframe in sorted(data[symbol]):
                frame = data[symbol][timeframe]
                if len(frame) == 0:
                    sys.exit(f"::error::scenario {name} returned no {symbol} {timeframe} candles")
                digests[f"{name}/{symbol}/{timeframe}"] = _frame_digest(frame)

    # Releases before 4.0 have no model revision: they count as revision 0.
    revision = getattr(mf, "MODEL_REVISION", 0)
    out.write_text(
        json.dumps(
            {"version": mf.__version__, "model_revision": revision, "digests": digests},
            indent=1,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    print(f"{mf.__version__}: {len(digests)} fingerprints -> {out}")


def latest_release() -> str:
    if version := os.environ.get("BASELINE_VERSION", "").strip():
        return version
    url = f"https://pypi.org/pypi/{PACKAGE}/json"
    with urllib.request.urlopen(url, timeout=30) as response:
        return str(json.load(response)["info"]["version"])


def _release(version: str) -> str:
    """The release part of a version: 4.0.0rc1 and 4.0.0.dev0 are 4.0.0."""
    match = re.match(r"\d+(?:\.\d+)*", version)
    if not match:
        raise ValueError(f"cannot read the release of '{version}'")
    return match.group()


def announces_output_changes(changelog: str, version: str) -> bool:
    """Whether the changelog section of ``version`` has an "Output changes" heading."""
    section = re.search(
        rf"^## {re.escape(_release(version))}\s*$(.*?)(?=^## |\Z)", changelog, re.M | re.S
    )
    return bool(section and re.search(r"^### Output changes\s*$", section.group(1), re.M))


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


def cmd_compare(base_path: Path, head_path: Path, changelog_path: Path) -> int:
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
    base_revision = base.get("model_revision", 0)
    head_revision = head.get("model_revision", 0)
    announced = announces_output_changes(
        changelog_path.read_text(encoding="utf-8"), head["version"]
    )
    if head_revision > base_revision and announced:
        print(
            f"::notice title=Seed output changed::{len(lines)} outputs differ from "
            f"{base['version']}; announced as Output changes in model revision {head_revision}"
        )
        return 0
    missing = []
    if head_revision <= base_revision:
        missing.append(
            f"increment MODEL_REVISION in marketforge/_version.py (it is {head_revision}, "
            f"the release has {base_revision})"
        )
    if not announced:
        missing.append(
            f"add an '### Output changes' section under '## {_release(head['version'])}' "
            "in CHANGELOG.md"
        )
    print(
        f"::error title=Seed output changed::{len(lines)} outputs differ from release "
        f"{base['version']}. If the change is intended (ADR 0011), " + " and ".join(missing)
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
    cmp.add_argument("--changelog", type=Path, default=Path("CHANGELOG.md"))
    args = parser.parse_args(argv)

    if args.command == "capture":
        capture(args.out)
        return 0
    if args.command == "baseline":
        print(latest_release())
        return 0
    return cmd_compare(args.base, args.head, args.changelog)


if __name__ == "__main__":
    sys.exit(main())
