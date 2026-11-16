# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the MIT License. See the LICENSE file in the project
# root for full license information.

"""
Command-line interface.

    marketforge generate -o ./data --from 2024-01-01 --to 2025-01-01 --assets EURUSD --seed 42
    marketforge list-assets --market forex
    marketforge validate --input ./data/forex/EURUSD_m1.csv --market forex
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path
from typing import Any

import click

from marketforge import __version__
from marketforge.domain.markets import MarketType


def _split(value: str | None) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()] if value else []


class _Group(click.Group):
    """Prints unexpected errors as one line unless ``--debug`` is given."""

    def invoke(self, ctx: click.Context) -> Any:
        try:
            return super().invoke(ctx)
        except (click.ClickException, click.exceptions.Exit, click.exceptions.Abort, SystemExit):
            raise
        except Exception as e:  # user-facing errors: one line unless --debug
            if ctx.params.get("debug"):
                raise
            click.secho(f"Error: {e}", fg="red", err=True)
            click.echo("Run again with --debug for the full traceback.", err=True)
            ctx.exit(1)


@click.group(cls=_Group, context_settings={"help_option_names": ["-h", "--help"]})
@click.option("--debug", is_flag=True, help="Show full tracebacks on errors.")
@click.version_option(version=__version__, prog_name="marketforge")
def cli(debug: bool) -> None:
    """MarketForge: realistic synthetic OHLCV data for crypto, forex and stocks."""


# ------------------------------------------------------------------ generate
@cli.command()
@click.option(
    "--output-dir",
    "-o",
    type=click.Path(file_okay=False),
    help="Directory to write {market}/{SYMBOL}_{tf}.{csv|parquet} files into.",
)
@click.option(
    "--from",
    "start",
    required=True,
    metavar="TIME",
    help="Start (inclusive): 2024-01-01, 2024-01-01T09:30, or Unix seconds. UTC unless an offset is given.",
)
@click.option(
    "--to", "end", required=True, metavar="TIME", help="End (exclusive), same formats as --from."
)
@click.option(
    "--assets",
    "-a",
    metavar="LIST",
    help="Comma-separated instruments, e.g. EURUSD,AAPL,BTCUSD. Markets are inferred.",
)
@click.option(
    "--market",
    "-m",
    "markets",
    metavar="LIST",
    help="Comma-separated markets: crypto, forex, stocks, or all (default when --assets is not given).",
)
@click.option(
    "--seed",
    "-s",
    type=click.IntRange(min=0),
    help="Seed for reproducible output. Printed when omitted so any run can be repeated.",
)
@click.option(
    "--timeframes",
    "-t",
    default="m1,m5,m15,m30,H1,H4,D1,W1",
    show_default=True,
    help="Comma-separated: m1,m5,m15,m30,H1,H4,D1,W1.",
)
@click.option(
    "--anomalies", metavar="LIST", help="Optional unrealistic events: spikes, flash_crash."
)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["csv", "parquet"]),
    default="csv",
    show_default=True,
    help="Output file format.",
)
@click.option(
    "--config",
    "overrides",
    type=click.Path(exists=True, dir_okay=False),
    help="TOML override file to change or add instruments.",
)
@click.option(
    "--with-regime",
    is_flag=True,
    help="Add a 'regime' column (0=trend_up 1=trend_down 2=range 3=high_volatility 4=crash).",
)
@click.option(
    "--jobs",
    "-j",
    type=click.IntRange(min=1),
    default=None,
    help="Markets simulated in parallel. Default: one per market, up to the CPU count.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Print what would be generated (files, rows, size, time) and exit.",
)
@click.option(
    "--progress/--no-progress", default=True, show_default=True, help="Show a progress bar."
)
def generate(
    output_dir: str | None,
    start: str,
    end: str,
    assets: str | None,
    markets: str | None,
    seed: int | None,
    timeframes: str,
    anomalies: str | None,
    fmt: str,
    overrides: str | None,
    with_regime: bool,
    jobs: int | None,
    dry_run: bool,
    progress: bool,
) -> None:
    """Generate candles and write them to disk."""
    import os

    from marketforge.api.disk import generate_to_disk
    from marketforge.api.planning import plan_request

    market_list = _split(markets)
    if [m.lower() for m in market_list] == ["all"]:
        market_list = []
    request = plan_request(
        _split(assets) or None,
        market_list or None,
        start=start,
        end=end,
        seed=seed,
        timeframes=_split(timeframes),
        anomalies=_split(anomalies),
        include_regime=with_regime,
        overrides=overrides,
    )
    jobs = jobs or min(len(request.plans), os.cpu_count() or 1)
    _print_plan(request, fmt, output_dir, seed is None)
    if dry_run:
        return
    if not output_dir:
        raise click.UsageError("Missing option '--output-dir' / '-o'.")

    t0 = time.time()
    total = request.n_days * len(request.plans)
    bar = None
    lock = threading.Lock()
    if progress:
        from tqdm import tqdm

        bar = tqdm(total=total, unit="day", desc="Simulating", ncols=90, file=sys.stderr)

    def tick(_: MarketType) -> None:
        if bar is not None:
            with lock:
                bar.update(1)

    try:
        report = generate_to_disk(
            output_dir, request=request, start=start, end=end, fmt=fmt, jobs=jobs, on_day=tick
        )
    finally:
        if bar is not None:
            bar.close()
    elapsed = time.time() - t0
    click.secho(
        f"\nDone in {elapsed:.1f}s: {report.n_files} files in {Path(output_dir).resolve()}",
        fg="green",
    )
    click.echo(f"Reproduce with --seed {report.seed}")


def _print_plan(request: Any, fmt: str, output_dir: str | None, random_seed: bool) -> None:
    import datetime as dt

    from marketforge.calendars.trading_calendar import get_calendar

    def iso(t: int) -> str:
        return dt.datetime.fromtimestamp(t, dt.UTC).strftime("%Y-%m-%d %H:%M UTC")

    click.secho("MarketForge " + __version__, bold=True)
    click.echo(f"  Range       {iso(request.start)} -> {iso(request.end)}")
    click.echo(
        f"  Seed        {request.seed}"
        + ("  (random; pass --seed to fix it)" if random_seed else "")
    )
    click.echo(f"  Timeframes  {', '.join(tf.name for tf in request.timeframes)}")
    rows = 0
    seconds = 0.0
    for plan in request.plans:
        open_minutes = get_calendar(plan.market).count_open_minutes(request.start, request.end)
        per_asset = sum(open_minutes // max(1, min(tf.minutes, 1440)) for tf in request.timeframes)
        rows += per_asset * len(plan.selected)
        seconds += _simulation_seconds(plan, request.n_days, open_minutes)
        names = ", ".join(plan.selected[:6]) + (
            f" (+{len(plan.selected) - 6} more)" if len(plan.selected) > 6 else ""
        )
        click.echo(
            f"  {plan.market.value:<11} {len(plan.selected)} instrument(s), {open_minutes:,} open minutes: {names}"
        )
    bytes_per_row = 68 if fmt == "csv" else 33
    seconds += rows * (_CSV_ROW_SECONDS if fmt == "csv" else _PARQUET_ROW_SECONDS)
    n_files = sum(len(p.selected) for p in request.plans) * len(request.timeframes)
    click.echo(
        f"  Output      {n_files} {fmt} files, ~{rows:,} rows, ~{_human(rows * bytes_per_row)}"
        + (f" in {output_dir}" if output_dir else "")
    )
    click.echo(f"  Estimate    ~{_duration(seconds)} on one core")


# Cost model behind --dry-run's time estimate (one core, measured on 3.1).
# Random draws are market-wide and fixed-shape: 1440 x (factors + 3 x
# instruments) per simulated day, whatever is selected. The rest of the
# simulation runs only for the selected instruments' open minutes.
_DRAW_SECONDS = 7e-9
_INSTRUMENT_MINUTE_SECONDS = 35e-9
_MARKET_DAY_SECONDS = 1e-3  # per-day bookkeeping (calendar, aggregation, buffers)
_CSV_ROW_SECONDS = 0.75e-6  # aggregation + formatting + writing, per output row
_PARQUET_ROW_SECONDS = 0.6e-6


def _simulation_seconds(plan: Any, n_days: int, open_minutes: int) -> float:
    structure = plan.spec.structure
    draws = 1440 * (len(structure.factors) + 3 * len(structure.instruments))
    return n_days * (draws * _DRAW_SECONDS + _MARKET_DAY_SECONDS) + (
        open_minutes * len(plan.selected) * _INSTRUMENT_MINUTE_SECONDS
    )


def _human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _duration(s: float) -> str:
    if s < 60:
        return f"{max(1, round(s))}s"
    if s < 3600:
        return f"{s / 60:.0f} min"
    return f"{s / 3600:.1f} h"


# --------------------------------------------------------------- list-assets
@cli.command("list-assets")
@click.option(
    "--market", "-m", type=click.Choice([m.value for m in MarketType]), help="Only this market."
)
@click.option(
    "--config",
    "overrides",
    type=click.Path(exists=True, dir_okay=False),
    help="TOML override file to apply first.",
)
def list_assets(market: str | None, overrides: str | None) -> None:
    """List available instruments with their start price and volatility."""
    from marketforge.config.loader import load_catalog
    from marketforge.simulation.spec import build_market_spec

    catalog = load_catalog(overrides)
    for m, cfg in catalog.items():
        if market and m.value != market:
            continue
        spec = build_market_spec(cfg)
        anchors = set(spec.structure.factors)
        click.secho(f"\n{m.value} ({cfg.n_assets} instruments)", bold=True)
        click.echo(f"  {'SYMBOL':<10}{'START':>14}{'VOL':>8}{'DRIFT':>8}  NOTE")
        for s in cfg.symbols:
            a = cfg.get_asset(s)
            note = (
                ""
                if spec.structure.is_identity
                else ("anchor" if s in anchors else "cross (derived)")
            )
            click.echo(
                f"  {s:<10}{a.start_price:>14,.4f}{a.volatility:>8.3f}{a.drift:>8.3f}  {note}"
            )


# ------------------------------------------------------------------ validate
@cli.command()
@click.option(
    "--input",
    "input_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="CSV or Parquet file with open/high/low/close columns.",
)
@click.option(
    "--market",
    required=True,
    type=click.Choice([m.value for m in MarketType]),
    help="Market whose target bands to apply.",
)
def validate(input_path: str, market: str) -> None:
    """Check a candle file against real-market stylized facts (exit 1 on failure)."""
    import pandas as pd

    from marketforge.validation.report import validate_ohlcv

    path = Path(input_path)
    df = pd.read_parquet(path) if path.suffix == ".parquet" else pd.read_csv(path)
    missing = {"open", "high", "low", "close"} - set(df.columns)
    if missing:
        raise click.UsageError(f"{path} lacks column(s): {', '.join(sorted(missing))}")
    report = validate_ohlcv(
        df["open"].to_numpy(),
        df["high"].to_numpy(),
        df["low"].to_numpy(),
        df["close"].to_numpy(),
        MarketType(market),
    )
    click.echo(report.summary())
    sys.exit(0 if report.passed else 1)


def main() -> None:
    """Console-script entry point."""
    cli()
