"""The Python side of the website's playground.

The playground's Web Worker (worker.ts) runs this module in Pyodide, next to
the MarketForge wheel the site was built with, and calls the functions below
with JSON strings. Requests are checked against the caps in limits.json
before anything is simulated, because a browser tab that runs out of memory
dies without a message.
"""

from __future__ import annotations

import io
import json
import math
import time
import warnings
from typing import Any

import pandas as pd

import marketforge as mf

_result: mf.GeneratedData | None = None
_timeframes: list[str] = []
# Markets generated in this visit: their regimes are calibrated (and cached by
# MarketForge), so their next requests skip limits.json's calibrationSeconds.
_calibrated: set[str] = set()

EPOCH = pd.Timestamp(0, tz="UTC")

# threadpoolctl (which MarketForge uses to keep BLAS on one thread) calls a
# Pyodide API that Pyodide 314 deprecates; nothing for a visitor to act on.
warnings.filterwarnings("ignore", message=r"JsProxy\.as_object_map", category=RuntimeWarning)


def describe() -> str:
    """The MarketForge version and model revision running in the page."""
    return json.dumps({"version": mf.__version__, "model_revision": mf.MODEL_REVISION})


def _selection(request: dict[str, Any]) -> dict[str, Any]:
    """The keyword arguments `mf.generate` and `mf.estimate` share."""
    instruments = request.get("instruments") or None
    return {
        "instruments": instruments,
        "markets": None if instruments else [request["market"]],
        "start": request["start"],
        "days": int(request["days"]),
        "seed": int(request["seed"]),
        "timeframes": request["timeframes"],
        "with_regime": bool(request.get("include_regime")),
        "with_spread": bool(request.get("include_spread")),
    }


def check(request_json: str, limits_json: str) -> str:
    """Whether a request fits the playground's caps, and what it would cost."""
    request, limits = json.loads(request_json), json.loads(limits_json)
    days = int(request["days"])
    if not 1 <= days <= limits["maxDays"]:
        return json.dumps({"ok": False, "reason": f"Choose 1 to {limits['maxDays']} days."})
    if not request["timeframes"]:
        return json.dumps({"ok": False, "reason": "Choose at least one timeframe."})
    selection = _selection(request)
    estimate = mf.estimate(**selection, format="csv")
    markets = selection["markets"] or sorted(
        set(mf.instruments().loc[selection["instruments"], "market"])
    )
    calibration = sum(
        limits["calibrationSeconds"].get(m, 0) for m in markets if m not in _calibrated
    )
    seconds = estimate.seconds * limits["browserFactor"] + calibration
    memory_mb = estimate.memory_bytes / 1e6
    reasons = []
    if seconds > limits["maxSeconds"]:
        reasons.append(f"about {math.ceil(seconds)} s of simulation in the browser")
    if estimate.rows > limits["maxRows"]:
        reasons.append(f"{estimate.rows:,} candles")
    if memory_mb > limits["maxMemoryMB"]:
        reasons.append(f"about {memory_mb:,.0f} MB of memory")
    return json.dumps(
        {
            "ok": not reasons,
            "reason": (
                "Too large for the web version: " + ", ".join(reasons) + ". "
                "Shorten the range, pick fewer instruments or coarser timeframes, "
                "or run the command below with the installed package."
            )
            if reasons
            else None,
            "rows": estimate.rows,
            "seconds": seconds,
            "calibration_seconds": calibration,
            "markets": markets,
            "memory_mb": memory_mb,
        }
    )


def run(request_json: str, limits_json: str) -> str:
    """Generate a request that fits the caps and keep the result for `candles` and `export`."""
    global _result, _timeframes
    verdict = json.loads(check(request_json, limits_json))
    if not verdict["ok"]:
        raise ValueError(verdict["reason"])
    request = json.loads(request_json)
    _result = None  # free the previous result before simulating the next one
    selection = _selection(request)
    started = time.perf_counter()
    _result = mf.generate(
        **selection,
        anomalies=request.get("anomalies") or (),
        with_bid_ask=bool(request.get("include_bid_ask")),
    )
    _timeframes = list(selection["timeframes"])
    rows = int(_result.summary()["candles"].sum())
    seconds = time.perf_counter() - started
    _calibrated.update(verdict["markets"])
    return json.dumps(
        {"instruments": list(_result), "timeframes": _timeframes, "rows": rows, "seconds": seconds}
    )


def _stored() -> mf.GeneratedData:
    if _result is None:
        raise ValueError("Generate data first.")
    return _result


def candles(symbol: str, timeframe: str, limit: int) -> str:
    """The last `limit` candles of one instrument, in the chart's format."""
    frame = _stored()[symbol][timeframe]
    shown = frame.iloc[-limit:]
    times = ((shown.index - EPOCH) // pd.Timedelta(seconds=1)).tolist()
    columns = [shown[c].tolist() for c in ("open", "high", "low", "close", "volume")]
    spread = shown["spread"].tolist() if "spread" in shown else [None] * len(shown)
    regime = shown["regime"].astype(str).tolist() if "regime" in shown else [None] * len(shown)
    rows = [list(row) for row in zip(times, *columns, spread, regime, strict=True)]
    return json.dumps({"total": len(frame), "candles": rows})


def export(timeframe: str, fmt: str) -> bytes:
    """Every instrument's candles at one timeframe, as one long CSV or Parquet file."""
    data = _stored()
    frame = data.to_long(timeframe if len(_timeframes) > 1 else None).reset_index()
    buffer = io.BytesIO()
    if fmt == "parquet":
        frame.to_parquet(buffer, index=False)
    else:
        frame["time"] = frame["time"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        frame.to_csv(buffer, index=False)
    return buffer.getvalue()
