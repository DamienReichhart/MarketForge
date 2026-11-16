"""Tests for the seed-reproducibility gate (.github/scripts/repro.py)."""

from __future__ import annotations

import importlib.util
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


@pytest.mark.parametrize(
    ("head_version", "exit_code"),
    [("3.2.0", 1), ("3.1.1", 1), ("4.0.0", 0), ("4.0.0rc1", 0), ("4.0.0.dev0", 0)],
)
def test_changed_output_needs_a_major_bump(tmp_path, capsys, head_version, exit_code):
    base, head = tmp_path / "base.json", tmp_path / "head.json"
    base.write_text(json.dumps(_fingerprint("3.1.0", a="1")))
    head.write_text(json.dumps(_fingerprint(head_version, a="2")))
    assert repro.cmd_compare(base, head) == exit_code
    out = capsys.readouterr().out
    assert ("::error" in out) == (exit_code == 1)


def test_baseline_can_be_pinned(monkeypatch):
    monkeypatch.setenv("BASELINE_VERSION", "2.0.0")
    assert repro.latest_release() == "2.0.0"


@pytest.mark.parametrize(
    "kwargs",
    [*repro.DISK_SCENARIOS.values(), *repro.MEMORY_SCENARIOS.values()],
)
def test_scenarios_are_valid_requests(kwargs):
    from marketforge.api.planning import plan_request

    assert plan_request(**kwargs).seed == kwargs["seed"]
