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
Batch processing manager for memory-efficient generation.

Processes large numbers of assets in batches to manage memory usage
while maintaining correlation structure within batches.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Callable
import gc
import os
from concurrent.futures import ThreadPoolExecutor, Future, as_completed
from threading import Lock

import click
import numpy as np
from tqdm import tqdm

from marketforge.configs.base import MarketConfig, MarketType
from marketforge.configs.loader import (
    ConfigRegistry,
    market_config_to_generator_config,
)
from marketforge.config.settings import AnomalyType
from marketforge.core.returns import ReturnGenerator
from marketforge.generators.ohlcv import OHLCVBuilder
from marketforge.generators.volume import VolumeGenerator
from marketforge.generators.anomalies import AnomalyInjector
from marketforge.aggregation.timeframes import TimeframeAggregator, Timeframe
from marketforge.output.csv_writer import CSVWriter, CSVWriterConfig
from marketforge.utils.random import RandomState


@dataclass
class BatchConfig:
    """
    Configuration for batch processing.
    
    Attributes:
        batch_size: Number of assets to process per batch.
        overlap_assets: Number of assets to overlap between batches for continuity.
        gc_between_batches: Whether to run garbage collection between batches.
        thread_count: Number of threads to use for parallel batch processing.
                      If None, uses CPU count. If 1, runs sequentially.
    """
    batch_size: int = 25
    overlap_assets: int = 0
    gc_between_batches: bool = True
    thread_count: Optional[int] = None


class BatchManager:
    """
    Manager for batch processing of large asset sets.
    
    Handles:
    - Splitting assets into manageable batches
    - Maintaining correlation structure within batches
    - Memory management through explicit cleanup
    - Progress tracking across batches
    
    Attributes:
        market_config: Market configuration with all assets.
        batch_config: Batch processing settings.
        
    Example:
        >>> manager = BatchManager(market_config, BatchConfig(batch_size=30))
        >>> for batch in manager.get_batches():
        >>>     process_batch(batch)
    """
    
    def __init__(
        self,
        market_config: MarketConfig,
        batch_config: Optional[BatchConfig] = None,
    ) -> None:
        """
        Initialize batch manager.
        
        Args:
            market_config: Market configuration with all assets.
            batch_config: Batch processing settings.
        """
        self._market_config = market_config
        self._batch_config = batch_config or BatchConfig()
        self._batches = self._create_batches()
    
    @property
    def market_config(self) -> MarketConfig:
        """Return market configuration."""
        return self._market_config
    
    @property
    def batch_config(self) -> BatchConfig:
        """Return batch configuration."""
        return self._batch_config
    
    @property
    def n_batches(self) -> int:
        """Return number of batches."""
        return len(self._batches)
    
    @property
    def n_assets(self) -> int:
        """Return total number of assets."""
        return self._market_config.n_assets
    
    def _create_batches(self) -> list[list[str]]:
        """Create list of symbol batches."""
        symbols = self._market_config.symbols
        batch_size = self._batch_config.batch_size
        
        batches = []
        for i in range(0, len(symbols), batch_size):
            batch = symbols[i:i + batch_size]
            batches.append(batch)
        
        return batches
    
    def get_batches(self) -> list[list[str]]:
        """Return list of symbol batches."""
        return self._batches
    
    def get_batch(self, index: int) -> list[str]:
        """Get a specific batch by index."""
        return self._batches[index]
    
    def get_batch_correlation_matrix(self, batch_symbols: list[str]) -> np.ndarray:
        """
        Get correlation submatrix for a batch.
        
        Args:
            batch_symbols: List of symbols in the batch.
            
        Returns:
            Correlation matrix for the batch.
        """
        return self._market_config.get_correlation_submatrix(batch_symbols)


