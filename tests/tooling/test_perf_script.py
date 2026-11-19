"""Tests for the performance gate (.github/scripts/perf.py)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".github" / "scripts" / "perf.py"
if not SCRIPT.is_file():  # running from the sdist, which ships tests/ but not .github/
    pytest.skip("release tooling is not part of the sdist", allow_module_level=True)

_spec = importlib.util.spec_from_file_location("perf", SCRIPT)
assert _spec is not None and _spec.loader is not None
perf = importlib.util.module_from_spec(_spec)
sys.modules["perf"] = perf
_spec.loader.exec_module(perf)

CRYPTO = next(iter(perf.WORKLOADS))


def _results(head, base, head_version="4.0.0", base_version="3.1.1"):
    return {
        "head": {"version": head_version, "timings": head, "skipped": []},
        "base": {"version": base_version, "timings": base, "skipped": []},
    }


def test_compares_the_fastest_run_of_each_side():
    # A noisy slow run on one side must not count against it.
    rows, one_sided = perf.compare(
        _results({CRYPTO: [1.0, 0.50, 3.0]}, {CRYPTO: [0.48, 0.9]}), max_slowdown=0.15
    )
    assert one_sided == []
    [row] = rows
    assert row["head"] == 0.50 and row["base"] == 0.48
    assert row["ratio"] == pytest.approx(0.50 / 0.48)
    assert not row["slower"]


def test_a_slowdown_above_the_threshold_is_flagged():
    [row], _ = perf.compare(_results({CRYPTO: [1.2]}, {CRYPTO: [1.0]}), max_slowdown=0.15)
    assert row["slower"]
    [row], _ = perf.compare(_results({CRYPTO: [1.149]}, {CRYPTO: [1.0]}), max_slowdown=0.15)
    assert not row["slower"]


def test_workloads_only_one_version_can_run_are_reported_not_compared():
    rows, one_sided = perf.compare(
        _results({CRYPTO: [1.0], "spread": [1.0]}, {CRYPTO: [1.0]}), max_slowdown=0.15
    )
    assert [row["workload"] for row in rows] == [CRYPTO]
    assert one_sided == ["spread"]


@pytest.mark.parametrize(
    ("messages", "expected"),
    [
        ([], None),
        (["fix: something\n\nNo trailer here."], None),
        (["perf!: exact sums\n\nAccept-Slowdown: 30%"], 0.30),
        (["a\n\naccept-slowdown: 12.5 %", "b\n\nAccept-Slowdown: 40%"], 0.40),
        (["Accept-Slowdown: lots"], None),
    ],
)
def test_accept_slowdown_trailers(messages, expected):
    assert perf.accepted_slowdown(messages) == (
        pytest.approx(expected) if expected is not None else None
    )


def _write(tmp_path, results):
    path = tmp_path / "results.json"
    path.write_text(json.dumps(results), encoding="utf-8")
    return path


def _git(monkeypatch, messages, tag="v3.1.1"):
    monkeypatch.setattr(perf, "_release_tag", lambda version: tag)
    monkeypatch.setattr(perf, "_messages_since", lambda tag: messages)


def test_compare_fails_on_a_regression(tmp_path, monkeypatch, capsys):
    _git(monkeypatch, ["feat: x"])
    path = _write(tmp_path, _results({CRYPTO: [1.5]}, {CRYPTO: [1.0]}))
    assert perf.cmd_compare(path, max_slowdown=0.15) == 1
    assert "::error title=Performance regression::" in capsys.readouterr().out


def test_compare_passes_within_the_threshold_and_writes_a_summary(tmp_path, monkeypatch):
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    _git(monkeypatch, [])
    path = _write(tmp_path, _results({CRYPTO: [1.05]}, {CRYPTO: [1.0]}))
    assert perf.cmd_compare(path, max_slowdown=0.15) == 0
    text = summary.read_text(encoding="utf-8")
    assert "| Workload | 3.1.1 | 4.0.0 | Change |" in text and "+5.0%" in text


def test_an_accept_slowdown_trailer_raises_the_threshold(tmp_path, monkeypatch, capsys):
    _git(monkeypatch, ["perf!: slower but exact\n\nAccept-Slowdown: 60%"])
    path = _write(tmp_path, _results({CRYPTO: [1.5]}, {CRYPTO: [1.0]}))
    assert perf.cmd_compare(path, max_slowdown=0.15) == 0
    assert "Accept-Slowdown: 60%" in capsys.readouterr().out


def test_compare_fails_when_nothing_could_be_compared(tmp_path, monkeypatch):
    _git(monkeypatch, [])
    path = _write(tmp_path, _results({"new": [1.0]}, {"old": [1.0]}))
    assert perf.cmd_compare(path, max_slowdown=0.15) == 1


def test_a_workload_is_skipped_when_the_version_lacks_one_of_its_parameters(tmp_path):
    def generate(instruments=None, *, start, end, seed=None):
        return (instruments, start, end, seed)

    module = SimpleNamespace(generate=generate)
    spec = {"call": "generate", "instruments": ["BTCUSD"], "kwargs": {"start": "a", "end": "b"}}
    run = perf._call(module, "w", spec, tmp_path)
    assert run is not None and run() == (["BTCUSD"], "a", "b", None)

    with_spread = {**spec, "kwargs": {**spec["kwargs"], "with_spread": True}}
    assert perf._call(module, "w", with_spread, tmp_path) is None
    assert perf._call(SimpleNamespace(), "w", spec, tmp_path) is None


def test_a_workload_uses_the_names_a_release_before_5_takes(tmp_path):
    def generate(instruments=None, *, start, end, include_spread=False):
        return (instruments, start, end, include_spread)

    spec = {
        "call": "generate",
        "instruments": ["BTCUSD"],
        "kwargs": {"start": "a", "end": "b", "with_spread": True},
    }
    run = perf._call(SimpleNamespace(generate=generate), "w", spec, tmp_path)
    assert run is not None and run() == (["BTCUSD"], "a", "b", True)


def test_every_workload_runs_on_the_current_api(tmp_path):
    # The workloads must stay valid for the code under test, or the gate
    # would quietly compare nothing.
    import marketforge as mf

    for name, spec in perf.WORKLOADS.items():
        assert perf._call(mf, name, spec, tmp_path) is not None, name
