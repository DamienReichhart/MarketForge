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
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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


def discard_manifest(dataset: str | os.PathLike[str]) -> None:
    """Forget what a directory held, before a new dataset is generated into it."""
    for name in (MANIFEST_NAME, _PENDING_MANIFEST_NAME, _JOURNAL_NAME):
        (Path(dataset) / name).unlink(missing_ok=True)


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
    rewritten = list(root.rglob("*" + REWRITE_SUFFIX))
    if pending.exists():  # every file is complete: finish swapping them in
        for path in rewritten:
            if path != pending:
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
