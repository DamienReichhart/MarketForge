"""Performance gate: the code under test must not be slower than the latest release.

Speed is part of what MarketForge promises (ADR 0003, ADR 0007), so CI times
a fixed set of workloads with the code under test (HEAD) and with the latest
release (BASE) and fails when HEAD is more than --max-slowdown slower on any
of them.

Shared CI runners are noisy, so the comparison is made as fairly as it can be:

* both versions run on the SAME runner, with the SAME dependency versions
  (two virtual environments, one freeze);
* their runs are interleaved (HEAD, BASE, BASE, HEAD, ...), so a slow minute
  on the runner hits both sides alike;
* every workload is warmed up first (Numba compiles or loads its cache) and
  then timed several times; the fastest time is kept, which is the best
  estimate of the true cost of deterministic CPU-bound code.

A slowdown can be intended (a fix that costs time). Then add a trailer to a
commit since the release, and the gate allows up to that much on every
workload until the next release resets the baseline:

    Accept-Slowdown: 30%

Subcommands:

    measure OUT.json      Time the workloads with the installed `marketforge`
                          (run with `python -I` from outside the repository).
    run OUT.json          Interleave `measure` (and a cold-start timing) in
                          the --head and --base interpreters, merge the results.
    compare RESULTS.json  Fail when HEAD is slower than allowed.

`measure` needs marketforge; the rest is stdlib.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Iterable
from inspect import signature
from pathlib import Path
from typing import Any

DEFAULT_MAX_SLOWDOWN = 0.15
TRAILER = "Accept-Slowdown"

# Fixed, single-threaded workloads that cover what users run: the simulator
# for each market (forex crosses included), aggregation to every timeframe,
# and the CSV writer. Each takes a fraction of a second, so many timed
# repetitions fit in a few minutes. Instruments are passed positionally:
# releases before 4.0 call that parameter `assets`.
ALL_TIMEFRAMES = ["m1", "m5", "m15", "m30", "H1", "H4", "D1", "W1"]
WORKLOADS: dict[str, dict[str, Any]] = {
    "crypto: 3 instruments, 6 weeks, every timeframe": {
        "call": "generate",
        "instruments": ["BTCUSD", "ETHUSD", "SOLUSD"],
        "kwargs": {
            "start": "2024-01-01",
            "end": "2024-02-12",
            "seed": 1,
            "timeframes": ALL_TIMEFRAMES,
            "with_regime": True,
        },
    },
    "forex: majors and crosses, 2 months": {
        "call": "generate",
        "instruments": ["EURUSD", "GBPUSD", "USDJPY", "EURGBP", "GBPJPY"],
        "kwargs": {
            "start": "2024-03-04",
            "end": "2024-05-06",
            "seed": 2,
            "timeframes": ["m1", "H1"],
        },
    },
    "stocks: 3 instruments, 6 months": {
        "call": "generate",
        "instruments": ["AAPL", "MSFT", "NVDA"],
        "kwargs": {
            "start": "2024-01-02",
            "end": "2024-07-01",
            "seed": 3,
            "timeframes": ["m1", "D1"],
        },
    },
    "anomalies: crypto, 6 weeks": {
        "call": "generate",
        "instruments": ["BTCUSD"],
        "kwargs": {
            "start": "2024-02-01",
            "end": "2024-03-14",
            "seed": 4,
            "timeframes": ["m1"],
            "anomalies": ["spikes", "flash_crash"],
        },
    },
    "CSV to disk: crypto, 3 weeks, every timeframe": {
        "call": "generate_to_disk",
        "instruments": ["BTCUSD", "ETHUSD"],
        "kwargs": {
            "start": "2024-01-01",
            "end": "2024-01-22",
            "seed": 5,
            "format": "csv",
            "jobs": 1,
        },
    },
}

# Time from a fresh interpreter to the first candles: import, loading the
# cached Numba kernels and one small generation. A lost `cache=True` or a
# heavy new import shows up here, not in the warmed-up workloads.
COLD_START = "cold start: import and first generate"
COLD_START_CODE = (
    "import marketforge as mf; "
    "mf.generate(['EURUSD'], start='2024-01-02', end='2024-01-03', seed=1, timeframes=['m1'])"
)


# 5.0 renamed these keyword arguments; a release before it takes the old names.
# Drop this once the baseline release is 5.0 or newer.
_BEFORE_5 = {
    "format": "fmt",
    "with_regime": "include_regime",
    "with_spread": "include_spread",
    "with_bid_ask": "include_bid_ask",
}


def _for_version(function: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    """``kwargs`` in the spelling ``function`` takes (old names before 5.0)."""
    parameters = signature(function).parameters
    return {
        (_BEFORE_5[k] if k not in parameters and k in _BEFORE_5 else k): v
        for k, v in kwargs.items()
    }


def _call(mf: Any, name: str, spec: dict[str, Any], workdir: Path) -> Callable[[], object] | None:
    """A zero-argument callable running the workload, or None if this version lacks a parameter."""
    function = getattr(mf, spec["call"], None)
    if function is None:
        return None
    parameters = signature(function).parameters
    kwargs = _for_version(function, spec["kwargs"])
    if any(key not in parameters for key in kwargs):
        return None
    if spec["call"] == "generate_to_disk":
        out = workdir / re.sub(r"\W+", "-", name)
        # Each timing writes the dataset again; 4.0 refuses that without overwrite.
        again = {"overwrite": True} if "overwrite" in parameters else {}
        return lambda: function(out, list(spec["instruments"]), **kwargs, **again)
    return lambda: function(list(spec["instruments"]), **kwargs)


def measure(repeat: int) -> dict[str, Any]:
    import marketforge as mf

    origin = Path(mf.__file__).resolve()
    if "site-packages" not in origin.parts:
        sys.exit(f"::error::imported {origin}, not an installed package; run with `python -I`")

    timings: dict[str, list[float]] = {}
    skipped: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        for name, spec in WORKLOADS.items():
            run = _call(mf, name, spec, Path(tmp))
            if run is None:
                skipped.append(name)
                continue
            run()  # warm-up: JIT compilation or cache load, page cache, allocator
            samples = []
            for _ in range(repeat):
                start = time.perf_counter()
                run()
                samples.append(time.perf_counter() - start)
            timings[name] = samples
    return {"version": mf.__version__, "timings": timings, "skipped": skipped}


def _single_threaded_env() -> dict[str, str]:
    env = dict(os.environ)
    for var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMBA_NUM_THREADS"):
        env[var] = "1"
    env["TQDM_DISABLE"] = "1"
    return env


def _cold_start(python: str, env: dict[str, str], cwd: str) -> float:
    start = time.perf_counter()
    subprocess.run([python, "-I", "-c", COLD_START_CODE], check=True, env=env, cwd=cwd)
    return time.perf_counter() - start


def _measure_in(python: str, repeat: int, env: dict[str, str], cwd: str) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "measure.json"
        subprocess.run(
            [
                python,
                "-I",
                str(Path(__file__).resolve()),
                "measure",
                str(out),
                "--repeat",
                str(repeat),
            ],
            check=True,
            env=env,
            cwd=cwd,
        )
        return dict(json.loads(out.read_text(encoding="utf-8")))


def run(head: str, base: str, rounds: int, repeat: int) -> dict[str, Any]:
    env = _single_threaded_env()
    # abspath, not resolve(): a venv's python is a symlink to the base
    # interpreter, and following it would leave the venv.
    sides = {"head": os.path.abspath(head), "base": os.path.abspath(base)}
    results: dict[str, dict[str, Any]] = {
        side: {"version": None, "timings": {}, "skipped": set()} for side in sides
    }
    with tempfile.TemporaryDirectory() as cwd:
        for python in sides.values():  # fill each side's Numba cache before timing
            _cold_start(python, env, cwd)
        for round_ in range(rounds):
            order = ["head", "base"] if round_ % 2 == 0 else ["base", "head"]
            for side in order:
                print(f"round {round_ + 1}/{rounds}: {side}", flush=True)
                result = results[side]
                result["timings"].setdefault(COLD_START, []).append(
                    _cold_start(sides[side], env, cwd)
                )
                measured = _measure_in(sides[side], repeat, env, cwd)
                result["version"] = measured["version"]
                result["skipped"].update(measured["skipped"])
                for name, samples in measured["timings"].items():
                    result["timings"].setdefault(name, []).extend(samples)
    for result in results.values():
        result["skipped"] = sorted(result["skipped"])
    return results


def compare(results: dict[str, Any], max_slowdown: float) -> tuple[list[dict[str, Any]], list[str]]:
    """Return (one row per workload both sides ran, names of workloads only one side ran)."""
    head, base = results["head"]["timings"], results["base"]["timings"]
    rows = []
    for name in [*WORKLOADS, COLD_START]:
        if name not in head or name not in base:
            continue
        head_best, base_best = min(head[name]), min(base[name])
        ratio = head_best / base_best
        rows.append(
            {
                "workload": name,
                "base": base_best,
                "head": head_best,
                "ratio": ratio,
                "base_median": statistics.median(base[name]),
                "head_median": statistics.median(head[name]),
                "slower": ratio > 1 + max_slowdown,
            }
        )
    one_sided = sorted(head.keys() ^ base.keys())
    return rows, one_sided


def accepted_slowdown(messages: Iterable[str]) -> float | None:
    """The largest `Accept-Slowdown: N%` trailer value among the messages, as a fraction."""
    values = []
    for message in messages:
        for line in message.splitlines():
            match = re.fullmatch(rf"\s*{TRAILER}:\s*(\d+(?:\.\d+)?)\s*%\s*", line, re.IGNORECASE)
            if match:
                values.append(float(match.group(1)) / 100)
    return max(values) if values else None


def _release_tag(version: str) -> str | None:
    tags = subprocess.run(
        ["git", "tag", "--list"], check=True, capture_output=True, text=True
    ).stdout.split()
    for tag in tags:
        if tag.lstrip("vV") == version:
            return tag
    return None


def _messages_since(tag: str) -> list[str]:
    log = subprocess.run(
        ["git", "log", "--format=%B%x00", f"{tag}..HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return [m for m in log.split("\0") if m.strip()]


def _format_seconds(seconds: float) -> str:
    return f"{seconds * 1000:.0f} ms" if seconds < 10 else f"{seconds:.1f} s"


def _summary(markdown: str) -> None:
    if path := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(markdown + "\n")


def cmd_compare(path: Path, max_slowdown: float) -> int:
    results = json.loads(path.read_text(encoding="utf-8"))
    base_version, head_version = results["base"]["version"], results["head"]["version"]

    tag = _release_tag(base_version)
    accepted = accepted_slowdown(_messages_since(tag)) if tag else None
    if tag is None:
        print(f"::warning::no tag for release {base_version}; {TRAILER} trailers are not read")
    allowed = max(max_slowdown, accepted or 0.0)

    rows, one_sided = compare(results, allowed)
    if not rows:
        print("::error::no workload ran on both versions")
        return 1

    table = [
        f"| Workload | {base_version} | {head_version} | Change |",
        "| --- | ---: | ---: | ---: |",
    ]
    for row in rows:
        change = f"{(row['ratio'] - 1) * 100:+.1f}%"
        table.append(
            f"| {row['workload']} | {_format_seconds(row['base'])} | "
            f"{_format_seconds(row['head'])} | {'**' + change + '**' if row['slower'] else change} |"
        )
        print(
            f"{row['workload']:<48} base {_format_seconds(row['base']):>9}  "
            f"head {_format_seconds(row['head']):>9}  {change}"
        )
    notes = [f"Fastest of every timed run; fails above +{allowed * 100:.0f}%."]
    if accepted is not None:
        notes.append(f"`{TRAILER}: {accepted * 100:g}%` found in a commit since {tag}.")
    if one_sided:
        notes.append("Not compared (one version cannot run it): " + ", ".join(one_sided) + ".")
    slower = [row for row in rows if row["slower"]]
    _summary(
        f"### Performance: {head_version} vs released {base_version}"
        f"{' (slower)' if slower else ''}\n\n" + "\n".join(table) + "\n\n" + " ".join(notes)
    )
    for note in notes[1:]:
        print(note)

    if not slower:
        print(f"No workload is more than {allowed * 100:.0f}% slower than {base_version}")
        return 0
    for row in slower:
        print(
            f"::error title=Performance regression::{row['workload']} is "
            f"{(row['ratio'] - 1) * 100:.0f}% slower than release {base_version} "
            f"({_format_seconds(row['head'])} vs {_format_seconds(row['base'])}). "
            f"If this is intended, add a '{TRAILER}: N%' trailer to a commit message"
        )
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    m = sub.add_parser("measure")
    m.add_argument("out", type=Path)
    m.add_argument("--repeat", type=int, default=5)
    r = sub.add_parser("run")
    r.add_argument("out", type=Path)
    r.add_argument(
        "--head", required=True, help="python of the environment with the code under test"
    )
    r.add_argument("--base", required=True, help="python of the environment with the release")
    r.add_argument("--rounds", type=int, default=4)
    r.add_argument("--repeat", type=int, default=3)
    c = sub.add_parser("compare")
    c.add_argument("results", type=Path)
    c.add_argument("--max-slowdown", type=float, default=DEFAULT_MAX_SLOWDOWN)
    args = parser.parse_args(argv)

    if args.command == "measure":
        args.out.write_text(json.dumps(measure(args.repeat), indent=1), encoding="utf-8")
        return 0
    if args.command == "run":
        results = run(args.head, args.base, args.rounds, args.repeat)
        args.out.write_text(json.dumps(results, indent=1), encoding="utf-8")
        return 0
    return cmd_compare(args.results, args.max_slowdown)


if __name__ == "__main__":
    sys.exit(main())