def generate_market_batched(
    market_config: MarketConfig,
    start_timestamp: int,
    end_timestamp: int,
    output_dir: str,
    seed: Optional[int] = None,
    anomaly_types: Optional[frozenset[AnomalyType]] = None,
    timeframes: tuple[str, ...] = ("m1", "m5", "m15", "m30", "H1", "H4", "D1", "W1"),
    batch_config: Optional[BatchConfig] = None,
    show_progress: bool = True,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> dict[str, Path]:
    """
    Generate OHLCV data for a market using batch processing.
    
    Supports parallel processing via threading when thread_count > 1.
    Each thread processes one batch independently.
    
    Args:
        market_config: Market configuration with all assets.
        start_timestamp: Start timestamp for generation.
        end_timestamp: End timestamp for generation.
        output_dir: Base output directory.
        seed: Random seed for reproducibility.
        anomaly_types: Types of anomalies to inject.
        timeframes: Timeframes to generate.
        batch_config: Batch processing settings.
        show_progress: Whether to show progress.
        progress_callback: Optional callback for progress updates.
        
    Returns:
        Dictionary mapping symbol to primary output path.
        
    Raises:
        RuntimeError: If any batch fails during parallel processing.
    """
    batch_config = batch_config or BatchConfig()
    manager = BatchManager(market_config, batch_config)
    
    # Create market subdirectory (thread-safe with exist_ok=True)
    market_dir = Path(output_dir) / market_config.market_type.value
    market_dir.mkdir(parents=True, exist_ok=True)
    
    # Parse timeframes
    tf_list = [Timeframe.from_string(tf) for tf in timeframes]
    
    # Determine thread count
    thread_count = _determine_thread_count(batch_config.thread_count, manager.n_batches)
    
    # Process batches
    if thread_count == 1:
        # Sequential processing (original behavior)
        return _generate_market_sequential(
            manager=manager,
            market_dir=market_dir,
            start_timestamp=start_timestamp,
            end_timestamp=end_timestamp,
            seed=seed,
            anomaly_types=anomaly_types,
            timeframes=timeframes,
            tf_list=tf_list,
            batch_config=batch_config,
            show_progress=show_progress,
            progress_callback=progress_callback,
        )
    else:
        # Parallel processing with threading
        return _generate_market_parallel(
            manager=manager,
            market_dir=market_dir,
            start_timestamp=start_timestamp,
            end_timestamp=end_timestamp,
            seed=seed,
            anomaly_types=anomaly_types,
            timeframes=timeframes,
            tf_list=tf_list,
            batch_config=batch_config,
            thread_count=thread_count,
            show_progress=show_progress,
            progress_callback=progress_callback,
        )


def _determine_thread_count(
    requested: Optional[int],
    n_batches: int
) -> int:
    """
    Determine optimal thread count for batch processing.
    
    Args:
        requested: User-requested thread count (None = auto).
        n_batches: Total number of batches to process.
        
    Returns:
        Thread count to use (at least 1, at most n_batches).
    """
    if requested is not None:
        # User specified thread count
        if requested < 1:
            raise ValueError(f"thread_count must be >= 1, got {requested}")
        # Cap at number of batches (no point having more threads than batches)
        return min(requested, n_batches)
    
    # Auto-detect: use CPU count, but cap at reasonable maximum
    cpu_count = os.cpu_count() or 4
    max_threads = min(cpu_count, 16, n_batches)  # Cap at 16 to avoid resource exhaustion
    return max(1, max_threads)


def _generate_market_sequential(
    manager: BatchManager,
    market_dir: Path,
    start_timestamp: int,
    end_timestamp: int,
    seed: Optional[int],
    anomaly_types: Optional[frozenset[AnomalyType]],
    timeframes: tuple[str, ...],
    tf_list: list[Timeframe],
    batch_config: BatchConfig,
    show_progress: bool,
    progress_callback: Optional[Callable[[int, int, str], None]],
) -> dict[str, Path]:
    """
    Generate market data sequentially (one batch at a time).
    
    This is the original implementation, kept for when thread_count=1
    or for debugging purposes.
    """
    # Initialize writer (shared across batches in sequential mode)
    writer_config = CSVWriterConfig(
        output_dir=str(market_dir),
        decimal_places=8,
        volume_decimal_places=4,
    )
    writer = CSVWriter(writer_config)
    
    # Track output paths
    output_paths: dict[str, Path] = {}
    total_assets = manager.n_assets
    processed_assets = 0
    
    # Initialize progress bar
    pbar = None
    if show_progress:
        pbar = tqdm(
            total=total_assets,
            unit="asset",
            unit_scale=False,
            desc="  Processing",
            leave=True,
            ncols=100,
            bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]"
        )
    
    try:
        for batch_idx, batch_symbols in enumerate(manager.get_batches()):
            batch_size = len(batch_symbols)
            
            if show_progress and pbar:
                pbar.set_description(
                    f"  Batch {batch_idx + 1}/{manager.n_batches}: "
                    f"{batch_symbols[0]}...{batch_symbols[-1]}"
                )
            
            # Create generator config for this batch
            gen_config = market_config_to_generator_config(
                market_config=manager.market_config,
                start_timestamp=start_timestamp,
                end_timestamp=end_timestamp,
                seed=seed + batch_idx if seed is not None else None,
                anomaly_types=anomaly_types,
                timeframes=timeframes,
                output_dir=str(market_dir),
                show_progress=False,
                batch_symbols=batch_symbols,
            )
            
            # Generate data for batch
            batch_paths = _generate_batch(
                gen_config=gen_config,
                writer=writer,
                tf_list=tf_list,
                anomaly_types=anomaly_types,
            )
            
            output_paths.update(batch_paths)
            processed_assets += batch_size
            
            # Update progress bar
            if show_progress and pbar:
                pbar.update(batch_size)
            
            if progress_callback:
                progress_callback(processed_assets, total_assets, batch_symbols[-1])
            
            # Cleanup between batches
            if batch_config.gc_between_batches:
                gc.collect()
    finally:
        if pbar:
            pbar.close()
    
    return output_paths


