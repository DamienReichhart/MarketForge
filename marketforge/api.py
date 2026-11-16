# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the MIT License. See the LICENSE file in the project
# root for full license information.

"""
Public Python API.

    >>> import marketforge as mf
    >>> data = mf.generate(["EURUSD", "AAPL"], start="2024-01-01", end="2024-02-01",
    ...                    seed=42, timeframes=["m1", "H1", "D1"])
    >>> data["EURUSD"]["H1"].head()

:func:`generate` returns candles in memory as pandas DataFrames;
:func:`generate_to_disk` streams them to CSV or Parquet files. Both simulate
whole markets (see docs/adr/0001): asking for one instrument costs as much as
asking for its whole market, and returns exactly the same candles.
"""

from __future__ import annotations

import datetime as dt
import secrets
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Optional, Sequence, Union

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from marketforge.aggregation.streaming import SUPPORTED_TIMEFRAMES, BarAggregator, Bars
from marketforge.aggregation.timeframes import Timeframe
from marketforge.config.loader import load_catalog
from marketforge.config.settings import AnomalyType, MarketType
from marketforge.engine import MarketSimulator, MarketSpec, build_market_spec
from marketforge.output.writers import CandleWriter, OutputFormat
from marketforge.trading_calendar import SECONDS_PER_DAY, get_calendar

TimeLike = Union[int, float, str, dt.datetime, dt.date]
DEFAULT_TIMEFRAMES = ("m1", "m5", "m15", "m30", "H1", "H4", "D1", "W1")
REGIME_NAMES = ("trend_up", "trend_down", "range", "high_volatility", "crash")

_ANOMALY_ALIASES = {
    "spike": "spikes", "flash": "flash_crash", "crash": "flash_crash", "flashcrash": "flash_crash",
}


# ----------------------------------------------------------------- parsing
def parse_time(value: TimeLike) -> int:
    """
    Convert a time to Unix seconds (UTC).

    Accepts Unix seconds (int, float or digit string), ISO 8601 dates or
    datetimes ("2024-01-01", "2024-01-01T09:30", "2024-01-01T09:30-05:00"),
    and ``date`` / ``datetime`` objects. Naive values are taken as UTC.
    """
    if isinstance(value, bool):
        raise TypeError("time must not be a bool")
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, float):
        return int(value)
    if isinstance(value, dt.datetime):
        moment = value
    elif isinstance(value, dt.date):
        moment = dt.datetime(value.year, value.month, value.day)
    elif isinstance(value, str):
        text = value.strip()
        if text.lstrip("-").isdigit():
            return int(text)
        try:
            moment = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError(
                f"Cannot parse time {value!r}: use Unix seconds or ISO 8601 "
                "like 2024-01-01 or 2024-01-01T09:30"
            ) from None
    else:
        raise TypeError(f"Unsupported time value: {value!r}")
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=dt.timezone.utc)
    return int(moment.timestamp())


def parse_timeframes(values: Iterable[str]) -> list[Timeframe]:
    out: list[Timeframe] = []
    for v in values:
        tf = Timeframe.from_string(v.strip())
        if tf not in SUPPORTED_TIMEFRAMES:
            raise ValueError(f"Unsupported timeframe {v!r}; choose from {[t.name for t in SUPPORTED_TIMEFRAMES]}")
        if tf not in out:
            out.append(tf)
    if not out:
        raise ValueError("At least one timeframe is required")
    return out


def parse_anomalies(values: Iterable[str]) -> frozenset[AnomalyType]:
    out = set()
    for v in values:
        key = _ANOMALY_ALIASES.get(v.strip().lower(), v.strip().lower())
        if key in ("gap", "gaps"):
            raise ValueError(
                "The 'gaps' anomaly was removed in 3.0: overnight and weekend gaps now "
                "come from market closures automatically."
            )
        try:
            out.add(AnomalyType(key))
        except ValueError:
            raise ValueError(f"Unknown anomaly {v!r}; choose from spikes, flash_crash") from None
    return frozenset(out)


# ---------------------------------------------------------------- planning
@dataclass
class MarketPlan:
    """What to simulate for one market and which instruments to output."""

    spec: MarketSpec
    selected: list[str]

    @property
    def market(self) -> MarketType:
        return self.spec.market

    @property
    def columns(self) -> list[int]:
        return [self.spec.symbols.index(s) for s in self.selected]


@dataclass
class Request:
    """A fully resolved generation request."""

    plans: list[MarketPlan]
    start: int
    end: int
    seed: int
    timeframes: list[Timeframe]
    include_regime: bool = False

    @property
    def n_days(self) -> int:
        return (self.end - 1) // SECONDS_PER_DAY - self.start // SECONDS_PER_DAY + 1


