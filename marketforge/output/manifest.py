# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

"""
The manifest of a dataset, and the journal that keeps an extension all-or-nothing.

``marketforge.json`` records how a dataset was produced and the checkpoint an
extension resumes from. An extension appends to CSV files in place and
rewrites Parquet files beside the originals, so it first writes a journal
(``marketforge.extending``) with the size of every CSV file. If it is
interrupted, :func:`recover` puts the dataset back: before the new manifest
is ready, CSV files are cut back to their recorded size and the rewritten
Parquet files discarded; once it is ready, the remaining files are swapped in.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from marketforge.domain.markets import MarketType
from marketforge.domain.timeframes import Timeframe

MANIFEST_NAME = "marketforge.json"
_JOURNAL_NAME = "marketforge.extending"
_PENDING_MANIFEST_NAME = MANIFEST_NAME + ".tmp"
# A Parquet file cannot be appended to: an extension writes the whole new
# file beside the original, under this suffix, and swaps it in at the end.
REWRITE_SUFFIX = ".tmp"


@dataclass
class Manifest:
    """How a dataset was produced, and where its simulation can be resumed."""

    version: str  # the MarketForge version that wrote the dataset
    model_revision: int  # the model generation that produced its candles (ADR 0011)
    seed: int
    start: int  # Unix seconds, inclusive
    end: int  # Unix seconds, exclusive
    format: str
    timestamps: str
    timeframes: list[str]
    anomalies: list[str]
    include_regime: bool
    include_spread: bool
    include_bid_ask: bool
    instruments: dict[str, list[str]]  # market -> symbols, in file order
    overrides: dict[str, dict[str, Any]]
    checkpoint: dict[str, dict[str, Any]]  # market -> where to resume

    def to_json(self) -> str:
        doc = {
            "marketforge": self.version,
            "model_revision": self.model_revision,
            "seed": self.seed,
            "start": iso_time(self.start),
            "end": iso_time(self.end),
            "format": self.format,
            "timestamps": self.timestamps,
            "timeframes": self.timeframes,
            "anomalies": self.anomalies,
            "include_regime": self.include_regime,
            "include_spread": self.include_spread,
            "include_bid_ask": self.include_bid_ask,
            "instruments": self.instruments,
            "overrides": self.overrides,
            "checkpoint": self.checkpoint,
        }
        return json.dumps(doc, indent=1) + "\n"

    @classmethod
    def from_json(cls, text: str) -> Manifest:
        doc = json.loads(text)
        return cls(
            version=doc["marketforge"],
            model_revision=doc["model_revision"],
            seed=doc["seed"],
            start=_unix(doc["start"]),
            end=_unix(doc["end"]),
            format=doc["format"],
            timestamps=doc["timestamps"],
            timeframes=doc["timeframes"],
            anomalies=doc["anomalies"],
            include_regime=doc["include_regime"],
            include_spread=doc["include_spread"],
            include_bid_ask=doc.get("include_bid_ask", False),
            instruments=doc["instruments"],
            overrides=doc["overrides"],
            checkpoint=doc["checkpoint"],
        )


def iso_time(seconds: int) -> str:
    """Unix seconds as an ISO 8601 UTC time."""
    return dt.datetime.fromtimestamp(seconds, dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _unix(iso: str) -> int:
    return int(dt.datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp())


def read_manifest(dataset: str | os.PathLike[str]) -> Manifest:
    """The manifest of a dataset directory."""
    path = Path(dataset) / MANIFEST_NAME
    try:
        return Manifest.from_json(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValueError(
            f"{Path(dataset)} is not a MarketForge dataset: it has no {MANIFEST_NAME} "
            "(datasets written before 4.0 have none and cannot be extended)"
        ) from None
    except (KeyError, TypeError, ValueError) as e:
        raise ValueError(f"{path} is not a valid manifest: {e!r}") from None


def write_manifest(dataset: str | os.PathLike[str], manifest: Manifest) -> Path:
    """Write the manifest of a freshly generated dataset."""
    path = Path(dataset) / MANIFEST_NAME
    _write_atomically(path, manifest.to_json())
    return path


_MARKET_DIRS = tuple(market.value for market in MarketType)
_CANDLE_FILE = re.compile(
    r"^[^/\\]+_(?:"
    + "|".join(tf.name for tf in Timeframe)
    + r")\.(?:csv|parquet|feather)(?:\.tmp)?$"
)


def dataset_files(dataset: str | os.PathLike[str]) -> list[Path]:
    """The files of a MarketForge dataset in a directory: manifest and candle files.

    Candle files count without a manifest too: an interrupted generation leaves
    them behind. Files MarketForge does not write are never listed.
    """
    root = Path(dataset)
    found = [
        root / name
        for name in (MANIFEST_NAME, _PENDING_MANIFEST_NAME, _JOURNAL_NAME)
        if (root / name).is_file()
    ]
    for market in _MARKET_DIRS:
        folder = root / market
        if folder.is_dir():
            found.extend(
                sorted(p for p in folder.iterdir() if p.is_file() and _CANDLE_FILE.match(p.name))
            )
    return found


def clear_dataset(dataset: str | os.PathLike[str], *, overwrite: bool) -> None:
    """Make room for a new dataset: refuse to mix it with an old one unless ``overwrite``."""
    files = dataset_files(dataset)
    if not files:
        return
    if not overwrite:
        raise FileExistsError(
            f"{Path(dataset)} already holds a MarketForge dataset ({len(files)} files). "
            "Pass overwrite=True (--overwrite on the command line) to replace it, "
            "or continue it with `marketforge extend` (mf.extend)"
        )
    for path in files:
        path.unlink(missing_ok=True)


def begin_extension(dataset: str | os.PathLike[str], csv_files: list[Path]) -> None:
    """Record the size of every CSV file that is about to be appended to."""
    root = Path(dataset)
    sizes = {p.relative_to(root).as_posix(): p.stat().st_size for p in csv_files}
    _write_atomically(root / _JOURNAL_NAME, json.dumps(sizes))


def commit_extension(dataset: str | os.PathLike[str], manifest: Manifest) -> Path:
    """Make a finished extension the dataset: swap in rewritten files and the manifest."""
    root = Path(dataset)
    _write_atomically(root / _PENDING_MANIFEST_NAME, manifest.to_json())
    recover(root)
    return root / MANIFEST_NAME


def recover(dataset: str | os.PathLike[str]) -> None:
    """Finish or undo an extension that was interrupted; a no-op otherwise."""
    root = Path(dataset)
    journal = root / _JOURNAL_NAME
    if not journal.exists():
        return
    pending = root / _PENDING_MANIFEST_NAME
    # Only candle files MarketForge rewrote: other *.tmp files are the user's.
    rewritten = [
        path
        for path in dataset_files(root)
        if path.name.endswith(REWRITE_SUFFIX) and path != pending
    ]
    if pending.exists():  # every file is complete: finish swapping them in
        for path in rewritten:
            os.replace(path, path.with_name(path.name.removesuffix(REWRITE_SUFFIX)))
        os.replace(pending, root / MANIFEST_NAME)
    else:  # interrupted while generating: back to the dataset as it was
        for name, size in json.loads(journal.read_text(encoding="utf-8")).items():
            os.truncate(root / name, size)
        for path in rewritten:
            path.unlink()
    journal.unlink()


def _write_atomically(path: Path, text: str) -> None:
    scratch = path.with_name(path.name + ".part")
    scratch.write_text(text, encoding="utf-8")
    os.replace(scratch, path)