def _generate_market_parallel(
    manager: BatchManager,
    market_dir: Path,
    start_timestamp: int,
    end_timestamp: int,
    seed: Optional[int],
    anomaly_types: Optional[frozenset[AnomalyType]],
    timeframes: tuple[str, ...],
    tf_list: list[Timeframe],
    batch_config: BatchConfig,
    thread_count: int,
    show_progress: bool,
    progress_callback: Optional[Callable[[int, int, str], None]],
) -> dict[str, Path]:
    """
    Generate market data in parallel using ThreadPoolExecutor.
    
    Each thread processes one batch independently with its own:
    - RandomState (with unique seed)
    - CSVWriter instance (thread-safe)
    - Generator instances
    
    Args:
        manager: Batch manager with all batches.
        market_dir: Output directory for this market.
        start_timestamp: Start timestamp.
        end_timestamp: End timestamp.
        seed: Base random seed.
        anomaly_types: Anomaly types to inject.
        timeframes: Timeframes to generate.
        tf_list: Parsed timeframe list.
        batch_config: Batch configuration.
        thread_count: Number of threads to use.
        show_progress: Whether to show progress.
        progress_callback: Optional progress callback.
        
    Returns:
        Dictionary mapping symbol to primary output path.
        
    Raises:
        RuntimeError: If any batch fails during processing.
    """
    batches = manager.get_batches()
    total_assets = manager.n_assets
    
    # Thread-safe progress tracking
    progress_lock = Lock()
    processed_assets = 0
    output_paths: dict[str, Path] = {}
    errors: list[tuple[int, Exception]] = []
    
    # Initialize thread-safe progress bar
    pbar = None
    if show_progress:
        pbar = tqdm(
            total=total_assets,
            unit="asset",
            unit_scale=False,
            desc="  Processing",
            leave=True,
            ncols=100,
            bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]"
        )
    
    def process_batch(batch_idx: int, batch_symbols: list[str]) -> tuple[int, dict[str, Path]]:
        """
        Process a single batch in a thread.
        
        Returns:
            Tuple of (batch_idx, output_paths_dict).
        """
        nonlocal processed_assets
        
        try:
            # Each thread gets its own CSVWriter instance (thread-safe)
            writer_config = CSVWriterConfig(
                output_dir=str(market_dir),
                decimal_places=8,
                volume_decimal_places=4,
            )
            writer = CSVWriter(writer_config)
            
            # Create generator config for this batch
            gen_config = market_config_to_generator_config(
                market_config=manager.market_config,
                start_timestamp=start_timestamp,
                end_timestamp=end_timestamp,
                seed=seed + batch_idx if seed is not None else None,
                anomaly_types=anomaly_types,
                timeframes=timeframes,
                output_dir=str(market_dir),
                show_progress=False,
                batch_symbols=batch_symbols,
            )
            
            # Generate data for batch
            batch_paths = _generate_batch(
                gen_config=gen_config,
                writer=writer,
                tf_list=tf_list,
                anomaly_types=anomaly_types,
            )
            
            # Thread-safe progress update
            batch_size = len(batch_symbols)
            with progress_lock:
                processed_assets += batch_size
                if show_progress and pbar:
                    # Update progress bar (tqdm is thread-safe)
                    pbar.update(batch_size)
                    # Update description with current batch info
                    pbar.set_description(
                        f"  Batch {batch_idx + 1}/{len(batches)}: "
                        f"{batch_symbols[0]}...{batch_symbols[-1]}"
                    )
                if progress_callback:
                    progress_callback(processed_assets, total_assets, batch_symbols[-1])
            
            # Cleanup (each thread manages its own memory)
            if batch_config.gc_between_batches:
                gc.collect()
            
            return batch_idx, batch_paths
            
        except Exception as e:
            # Collect error for reporting
            with progress_lock:
                errors.append((batch_idx, e))
            raise  # Re-raise to be caught by Future
    
    try:
        # Process batches in parallel
        with ThreadPoolExecutor(max_workers=thread_count, thread_name_prefix="BatchWorker") as executor:
            # Submit all batch tasks
            future_to_batch: dict[Future, tuple[int, list[str]]] = {}
            for batch_idx, batch_symbols in enumerate(batches):
                future = executor.submit(process_batch, batch_idx, batch_symbols)
                future_to_batch[future] = (batch_idx, batch_symbols)
            
            # Collect results as they complete
            for future in as_completed(future_to_batch):
                batch_idx, batch_symbols = future_to_batch[future]
                try:
                    _, batch_paths = future.result()
                    output_paths.update(batch_paths)
                except Exception as e:
                    # Error already collected in process_batch
                    if show_progress:
                        click.secho(
                            f"  ERROR in batch {batch_idx + 1}: {e}",
                            fg="red",
                            err=True
                        )
    finally:
        if pbar:
            pbar.close()
    
    # Report any errors
    if errors:
        error_msg = f"Failed to process {len(errors)} batch(es):\n"
        for batch_idx, error in errors:
            error_msg += f"  Batch {batch_idx + 1}: {type(error).__name__}: {error}\n"
        raise RuntimeError(error_msg)
    
    return output_paths


