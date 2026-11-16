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
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from marketforge.aggregation.streaming import SUPPORTED_TIMEFRAMES, BarAggregator
from marketforge.calendars.trading_calendar import get_calendar
from marketforge.config.loader import load_catalog
from marketforge.domain.anomalies import AnomalyType
from marketforge.domain.bars import Bars
from marketforge.domain.markets import MarketType
from marketforge.domain.time import SECONDS_PER_DAY
from marketforge.domain.timeframes import Timeframe
from marketforge.output.writers import CandleWriter, OutputFormat, ensure_open_file_capacity
from marketforge.simulation.simulator import MarketSimulator
from marketforge.simulation.spec import MarketSpec, build_market_spec

TimeLike = int | float | str | dt.datetime | dt.date
DEFAULT_TIMEFRAMES = ("m1", "m5", "m15", "m30", "H1", "H4", "D1", "W1")
REGIME_NAMES = ("trend_up", "trend_down", "range", "high_volatility", "crash")

_ANOMALY_ALIASES = {
    "spike": "spikes",
    "flash": "flash_crash",
    "crash": "flash_crash",
    "flashcrash": "flash_crash",
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
        moment = dt.datetime(value.year, value.month, value.day, tzinfo=dt.UTC)
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
        moment = moment.replace(tzinfo=dt.UTC)
    return int(moment.timestamp())


def parse_timeframes(values: Iterable[str]) -> list[Timeframe]:
    out: list[Timeframe] = []
    for v in values:
        tf = Timeframe.from_string(v.strip())
        if tf not in SUPPORTED_TIMEFRAMES:
            raise ValueError(
                f"Unsupported timeframe {v!r}; choose from {[t.name for t in SUPPORTED_TIMEFRAMES]}"
            )
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
    assets: Sequence[str] | None = None,
    markets: Sequence[str | MarketType] | None = None,
    *,
    start: TimeLike,
    end: TimeLike,
    seed: int | None = None,
    timeframes: Sequence[str] = DEFAULT_TIMEFRAMES,
    anomalies: Sequence[str] = (),
    include_regime: bool = False,
    overrides: str | Path | None = None,
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
        if markets
        else None
    )
    symbol_market = {s: m for m, cfg in catalog.items() for s in cfg.symbols}
    by_market: dict[MarketType, list[str]] = {}
    if assets:
        requested = list(dict.fromkeys(a.strip().upper() for a in assets if a.strip()))
        unknown = [a for a in requested if a not in symbol_market]
        if unknown:
            raise ValueError(
                f"Unknown instrument(s): {', '.join(unknown)}. Run 'marketforge list-assets'."
            )
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
Sink = Callable[[MarketPlan, Timeframe, Bars | None], None]


def _run_market(
    request: Request,
    plan: MarketPlan,
    sink: Sink,
    on_day: Callable[[MarketType], None] | None = None,
) -> None:
    # Random draws are market-wide; everything after them runs only for the
    # selected instruments, whose columns come back in plan.selected order.
    sim = MarketSimulator(plan.spec, request.seed, instruments=plan.selected)
    cal = get_calendar(plan.market)
    aggs = {tf: BarAggregator(cal, tf, request.start, request.end) for tf in request.timeframes}
    first = request.start // SECONDS_PER_DAY
    last = (request.end - 1) // SECONDS_PER_DAY
    for day in range(first, last + 1):
        m1 = sim.simulate_day(day, request.start, request.end)
        if m1 is not None:
            anchor = cal.anchor_minutes(m1.timestamps)  # shared by every timeframe
            for tf, agg in aggs.items():
                sink(plan, tf, agg.push(m1, anchor))
        if on_day is not None:
            on_day(plan.market)
    for tf, agg in aggs.items():
        sink(plan, tf, agg.finish())


def execute(
    request: Request,
    sink: Sink,
    jobs: int = 1,
    on_day: Callable[[MarketType], None] | None = None,
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
    assets: Sequence[str] | None = None,
    *,
    start: TimeLike,
    end: TimeLike,
    markets: Sequence[str | MarketType] | None = None,
    seed: int | None = None,
    timeframes: Sequence[str] = ("m1",),
    anomalies: Sequence[str] = (),
    include_regime: bool = False,
    overrides: str | Path | None = None,
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
        assets,
        markets,
        start=start,
        end=end,
        seed=seed,
        timeframes=timeframes,
        anomalies=anomalies,
        include_regime=include_regime,
        overrides=overrides,
    )
    parts: dict[tuple[MarketType, Timeframe], list[Bars]] = {}

    def collect(plan: MarketPlan, tf: Timeframe, bars: Bars | None) -> None:
        if bars is not None and len(bars):
            parts.setdefault((plan.market, tf), []).append(bars)

    execute(request, collect)
    out = GeneratedData()
    out.seed = request.seed
    for plan in request.plans:
        for tf in request.timeframes:
            chunks = parts.get((plan.market, tf))
            frames = _frames(chunks or [], len(plan.selected), request.include_regime)
            for symbol, frame in zip(plan.selected, frames, strict=True):
                out.setdefault(symbol, {})[tf.name] = frame
    return out