def plan_request(
    assets: Optional[Sequence[str]] = None,
    markets: Optional[Sequence[Union[str, MarketType]]] = None,
    *,
    start: TimeLike,
    end: TimeLike,
    seed: Optional[int] = None,
    timeframes: Sequence[str] = DEFAULT_TIMEFRAMES,
    anomalies: Sequence[str] = (),
    include_regime: bool = False,
    overrides: Optional[Union[str, Path]] = None,
) -> Request:
    """
    Resolve user input into a :class:`Request`.

    With ``assets`` only, their markets are inferred; with ``markets`` only,
    every instrument of those markets is produced; with both, only the listed
    assets that belong to the listed markets are produced. With neither, all
    markets are produced.

    Raises:
        ValueError: on unknown assets or markets, an empty selection, or an
            invalid time range.
    """
    t0, t1 = parse_time(start), parse_time(end)
    if t0 >= t1:
        raise ValueError(f"start ({t0}) must be before end ({t1})")
    if seed is None:
        seed = secrets.randbits(32)
    if seed < 0:
        raise ValueError(f"seed must be a non-negative integer, got {seed}")
    tfs = parse_timeframes(timeframes)
    anomaly_types = parse_anomalies(anomalies)
    catalog = load_catalog(overrides)

    wanted_markets = (
        [m if isinstance(m, MarketType) else MarketType(str(m).strip().lower()) for m in markets]
        if markets else None
    )
    symbol_market = {s: m for m, cfg in catalog.items() for s in cfg.symbols}
    by_market: dict[MarketType, list[str]] = {}
    if assets:
        requested = list(dict.fromkeys(a.strip().upper() for a in assets if a.strip()))
        unknown = [a for a in requested if a not in symbol_market]
        if unknown:
            raise ValueError(f"Unknown instrument(s): {', '.join(unknown)}. Run 'marketforge list-assets'.")
        for a in requested:
            m = symbol_market[a]
            if wanted_markets is None or m in wanted_markets:
                by_market.setdefault(m, []).append(a)
        if not by_market:
            raise ValueError("None of the requested instruments belong to the requested markets")
    else:
        for m in wanted_markets or list(MarketType):
            by_market[m] = list(catalog[m].symbols)

    plans = [
        MarketPlan(build_market_spec(catalog[m], anomaly_types), selected)
        for m, selected in by_market.items()
    ]
    return Request(plans, t0, t1, int(seed), tfs, include_regime)


# ---------------------------------------------------------------- running
# Receives candles of the plan's *selected* instruments, in plan.selected order.
Sink = Callable[[MarketPlan, Timeframe, Optional[Bars]], None]


def _run_market(
    request: Request,
    plan: MarketPlan,
    sink: Sink,
    on_day: Optional[Callable[[MarketType], None]] = None,
) -> None:
    sim = MarketSimulator(plan.spec, request.seed)
    cal = get_calendar(plan.market)
    aggs = {tf: BarAggregator(cal, tf, request.start, request.end) for tf in request.timeframes}
    cols = plan.columns
    first = request.start // SECONDS_PER_DAY
    last = (request.end - 1) // SECONDS_PER_DAY
    for day in range(first, last + 1):
        res = sim.simulate_day(day, request.start, request.end)
        if res is not None:
            # Only the selected instruments are aggregated and written.
            c = cols
            m1 = Bars(res.timestamps, res.open[:, c], res.high[:, c], res.low[:, c],
                      res.close[:, c], res.volume[:, c], res.regime)
            for tf, agg in aggs.items():
                sink(plan, tf, agg.push(m1))
        if on_day is not None:
            on_day(plan.market)
    for tf, agg in aggs.items():
        sink(plan, tf, agg.finish())


def execute(
    request: Request,
    sink: Sink,
    jobs: int = 1,
    on_day: Optional[Callable[[MarketType], None]] = None,
) -> None:
    """Run every market of a request, optionally in parallel threads."""
    # The matrix products here are tiny; multithreaded BLAS only burns CPU
    # (4x the CPU time for the same wall time) and oversubscribes parallel jobs.
    with threadpool_limits(limits=1, user_api="blas"):
        if jobs <= 1 or len(request.plans) == 1:
            for plan in request.plans:
                _run_market(request, plan, sink, on_day)
            return
        with ThreadPoolExecutor(max_workers=min(jobs, len(request.plans))) as pool:
            for f in [pool.submit(_run_market, request, p, sink, on_day) for p in request.plans]:
                f.result()


# ------------------------------------------------------------------ public
class GeneratedData(dict):
    """``{symbol: {timeframe: DataFrame}}`` plus the seed that produced it."""

    seed: int