def _generate_batch(
    gen_config,
    writer: CSVWriter,
    tf_list: list[Timeframe],
    anomaly_types: Optional[frozenset[AnomalyType]],
) -> dict[str, Path]:
    """
    Generate OHLCV data for a single batch.
    
    Args:
        gen_config: Generator configuration for the batch.
        writer: CSV writer instance.
        tf_list: List of timeframes to generate.
        anomaly_types: Types of anomalies to inject.
        
    Returns:
        Dictionary mapping symbol to m1 output path.
    """
    rng = RandomState(gen_config.seed)
    
    # Generate returns
    return_generator = ReturnGenerator(gen_config)
    return_result = return_generator.generate(rng)
    
    # Build OHLCV
    volume_generator = VolumeGenerator(gen_config)
    ohlcv_builder = OHLCVBuilder(gen_config, volume_generator)
    ohlcv_data = ohlcv_builder.build(rng, return_result)
    
    # Inject anomalies if configured
    if anomaly_types and gen_config.anomaly_config.types:
        injector = AnomalyInjector(gen_config.anomaly_config, gen_config.market_type)
        ohlcv_data, _ = injector.inject_multi_asset(rng, ohlcv_data)
    
    # Aggregate timeframes
    aggregator = TimeframeAggregator(
        source_timeframe=Timeframe.m1,
        target_timeframes=tf_list,
    )
    aggregated_data = aggregator.aggregate_multi_asset(ohlcv_data)
    
    # Write to CSV
    output_paths: dict[str, Path] = {}
    
    for symbol, agg_data in aggregated_data.items():
        paths = writer.write_aggregated(agg_data)
        # Store the m1 path as the primary path
        if Timeframe.m1 in paths:
            output_paths[symbol] = paths[Timeframe.m1]
        elif paths:
            output_paths[symbol] = list(paths.values())[0]
    
    return output_paths


def estimate_memory_usage(
    n_assets: int,
    n_minutes: int,
    n_timeframes: int = 9,
) -> dict[str, float]:
    """
    Estimate memory usage for generation.
    
    Args:
        n_assets: Number of assets to generate.
        n_minutes: Number of minute candles.
        n_timeframes: Number of timeframes to generate.
        
    Returns:
        Dictionary with memory estimates in MB.
    """
    # Estimate bytes per value (float64 = 8 bytes)
    bytes_per_value = 8
    
    # OHLCV = 6 columns (timestamp, O, H, L, C, V)
    ohlcv_columns = 6
    
    # Per-asset memory for m1 data
    m1_per_asset = n_minutes * ohlcv_columns * bytes_per_value
    
    # Higher timeframes (rough estimate: ~20% of m1)
    higher_tf_per_asset = m1_per_asset * 0.2 * (n_timeframes - 1)
    
    # Returns, volatilities, regime data
    intermediate_per_asset = n_minutes * 3 * bytes_per_value
    
    # Correlation matrix
    correlation_matrix = n_assets * n_assets * bytes_per_value
    
    # Total per asset
    total_per_asset = m1_per_asset + higher_tf_per_asset + intermediate_per_asset
    
    # Total for all assets
    total = total_per_asset * n_assets + correlation_matrix
    
    # Convert to MB
    mb = 1024 * 1024
    
    return {
        "m1_data_mb": (m1_per_asset * n_assets) / mb,
        "higher_tf_mb": (higher_tf_per_asset * n_assets) / mb,
        "intermediate_mb": (intermediate_per_asset * n_assets) / mb,
        "correlation_mb": correlation_matrix / mb,
        "total_mb": total / mb,
        "recommended_batch_size": max(10, min(50, int(2000 / (total_per_asset / mb)))),
    }

