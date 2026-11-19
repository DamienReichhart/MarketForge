"""Tests for the seed-reproducibility gate (.github/scripts/repro.py)."""

from __future__ import annotations

import importlib.util
import inspect
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".github" / "scripts" / "repro.py"
if not SCRIPT.is_file():  # running from the sdist, which ships tests/ but not .github/
    pytest.skip("release tooling is not part of the sdist", allow_module_level=True)

_spec = importlib.util.spec_from_file_location("repro", SCRIPT)
assert _spec is not None and _spec.loader is not None
repro = importlib.util.module_from_spec(_spec)
sys.modules["repro"] = repro
_spec.loader.exec_module(repro)


def _fingerprint(version, **digests):
    return {"version": version, "digests": digests}


def test_identical_fingerprints_pass():
    same = _fingerprint("3.1.0", a="1", b="2")
    assert repro.compare(same, same) == (True, [])


def test_every_kind_of_difference_is_reported():
    base = _fingerprint("3.1.0", kept="1", changed="2", dropped="3")
    head = _fingerprint("3.2.0", kept="1", changed="X", added="4")
    identical, lines = repro.compare(base, head)
    assert not identical
    assert lines == ["new in 3.2.0: added", "changed: changed", "missing in 3.2.0: dropped"]


CHANGELOG_WITH_OUTPUT_CHANGES = """# Changelog

## 3.2.0

### Output changes
- Regimes now trend.

## 3.1.0

- Earlier.
"""
CHANGELOG_WITHOUT = """# Changelog

## 3.2.0

### Fixes
- A typo.

## 3.1.0

### Output changes
- An older change does not count for 3.2.0.
"""


@pytest.mark.parametrize(
    ("head_revision", "changelog", "exit_code"),
    [
        (2, CHANGELOG_WITH_OUTPUT_CHANGES, 0),
        (1, CHANGELOG_WITH_OUTPUT_CHANGES, 1),  # the revision was not incremented
        (2, CHANGELOG_WITHOUT, 1),  # the change is not announced for this version
        (1, CHANGELOG_WITHOUT, 1),
    ],
)
def test_changed_output_needs_a_new_model_revision_and_an_output_changes_entry(
    tmp_path, capsys, head_revision, changelog, exit_code
):
    base, head, log = tmp_path / "base.json", tmp_path / "head.json", tmp_path / "CHANGELOG.md"
    base.write_text(json.dumps({**_fingerprint("3.1.0", a="1"), "model_revision": 1}))
    head.write_text(json.dumps({**_fingerprint("3.2.0", a="2"), "model_revision": head_revision}))
    log.write_text(changelog)
    assert repro.cmd_compare(base, head, log) == exit_code
    out = capsys.readouterr().out
    assert ("::error" in out) == (exit_code == 1)


def test_a_release_without_a_model_revision_counts_as_revision_0(tmp_path):
    base, head, log = tmp_path / "base.json", tmp_path / "head.json", tmp_path / "CHANGELOG.md"
    base.write_text(json.dumps(_fingerprint("3.1.0", a="1")))  # 3.x has no MODEL_REVISION
    head.write_text(json.dumps({**_fingerprint("3.2.0", a="2"), "model_revision": 1}))
    log.write_text(CHANGELOG_WITH_OUTPUT_CHANGES)
    assert repro.cmd_compare(base, head, log) == 0


def test_identical_output_passes_whatever_the_revision_and_changelog(tmp_path):
    base, head, log = tmp_path / "base.json", tmp_path / "head.json", tmp_path / "CHANGELOG.md"
    base.write_text(json.dumps({**_fingerprint("3.1.0", a="1"), "model_revision": 1}))
    head.write_text(json.dumps({**_fingerprint("3.2.0", a="1"), "model_revision": 2}))
    log.write_text(CHANGELOG_WITHOUT)
    assert repro.cmd_compare(base, head, log) == 0


def test_baseline_can_be_pinned(monkeypatch):
    monkeypatch.setenv("BASELINE_VERSION", "2.0.0")
    assert repro.latest_release() == "2.0.0"


@pytest.mark.parametrize(
    "kwargs",
    [*repro.DISK_SCENARIOS.values(), *repro.MEMORY_SCENARIOS.values()],
)
def test_scenarios_are_valid_requests(kwargs):
    import marketforge as mf

    call = mf.generate_to_disk if kwargs in repro.DISK_SCENARIOS.values() else mf.generate
    assert set(repro._for_version(call, kwargs)) <= set(inspect.signature(call).parameters)
