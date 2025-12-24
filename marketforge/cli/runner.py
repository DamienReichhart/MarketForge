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
CLI runner that orchestrates the data generation process.

Connects all components and handles the generation workflow using
pre-configured market settings and batch processing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import click

from marketforge.configs.base import MarketType
from marketforge.configs.loader import (
    ConfigRegistry,
    get_asset_market_mapping,
    filter_market_config,
)
from marketforge.config.settings import AnomalyType
from marketforge.processing.batch import (
    BatchConfig,
    generate_market_batched,
    estimate_memory_usage,
)
from marketforge.utils.time import get_timestamp_range_info


def validate_and_filter_assets(
    requested_assets: list[str],
    selected_markets: list[MarketType],
    asset_to_market: dict[str, MarketType],
) -> dict[MarketType, list[str]]:
    """
    Validate and filter assets based on selected markets.
    
    If markets are provided, validates that assets belong to selected markets
    and filters out mismatches with warnings. If only assets are provided,
    auto-detects markets for each asset.
    
    Args:
        requested_assets: List of asset symbols requested by user.
        selected_markets: List of market types selected by user (empty if auto-detect).
        asset_to_market: Mapping of asset symbols to their market types.
        
    Returns:
        Dictionary mapping MarketType to list of valid asset symbols for that market.
        
    Raises:
        ValueError: If all assets are invalid or filtered out.
    """
    # Track assets by market
    assets_by_market: dict[MarketType, list[str]] = {}
    invalid_assets: list[str] = []
    mismatched_assets: list[tuple[str, MarketType, list[MarketType]]] = []
    
    # Determine if we're in filter mode (markets provided) or auto-detect mode
    is_filter_mode = len(selected_markets) > 0
    
    # Validate each requested asset
    for asset in requested_assets:
        if asset not in asset_to_market:
            invalid_assets.append(asset)
            continue
        
        asset_market = asset_to_market[asset]
        
        if is_filter_mode:
            # Filter mode: validate asset belongs to selected markets
            if asset_market not in selected_markets:
                mismatched_assets.append((asset, asset_market, selected_markets))
                continue
        
        # Asset is valid - add to appropriate market
        if asset_market not in assets_by_market:
            assets_by_market[asset_market] = []
        assets_by_market[asset_market].append(asset)
    
    # Show warnings for invalid assets
    if invalid_assets:
        click.secho(
            f"\n⚠ Warning: {len(invalid_assets)} asset(s) not found in any market:",
            fg="yellow",
            bold=True
        )
        for asset in invalid_assets:
            click.secho(f"  - {asset}", fg="yellow")
    
    # Show warnings for mismatched assets
    if mismatched_assets:
        click.secho(
            f"\n⚠ Warning: {len(mismatched_assets)} asset(s) skipped (wrong market):",
            fg="yellow",
            bold=True
        )
        for asset, asset_market, selected in mismatched_assets:
            selected_str = ", ".join(m.value for m in selected)
            click.secho(
                f"  - {asset} belongs to {asset_market.value} market, "
                f"but {selected_str} market(s) selected",
                fg="yellow"
            )
    
    # Check if we have any valid assets left
    total_valid = sum(len(assets) for assets in assets_by_market.values())
    if total_valid == 0:
        if invalid_assets or mismatched_assets:
            raise ValueError(
                "No valid assets to generate. All requested assets were invalid or mismatched."
            )
        else:
            raise ValueError("No assets specified.")
    
    # Show summary of what will be generated
    if invalid_assets or mismatched_assets:
        click.secho(
            f"\n✓ Will generate {total_valid} valid asset(s) from {len(assets_by_market)} market(s):",
            fg="green"
        )
        for market_type, assets in assets_by_market.items():
            click.secho(f"  - {market_type.value}: {len(assets)} asset(s)", fg="green")
    
    return assets_by_market