_FRAME_COLUMNS = ("open", "high", "low", "close", "volume")


def _frames(chunks: list[Bars], n_instruments: int, include_regime: bool) -> list[pd.DataFrame]:
    """
    One DataFrame per instrument from a market's candle chunks.

    The values are copied once, straight from the chunks into an
    (instrument, column, row) block; each frame then wraps its own slice
    without another copy, and all frames share one (immutable) time index.
    """
    n = sum(len(c) for c in chunks)
    block = np.empty((n_instruments, len(_FRAME_COLUMNS), n))
    ts = np.empty(n, dtype=np.int64)
    regime = np.empty(n, dtype=np.int8)
    row = 0
    for c in chunks:
        k = len(c)
        for i, name in enumerate(_FRAME_COLUMNS):
            block[:, i, row : row + k] = getattr(c, name).T
        ts[row : row + k] = c.timestamps
        regime[row : row + k] = c.regime
        row += k
    index = pd.DatetimeIndex(pd.to_datetime(ts, unit="s", utc=True), name="time")
    codes = regime.astype(int)
    frames = []
    for j in range(n_instruments):
        df = pd.DataFrame(block[j].T, index=index, columns=list(_FRAME_COLUMNS), copy=False)
        if include_regime:
            df["regime"] = pd.Categorical.from_codes(codes, categories=list(REGIME_NAMES))
        frames.append(df)
    return frames


@dataclass
class DiskReport:
    """Result of :func:`generate_to_disk`."""

    seed: int
    paths: dict[str, dict[str, dict[str, Path]]] = field(
        default_factory=dict
    )  # market -> symbol -> tf -> path

    @property
    def n_files(self) -> int:
        return sum(len(tfs) for syms in self.paths.values() for tfs in syms.values())


def generate_to_disk(
    output_dir: str | Path,
    assets: Sequence[str] | None = None,
    *,
    start: TimeLike,
    end: TimeLike,
    markets: Sequence[str | MarketType] | None = None,
    seed: int | None = None,
    timeframes: Sequence[str] = DEFAULT_TIMEFRAMES,
    anomalies: Sequence[str] = (),
    include_regime: bool = False,
    overrides: str | Path | None = None,
    fmt: str | OutputFormat = OutputFormat.CSV,
    jobs: int = 1,
    request: Request | None = None,
    on_day: Callable[[MarketType], None] | None = None,
) -> DiskReport:
    """
    Generate candles and stream them to ``{output_dir}/{market}/{SYMBOL}_{tf}.{fmt}``.

    Takes the same arguments as :func:`generate` plus ``fmt`` (``csv`` or
    ``parquet``) and ``jobs`` (markets simulated in parallel). Memory use does
    not grow with the length of the range.
    """
    if request is None:
        request = plan_request(
            assets,
            markets,
            start=start,
            end=end,
            seed=seed,
            timeframes=timeframes,
            anomalies=anomalies,
            include_regime=include_regime,
            overrides=overrides,
        )
    fmt = OutputFormat(fmt)
    if fmt == OutputFormat.PARQUET:
        n_files = sum(len(p.selected) for p in request.plans) * len(request.timeframes)
        ensure_open_file_capacity(n_files)
    writers = {
        plan.market: CandleWriter(
            output_dir,
            plan.market.value,
            plan.selected,
            list(range(len(plan.selected))),
            request.timeframes,
            fmt,
            request.include_regime,
        )
        for plan in request.plans
    }

    def write(plan: MarketPlan, tf: Timeframe, bars: Bars | None) -> None:
        writers[plan.market].write(tf, bars)

    report = DiskReport(seed=request.seed)

    def close_all() -> BaseException | None:
        # Close every writer even if one fails; return the first error.
        first: BaseException | None = None
        for market, writer in writers.items():
            try:
                paths = writer.close()
            except BaseException as e:
                first = first or e
                continue
            report.paths[market.value] = {s: dict(tfs) for s, tfs in paths.items()}
        return first

    try:
        execute(request, write, jobs=jobs, on_day=on_day)
    except BaseException:
        close_all()  # the generation error wins over any error while closing
        raise
    error = close_all()
    if error is not None:
        raise error
    return report