def generate(
    assets: Optional[Sequence[str]] = None,
    *,
    start: TimeLike,
    end: TimeLike,
    markets: Optional[Sequence[Union[str, MarketType]]] = None,
    seed: Optional[int] = None,
    timeframes: Sequence[str] = ("m1",),
    anomalies: Sequence[str] = (),
    include_regime: bool = False,
    overrides: Optional[Union[str, Path]] = None,
) -> GeneratedData:
    """
    Generate candles in memory.

    Args:
        assets: Instruments to return (e.g. ``["EURUSD", "AAPL"]``). If omitted,
            every instrument of ``markets`` (default: all markets).
        start, end: Range ``[start, end)`` as Unix seconds, ISO 8601 strings or
            date/datetime objects (naive = UTC).
        markets: Restrict to these markets (``crypto``, ``forex``, ``stocks``).
        seed: Non-negative integer; the same seed returns identical candles.
            If omitted a random seed is chosen and exposed as ``result.seed``.
        timeframes: Any of m1, m5, m15, m30, H1, H4, D1, W1.
        anomalies: Optional ``spikes`` and/or ``flash_crash``.
        include_regime: Add a ``regime`` column (market regime name at candle close).
        overrides: Path to a TOML override file (custom prices, new instruments).

    Returns:
        :class:`GeneratedData` mapping symbol -> timeframe -> DataFrame with a
        UTC ``DatetimeIndex`` named ``time`` and columns open, high, low, close,
        volume (and regime).
    """
    request = plan_request(
        assets, markets, start=start, end=end, seed=seed, timeframes=timeframes,
        anomalies=anomalies, include_regime=include_regime, overrides=overrides,
    )
    parts: dict[tuple[MarketType, Timeframe], list[Bars]] = {}

    def collect(plan: MarketPlan, tf: Timeframe, bars: Optional[Bars]) -> None:
        if bars is not None and len(bars):
            parts.setdefault((plan.market, tf), []).append(bars)

    execute(request, collect)
    out = GeneratedData()
    out.seed = request.seed
    for plan in request.plans:
        for tf in request.timeframes:
            chunks = parts.get((plan.market, tf))
            allb = Bars.concat(chunks) if chunks else None
            for j, symbol in enumerate(plan.selected):
                out.setdefault(symbol, {})[tf.name] = _frame(allb, j, request.include_regime)
    return out


def _frame(bars: Optional[Bars], j: int, include_regime: bool) -> pd.DataFrame:
    if bars is None:
        ts = np.empty(0, dtype=np.int64)
        data = {c: np.empty(0) for c in ("open", "high", "low", "close", "volume")}
        regime = np.empty(0, dtype=np.int8)
    else:
        ts = bars.timestamps
        data = {
            "open": bars.open[:, j], "high": bars.high[:, j], "low": bars.low[:, j],
            "close": bars.close[:, j], "volume": bars.volume[:, j],
        }
        regime = bars.regime
    index = pd.DatetimeIndex(pd.to_datetime(ts, unit="s", utc=True), name="time")
    df = pd.DataFrame(data, index=index)
    if include_regime:
        df["regime"] = pd.Categorical.from_codes(regime.astype(int), categories=list(REGIME_NAMES))
    return df


@dataclass
class DiskReport:
    """Result of :func:`generate_to_disk`."""

    seed: int
    paths: dict[str, dict[str, dict[str, Path]]] = field(default_factory=dict)  # market -> symbol -> tf -> path

    @property
    def n_files(self) -> int:
        return sum(len(tfs) for syms in self.paths.values() for tfs in syms.values())


def generate_to_disk(
    output_dir: Union[str, Path],
    assets: Optional[Sequence[str]] = None,
    *,
    start: TimeLike,
    end: TimeLike,
    markets: Optional[Sequence[Union[str, MarketType]]] = None,
    seed: Optional[int] = None,
    timeframes: Sequence[str] = DEFAULT_TIMEFRAMES,
    anomalies: Sequence[str] = (),
    include_regime: bool = False,
    overrides: Optional[Union[str, Path]] = None,
    fmt: Union[str, OutputFormat] = OutputFormat.CSV,
    jobs: int = 1,
    request: Optional[Request] = None,
    on_day: Optional[Callable[[MarketType], None]] = None,
) -> DiskReport:
    """
    Generate candles and stream them to ``{output_dir}/{market}/{SYMBOL}_{tf}.{fmt}``.

    Takes the same arguments as :func:`generate` plus ``fmt`` (``csv`` or
    ``parquet``) and ``jobs`` (markets simulated in parallel). Memory use does
    not grow with the length of the range.
    """
    if request is None:
        request = plan_request(
            assets, markets, start=start, end=end, seed=seed, timeframes=timeframes,
            anomalies=anomalies, include_regime=include_regime, overrides=overrides,
        )
    writers = {
        plan.market: CandleWriter(
            output_dir, plan.market.value, plan.selected, list(range(len(plan.selected))),
            request.timeframes, OutputFormat(fmt), request.include_regime,
        )
        for plan in request.plans
    }

    def write(plan: MarketPlan, tf: Timeframe, bars: Optional[Bars]) -> None:
        writers[plan.market].write(tf, bars)

    report = DiskReport(seed=request.seed)
    try:
        execute(request, write, jobs=jobs, on_day=on_day)
    finally:
        for market, writer in writers.items():
            paths = writer.close()
            report.paths[market.value] = {s: {tf: p for tf, p in tfs.items()} for s, tfs in paths.items()}
    return report