def run_generation(
    output_dir: str,
    from_ts: int,
    to_ts: int,
    markets: list[MarketType],
    seed: Optional[int] = None,
    anomaly_types: Optional[frozenset[AnomalyType]] = None,
    timeframes: tuple[str, ...] = ("m1", "m5", "m15", "m30", "H1", "H4", "D1", "W1"),
    batch_size: int = 25,
    thread_count: Optional[int] = None,
    show_progress: bool = True,
    assets: Optional[list[str]] = None,
) -> dict[str, dict[str, Path]]:
    """
    Run the MarketForge generation pipeline.
    
    Args:
        output_dir: Base output directory.
        from_ts: Start timestamp.
        to_ts: End timestamp.
        markets: List of markets to generate.
        seed: Random seed for reproducibility.
        anomaly_types: Types of anomalies to inject.
        timeframes: Timeframes to generate.
        batch_size: Assets per batch for memory management.
        thread_count: Number of threads for parallel processing.
        show_progress: Whether to show progress.
        assets: Optional list of specific assets to generate. If provided,
                only these assets will be generated (filtered by market if
                markets are also specified).
        
    Returns:
        Nested dictionary: {market: {symbol: path}}.
    """
    # Initialize config registry
    registry = ConfigRegistry()
    
    # Handle asset filtering if assets are specified
    markets_to_process = markets
    assets_by_market: dict[MarketType, list[str]] = {}
    
    if assets:
        # Get asset-to-market mapping
        asset_to_market = get_asset_market_mapping()
        
        # Validate and filter assets
        assets_by_market = validate_and_filter_assets(
            requested_assets=assets,
            selected_markets=markets,
            asset_to_market=asset_to_market,
        )
        
        # Update markets to process based on filtered assets
        if assets_by_market:
            markets_to_process = list(assets_by_market.keys())
        else:
            # No valid assets - error already raised in validate_and_filter_assets
            raise ValueError("No valid assets to generate.")
    
    # Print header
    _print_generation_header(from_ts, to_ts, markets_to_process, seed, timeframes, output_dir)
    
    # Create batch config
    batch_config = BatchConfig(
        batch_size=batch_size,
        thread_count=thread_count,
    )
    
    # Track all output paths
    all_outputs: dict[str, dict[str, Path]] = {}
    
    # Process each market
    for market_type in markets_to_process:
        click.echo(f"\n{'=' * 60}")
        click.secho(f"Generating {market_type.value.upper()} market", fg="cyan", bold=True)
        click.echo("=" * 60)
        
        # Load market config
        market_config = registry.get_config(market_type)
        
        # Filter market config if assets are specified
        if assets and market_type in assets_by_market:
            requested_assets_for_market = assets_by_market[market_type]
            market_config = filter_market_config(market_config, requested_assets_for_market)
        
        n_batches = (market_config.n_assets + batch_size - 1) // batch_size
        click.echo(f"Assets: {market_config.n_assets}")
        click.echo(f"Batches: {n_batches}")
        
        # Show threading info
        effective_threads = batch_config.thread_count
        if effective_threads is None:
            import os
            cpu_count = os.cpu_count() or 4
            effective_threads = min(cpu_count, 16, n_batches)
        if effective_threads > 1 and n_batches > 1:
            click.echo(f"Threading: {effective_threads} threads (parallel processing)")
        else:
            click.echo(f"Threading: Sequential processing")
        
        # Estimate memory usage
        n_minutes = (to_ts - from_ts) // 60
        memory_est = estimate_memory_usage(
            n_assets=batch_size,  # Per batch
            n_minutes=n_minutes,
            n_timeframes=len(timeframes),
        )
        click.echo(f"Estimated memory per batch: {memory_est['total_mb']:.1f} MB")
        
        # Generate data
        market_outputs = generate_market_batched(
            market_config=market_config,
            start_timestamp=from_ts,
            end_timestamp=to_ts,
            output_dir=output_dir,
            seed=seed,
            anomaly_types=anomaly_types,
            timeframes=timeframes,
            batch_config=batch_config,
            show_progress=show_progress,
        )
        
        all_outputs[market_type.value] = market_outputs
        
        click.secho(
            f"[OK] {market_type.value.upper()}: {len(market_outputs)} assets generated",
            fg="green"
        )
    
    # Print summary
    _print_generation_summary(all_outputs, output_dir, timeframes)
    
    return all_outputs


def _print_generation_header(
    from_ts: int,
    to_ts: int,
    markets: list[MarketType],
    seed: Optional[int],
    timeframes: tuple[str, ...],
    output_dir: str,
) -> None:
    """Print generation header information."""
    range_info = get_timestamp_range_info(from_ts, to_ts)
    
    click.echo("\n" + "=" * 60)
    click.secho("MarketForge", fg="cyan", bold=True)
    click.echo("=" * 60)
    
    click.echo(f"\nMarkets: {', '.join(m.value for m in markets)}")
    
    click.echo(f"\nTime Range:")
    click.echo(f"  From: {range_info['start_datetime']}")
    click.echo(f"  To:   {range_info['end_datetime']}")
    click.echo(f"  Duration: {range_info['duration_days']} days ({range_info['duration_hours']} hours)")
    click.echo(f"  M1 candles: {range_info['m1_candles']:,}")
    
    if seed is not None:
        click.echo(f"\nRandom seed: {seed}")
    
    click.echo(f"\nTimeframes: {', '.join(timeframes)}")
    click.echo(f"Output directory: {output_dir}")


def _print_generation_summary(
    all_outputs: dict[str, dict[str, Path]],
    output_dir: str,
    timeframes: tuple[str, ...],
) -> None:
    """Print generation completion summary."""
    total_assets = sum(len(outputs) for outputs in all_outputs.values())
    total_files = total_assets * len(timeframes)
    
    click.echo("\n" + "=" * 60)
    click.secho("Generation Complete!", fg="green", bold=True)
    click.echo("=" * 60)
    
    click.echo(f"\nGenerated {total_files:,} CSV files for {total_assets} assets:")
    
    for market, outputs in all_outputs.items():
        click.echo(f"\n  {market}/ ({len(outputs)} assets)")
        
        # Show first few and last few
        symbols = list(outputs.keys())
        if len(symbols) <= 6:
            for symbol in symbols:
                click.echo(f"    - {symbol}")
        else:
            for symbol in symbols[:3]:
                click.echo(f"    - {symbol}")
            click.echo(f"    ... ({len(symbols) - 6} more)")
            for symbol in symbols[-3:]:
                click.echo(f"    - {symbol}")
    
    click.echo(f"\nOutput directory: {output_dir}")
    click.echo(f"Timeframes per asset: {len(timeframes)}")
