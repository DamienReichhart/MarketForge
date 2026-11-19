# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

"""What a dataset holds (:func:`info`) and whether it is what its manifest says (:func:`verify`)."""

from __future__ import annotations

import datetime as dt
import os
import tempfile
import warnings
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.feather as feather
import pyarrow.parquet as pq

from marketforge._version import MODEL_REVISION, __version__
from marketforge.api.disk import default_jobs, write_request
from marketforge.api.planning import plan_request
from marketforge.output.manifest import (
    MANIFEST_NAME,
    Manifest,
    dataset_files,
    file_record,
    read_manifest,
)


@dataclass(frozen=True)
class DatasetInfo:
    """A dataset's summary, from its manifest and its files (:func:`info`)."""

    path: str
    version: str  # the MarketForge version that wrote it
    model_revision: int
    seed: int
    start: str  # ISO 8601 UTC
    end: str
    format: str
    layout: str
    timestamps: str
    timeframes: list[str]
    instruments: dict[str, list[str]]  # market -> symbols
    columns: dict[str, bool]  # spread, bid_ask, regime -> present
    anomalies: list[str]
    overrides: list[str]  # the symbols an override file changed or added
    files: int
    bytes: int
    extendable: bool
    not_extendable_because: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """As JSON-ready values (``marketforge info --json``)."""
        doc = asdict(self)
        doc["marketforge"] = doc.pop("version")
        return doc


def info(dataset: str | os.PathLike[str]) -> DatasetInfo:
    """
    Summarise a dataset: how it was made, what it holds, and whether it can be extended.

    Raises:
        ValueError: if the directory is not a dataset.
    """
    root = Path(dataset)
    manifest = read_manifest(root)
    files = [p for p in dataset_files(root) if p.name != MANIFEST_NAME]
    reason = _why_not_current(manifest)
    return DatasetInfo(
        path=str(root.resolve()),
        version=manifest.version,
        model_revision=manifest.model_revision,
        seed=manifest.seed,
        start=_iso(manifest.start),
        end=_iso(manifest.end),
        format=manifest.format,
        layout=manifest.layout,
        timestamps=manifest.timestamps,
        timeframes=list(manifest.timeframes),
        instruments=manifest.instruments,
        columns={
            "spread": manifest.include_spread,
            "bid_ask": manifest.include_bid_ask,
            "regime": manifest.include_regime,
        },
        anomalies=list(manifest.anomalies),
        overrides=sorted(manifest.overrides),
        files=len(files),
        bytes=sum(p.stat().st_size for p in files),
        extendable=reason is None,
        not_extendable_because=reason,
    )


@dataclass(frozen=True)
class VerifyReport:
    """The result of :func:`verify`: every file compared with a fresh generation.

    CSV files must be identical byte for byte; Parquet and Feather files must
    hold identical values (an extended file keeps its earlier row groups, so
    its bytes differ from a file written in one go).
    """

    identical: list[str] = field(default_factory=list)  # paths relative to the dataset
    differs: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    extra: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not (self.differs or self.missing or self.extra)

    @property
    def expected(self) -> int:
        """Files a fresh generation writes."""
        return len(self.identical) + len(self.differs) + len(self.missing)


def verify(
    dataset: str | os.PathLike[str], *, checksums: bool = False, jobs: int | None = None
) -> VerifyReport:
    """
    Regenerate a dataset from its manifest and compare every file with it.

    The fresh copy is written in a temporary directory beside the dataset (on
    the same disk), so it needs as much free space as the dataset.

    With ``checksums``, nothing is regenerated: every file is compared with
    the SHA-256 its manifest recorded when it was written. That is fast and
    proves the files unaltered since, but not that this MarketForge would
    produce them; it works on datasets of any model revision.

    Raises:
        ValueError: if the directory is not a dataset, was written by another
            model revision (unless ``checksums``), or has no checksums
            (written before 5.0) when ``checksums`` is asked for.
    """
    root = Path(dataset)
    manifest = read_manifest(root)
    if checksums:
        return _check_sums(root, manifest)
    reason = _why_not_current(manifest)
    if reason is not None:
        raise ValueError(f"{root} cannot be verified by MarketForge {__version__}: {reason}")
    request = plan_request(
        [s for symbols in manifest.instruments.values() for s in symbols],
        start=manifest.start,
        end=manifest.end,
        seed=manifest.seed,
        timeframes=manifest.timeframes,
        anomalies=manifest.anomalies,
        include_regime=manifest.include_regime,
        include_spread=manifest.include_spread,
        include_bid_ask=manifest.include_bid_ask,
        overrides=manifest.overrides or None,
        allow_closed=True,
    )
    ours = {_rel(p, root) for p in dataset_files(root) if p.name != MANIFEST_NAME}
    report = VerifyReport()
    with tempfile.TemporaryDirectory(
        prefix=".marketforge-verify-", dir=root.resolve().parent
    ) as tmp:
        fresh = Path(tmp)
        with warnings.catch_warnings():  # the dataset's generation already said it all
            warnings.simplefilter("ignore")
            write_request(
                request,
                fresh,
                fmt=manifest.format,
                timestamps=manifest.timestamps,
                layout=manifest.layout,
                jobs=default_jobs(request, jobs),
            )
        for path in sorted(p for p in dataset_files(fresh) if p.name != MANIFEST_NAME):
            rel = _rel(path, fresh)
            if rel not in ours:
                report.missing.append(rel)
            elif _same(root / rel, path, manifest.format):
                report.identical.append(rel)
            else:
                report.differs.append(rel)
        expected = {_rel(p, fresh) for p in dataset_files(fresh) if p.name != MANIFEST_NAME}
    report.extra.extend(sorted(ours - expected))
    return report


def _check_sums(root: Path, manifest: Manifest) -> VerifyReport:
    if not manifest.files:
        raise ValueError(
            f"{root}'s manifest records no checksums (it was written before MarketForge 5.0): "
            "verify it by regenerating it instead"
        )
    ours = {_rel(p, root) for p in dataset_files(root) if p.name != MANIFEST_NAME}
    report = VerifyReport()
    for rel, recorded in sorted(manifest.files.items()):
        if rel not in ours:
            report.missing.append(rel)
        elif file_record(root / rel)["sha256"] == recorded["sha256"]:
            report.identical.append(rel)
        else:
            report.differs.append(rel)
    report.extra.extend(sorted(ours - manifest.files.keys()))
    return report


def _same(ours: Path, fresh: Path, fmt: str) -> bool:
    if fmt == "csv":
        return ours.read_bytes() == fresh.read_bytes()
    try:
        return bool(_values(ours, fmt).equals(_values(fresh, fmt)))
    except (OSError, pa.ArrowException):
        return False  # not a readable file of that format


def _values(path: Path, fmt: str) -> pa.Table:
    table = pq.read_table(path) if fmt == "parquet" else feather.read_table(path)
    return table.replace_schema_metadata(None).combine_chunks()


def _why_not_current(manifest: Manifest) -> str | None:
    if manifest.model_revision == MODEL_REVISION:
        return None
    return (
        f"written by model revision {manifest.model_revision}; MarketForge {__version__} "
        f"has {MODEL_REVISION} (install marketforge=={manifest.version})"
    )


def _rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _iso(seconds: int) -> str:
    return dt.datetime.fromtimestamp(seconds, dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
