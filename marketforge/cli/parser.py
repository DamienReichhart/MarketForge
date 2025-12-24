# MarketForge
# Copyright (C) 2026 REICHHART Damien
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""
CLI argument parser using Click.

Provides the simplified command-line interface for MarketForge
using pre-configured market configs.
"""

from __future__ import annotations

import sys
from typing import Optional

import click

from marketforge import __version__
from marketforge.configs.base import MarketType
from marketforge.configs.loader import get_available_markets


def parse_markets(ctx, param, value: str) -> list[MarketType]:
    """Click callback to parse market selection."""
    if not value or value.lower() == "all":
        return list(MarketType)
    
    markets = []
    for part in value.split(","):
        part = part.strip().lower()
        if part:
            try:
                markets.append(MarketType(part))
            except ValueError:
                raise click.BadParameter(
                    f"Invalid market '{part}'. Valid options: {get_available_markets()}"
                )
    
    return markets


def parse_anomalies(ctx, param, value: Optional[str]) -> Optional[frozenset]:
    """Click callback to parse anomaly types."""
    if not value:
        return None
    
    from marketforge.config.settings import AnomalyType
    
    anomalies = set()
    for part in value.split(","):
        part = part.strip().lower()
        if not part:
            continue
        
        # Map common aliases
        aliases = {
            "gap": "gaps",
            "spike": "spikes",
            "flash": "flash_crash",
            "crash": "flash_crash",
            "flashcrash": "flash_crash",
        }
        part = aliases.get(part, part)
        
        try:
            anomalies.add(AnomalyType(part))
        except ValueError:
            valid = [a.value for a in AnomalyType]
            raise click.BadParameter(
                f"Invalid anomaly type '{part}'. Valid options: {valid}"
            )
    
    return frozenset(anomalies) if anomalies else None


def parse_assets(ctx, param, value: Optional[str]) -> Optional[list[str]]:
    """Click callback to parse asset symbols."""
    if not value:
        return None
    
    assets = []
    for part in value.split(","):
        part = part.strip().upper()
        if part:
            assets.append(part)
    
    if not assets:
        return None
    
    # Remove duplicates while preserving order
    seen = set()
    unique_assets = []
    for asset in assets:
        if asset not in seen:
            seen.add(asset)
            unique_assets.append(asset)
    
    return unique_assets if unique_assets else None


@click.command(name="marketforge")
@click.option(
    "--output-dir", "-o",
    required=True,
    type=click.Path(),
    help=(
        "Output directory where CSV files will be written. "
        "Directory structure: {output_dir}/{market}/{symbol}_{timeframe}.csv. "
        "Example: ./data/forex/EURUSD_m1.csv. "
        "The directory will be created if it doesn't exist."
    )
)
@click.option(
    "--from", "from_ts",
    required=True,
    type=int,
    help=(
        "Start timestamp in Unix epoch seconds (UTC). "
        "Example: 1764543600 (2025-11-30 23:00:00 UTC). "
        "Use 'date +%s' on Linux/Mac or online converters to get timestamps. "
        "Must be less than --to timestamp."
    )
)
@click.option(
    "--to", "to_ts",
    required=True,
    type=int,
    help=(
        "End timestamp in Unix epoch seconds (UTC). "
        "Example: 1767221999 (2025-12-31 22:59:59 UTC). "
        "Data generation stops at this timestamp (exclusive). "
        "Must be greater than --from timestamp."
    )
)
@click.option(
    "--market", "-m",
    default="all",
    callback=parse_markets,
    help=(
        "Markets to generate. Available markets: 'forex' (81 pairs), "
        "'crypto' (53 assets), 'stocks' (74 symbols). "
        "Use 'all' to generate all markets (default). "
        "For multiple markets, use comma-separated: 'forex,crypto'. "
        "Examples: --market forex, --market crypto,stocks, --market all"
    )
)
@click.option(
    "--seed", "-s",
    default=None,
    type=int,
    help=(
        "Random seed for reproducible data generation. "
        "If provided, the same seed will produce identical output. "
        "If not specified (default), uses random entropy for each run. "
        "Recommended for testing and debugging. "
        "Example: --seed 42"
    )
)
@click.option(
    "--anomalies",
    default=None,
    callback=parse_anomalies,
    help=(
        "Comma-separated list of anomaly types to inject into the data. "
        "Available types: 'gaps' (price gaps), 'spikes' (sudden price movements), "
        "'flash_crash' (rapid price drops). "
        "Aliases accepted: 'gap'->'gaps', 'spike'->'spikes', "
        "'flash'/'crash'/'flashcrash'->'flash_crash'. "
        "If not specified, no anomalies are injected. "
        "Examples: --anomalies gaps, --anomalies gaps,spikes, --anomalies flash_crash"
    )
)
@click.option(
    "--timeframes", "-t",
    default="m1,m5,m15,m30,H1,H4,D1,W1",
    type=str,
    help=(
        "Comma-separated list of timeframes to generate. "
        "Available timeframes: m1 (1 minute), m5 (5 minutes), m15 (15 minutes), "
        "m30 (30 minutes), H1 (1 hour), H4 (4 hours), D1 (1 day), W1 (1 week). "
        "Default: 'm1,m5,m15,m30,H1,H4,D1,W1'. "
        "All timeframes are aggregated from m1 data. "
        "Note: Higher timeframes (W1) require sufficient data duration. "
        "Examples: --timeframes m1,H1,D1, --timeframes m1,m5,m15"
    )
)
@click.option(
    "--batch-size",
    default=25,
    type=int,
    help=(
        "Number of assets to process per batch for memory management. "
        "Larger batches use more memory but may be faster. "
        "Smaller batches use less memory but may be slower. "
        "Default: 25. Recommended range: 10-50. "
        "Adjust based on available RAM and number of assets. "
        "Example: --batch-size 30"
    )
)
@click.option(
    "--threads", "--thread-count",
    default=None,
    type=int,
    help=(
        "Number of threads for parallel batch processing. "
        "If not specified (default), auto-detects CPU count and uses up to 16 threads. "
        "Set to 1 for sequential processing (no threading). "
        "More threads = faster processing but higher memory usage. "
        "Recommended: 2-8 threads for most systems. "
        "Examples: --threads 4, --threads 1 (sequential), --thread-count 8"
    )
)
@click.option(
    "--progress/--no-progress",
    default=True,
    help=(
        "Show progress information during generation. "
        "When enabled (default), displays batch progress and completion status. "
        "Use --no-progress to suppress progress output. "
        "Example: --no-progress"
    )
)
@click.option(
    "--assets",
    default=None,
    callback=parse_assets,
    help=(
        "Comma-separated list of specific assets to generate. "
        "Asset symbols are case-insensitive and will be normalized to uppercase. "
        "If --market is also provided, only assets belonging to the selected markets will be generated. "
        "Assets from other markets will show a warning and be skipped. "
        "If only --assets is provided (no --market), markets will be auto-detected from the assets. "
        "Examples: --assets BTCUSD,ETHUSD, --assets EURUSD,GBPUSD,XAUUSD, --market crypto --assets BTCUSD,ETHUSD"
    )
)
@click.version_option(version=__version__, prog_name="marketforge")
def create_cli(
    output_dir: str,
    from_ts: int,
    to_ts: int,
    market: list[MarketType],
    seed: Optional[int],
    anomalies: Optional[frozenset],
    timeframes: str,
    batch_size: int,
    threads: Optional[int],
    progress: bool,
    assets: Optional[list[str]],
) -> None:
    """
    Generate synthetic OHLCV data for backtesting and development using MarketForge.
    
    Uses pre-configured market definitions with realistic prices, volatilities,
    and correlation matrices for forex (82 pairs), crypto (53 assets), and
    stocks (73 symbols).
    
    \b
    Example usage:
    
    \b
        # Generate all markets
        python -m marketforge \\
            --output-dir ./data \\
            --from 1764543600 \\
            --to 1767221999 \\
            --seed 42 \\
            --anomalies gaps,spikes
    
    \b
        # Generate specific markets
        python -m marketforge \\
            --output-dir ./data \\
            --from 1764543600 \\
            --to 1767221999 \\
            --market forex,crypto
    
    \b
    Output structure:
        output/
        +-- forex/
        |   +-- EURUSD_m1.csv
        |   +-- EURUSD_H1.csv
        |   +-- ...
        +-- crypto/
        |   +-- BTCUSD_m1.csv
        |   +-- ...
        +-- stocks/
            +-- AAPL_m1.csv
            +-- ...
    """
    try:
        from marketforge.cli.runner import run_generation
        
        # Parse timeframes
        tf_tuple = tuple(t.strip() for t in timeframes.split(",") if t.strip())
        
        # Validate timestamps
        if from_ts >= to_ts:
            raise click.BadParameter(
                f"Start timestamp ({from_ts}) must be less than end timestamp ({to_ts})"
            )
        
        # Validate thread count if provided
        if threads is not None and threads < 1:
            raise click.BadParameter(
                f"Thread count must be >= 1, got {threads}"
            )
        
        # Run generation
        run_generation(
            output_dir=output_dir,
            from_ts=from_ts,
            to_ts=to_ts,
            markets=market,
            seed=seed,
            anomaly_types=anomalies,
            timeframes=tf_tuple,
            batch_size=batch_size,
            thread_count=threads,
            show_progress=progress,
            assets=assets,
        )
        
    except Exception as e:
        click.secho(f"Error: {e}", fg="red", err=True)
        if "--debug" in sys.argv:
            raise
        sys.exit(1)


def main() -> None:
    """Entry point for CLI."""
    create_cli()


if __name__ == "__main__":
    main()
