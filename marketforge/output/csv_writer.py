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
CSV output writer for OHLCV data.

Handles writing OHLCV data to CSV files with proper formatting,
directory structure, and metadata.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import os

import numpy as np
import pandas as pd

from marketforge.generators.ohlcv import OHLCVData, MultiAssetOHLCVData
from marketforge.aggregation.timeframes import (
    Timeframe,
    AggregatedData,
    TimeframeAggregator,
)


@dataclass
class CSVWriterConfig:
    """
    Configuration for CSV writer.
    
    Attributes:
        output_dir: Base output directory.
        decimal_places: Number of decimal places for prices.
        volume_decimal_places: Number of decimal places for volume.
        include_header: Whether to include column headers.
        timestamp_format: Format for timestamps ("unix" or "iso").
        create_subdirs: Whether to create subdirectories per asset.
        file_pattern: Pattern for filenames ({symbol}, {timeframe} placeholders).
    """
    output_dir: str = "./output"
    decimal_places: int = 8
    volume_decimal_places: int = 4
    include_header: bool = True
    timestamp_format: str = "unix"  # "unix" or "iso"
    create_subdirs: bool = False
    file_pattern: str = "{symbol}_{timeframe}.csv"


class CSVWriter:
    """
    Writer for exporting OHLCV data to CSV files.
    
    Handles:
    - Proper decimal formatting for prices and volumes
    - Directory creation
    - Multiple timeframes per asset
    - Consistent file naming
    
    Output format:
        timestamp,open,high,low,close,volume
        1704067200,50000.00000000,50125.50000000,49875.25000000,50050.75000000,1250.5000
        
    Attributes:
        config: CSV writer configuration.
        
    Example:
        >>> writer = CSVWriter(CSVWriterConfig(output_dir="./data"))
        >>> writer.write_aggregated(aggregated_data)
        # Creates: ./data/BTC_m1.csv, ./data/BTC_H1.csv, etc.
    """
    
    def __init__(self, config: Optional[CSVWriterConfig] = None) -> None:
        """
        Initialize CSV writer.
        
        Args:
            config: Writer configuration. Uses defaults if None.
        """
        self._config = config or CSVWriterConfig()
        self._ensure_output_dir()
    
    @property
    def config(self) -> CSVWriterConfig:
        """Return writer configuration."""
        return self._config
    
    @property
    def output_dir(self) -> Path:
        """Return output directory path."""
        return Path(self._config.output_dir)
    
    def _ensure_output_dir(self) -> None:
        """Create output directory if it doesn't exist."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def _format_filename(self, symbol: str, timeframe: Timeframe) -> str:
        """Generate filename from pattern."""
        return self._config.file_pattern.format(
            symbol=symbol,
            timeframe=timeframe.name,
        )
    
    def _get_output_path(self, symbol: str, timeframe: Timeframe) -> Path:
        """Get full output path for a file."""
        filename = self._format_filename(symbol, timeframe)
        
        if self._config.create_subdirs:
            subdir = self.output_dir / symbol
            subdir.mkdir(exist_ok=True)
            return subdir / filename
        
        return self.output_dir / filename
    
    def _format_price(self, value: float) -> str:
        """Format price value with configured decimal places."""
        return f"{value:.{self._config.decimal_places}f}"
    
    def _format_volume(self, value: float) -> str:
        """Format volume value with configured decimal places."""
        return f"{value:.{self._config.volume_decimal_places}f}"
    
    def write_ohlcv(
        self,
        data: OHLCVData,
        timeframe: Timeframe = Timeframe.m1
    ) -> Path:
        """
        Write single OHLCV dataset to CSV.
        
        Args:
            data: OHLCV data to write.
            timeframe: Timeframe for filename.
            
        Returns:
            Path to written file.
        """
        output_path = self._get_output_path(data.symbol, timeframe)
        
        # Create DataFrame
        df = self._create_dataframe(data)
        
        # Write to CSV
        df.to_csv(
            output_path,
            index=False,
            header=self._config.include_header,
        )
        
        return output_path
    
    def write_aggregated(
        self,
        data: AggregatedData
    ) -> dict[Timeframe, Path]:
        """
        Write aggregated data (all timeframes) to CSV files.
        
        Args:
            data: Aggregated OHLCV data with multiple timeframes.
            
        Returns:
            Dictionary mapping timeframe to output path.
        """
        paths = {}
        
        for tf, ohlcv in data.timeframes.items():
            path = self.write_ohlcv(ohlcv, tf)
            paths[tf] = path
        
        return paths
    
    def write_multi_asset(
        self,
        data: MultiAssetOHLCVData,
        timeframes: Optional[list[Timeframe]] = None
    ) -> dict[str, dict[Timeframe, Path]]:
        """
        Write multi-asset OHLCV data to CSV files.
        
        Creates one file per asset per timeframe.
        
        Args:
            data: Multi-asset OHLCV data.
            timeframes: Timeframes to aggregate and write. 
                       If None, writes only m1.
                       
        Returns:
            Nested dictionary: {symbol: {timeframe: path}}.
        """
        aggregator = TimeframeAggregator(
            source_timeframe=Timeframe.m1,
            target_timeframes=timeframes,
        )
        
        all_paths = {}
        
        for symbol, ohlcv in data.assets.items():
            aggregated = aggregator.aggregate(ohlcv)
            paths = self.write_aggregated(aggregated)
            all_paths[symbol] = paths
        
        return all_paths
    
    def write_multi_asset_aggregated(
        self,
        data: dict[str, AggregatedData]
    ) -> dict[str, dict[Timeframe, Path]]:
        """
        Write pre-aggregated multi-asset data.
        
        Args:
            data: Dictionary mapping symbol to AggregatedData.
            
        Returns:
            Nested dictionary: {symbol: {timeframe: path}}.
        """
        all_paths = {}
        
        for symbol, aggregated in data.items():
            paths = self.write_aggregated(aggregated)
            all_paths[symbol] = paths
        
        return all_paths
    
    def _create_dataframe(self, data: OHLCVData) -> pd.DataFrame:
        """
        Create formatted DataFrame from OHLCV data.
        
        Args:
            data: OHLCV data.
            
        Returns:
            Formatted DataFrame.
        """
        # Format timestamps
        if self._config.timestamp_format == "iso":
            timestamps = pd.to_datetime(
                data.timestamps, unit="s", utc=True
            ).strftime("%Y-%m-%dT%H:%M:%SZ")
        else:
            timestamps = data.timestamps
        
        # Create DataFrame with formatted values
        df = pd.DataFrame({
            "timestamp": timestamps,
            "open": [self._format_price(v) for v in data.open],
            "high": [self._format_price(v) for v in data.high],
            "low": [self._format_price(v) for v in data.low],
            "close": [self._format_price(v) for v in data.close],
            "volume": [self._format_volume(v) for v in data.volume],
        })
        
        return df


def write_ohlcv_simple(
    data: OHLCVData,
    output_path: str | Path,
    decimal_places: int = 8
) -> None:
    """
    Simple function to write OHLCV data to a single CSV file.
    
    Args:
        data: OHLCV data to write.
        output_path: Path for output file.
        decimal_places: Decimal places for formatting.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    df = pd.DataFrame({
        "timestamp": data.timestamps,
        "open": np.round(data.open, decimal_places),
        "high": np.round(data.high, decimal_places),
        "low": np.round(data.low, decimal_places),
        "close": np.round(data.close, decimal_places),
        "volume": np.round(data.volume, 4),
    })
    
    df.to_csv(output_path, index=False)


class CSVWriterWithProgress:
    """
    CSV writer with progress callback for large datasets.
    """
    
    def __init__(
        self,
        config: Optional[CSVWriterConfig] = None,
        progress_callback: Optional[callable] = None
    ) -> None:
        """
        Initialize writer with progress tracking.
        
        Args:
            config: Writer configuration.
            progress_callback: Called with (current, total) for each file.
        """
        self._writer = CSVWriter(config)
        self._progress_callback = progress_callback
    
    def write_multi_asset_aggregated(
        self,
        data: dict[str, AggregatedData]
    ) -> dict[str, dict[Timeframe, Path]]:
        """
        Write multi-asset data with progress tracking.
        
        Args:
            data: Dictionary mapping symbol to AggregatedData.
            
        Returns:
            Nested dictionary of output paths.
        """
        # Calculate total files
        total = sum(len(agg.timeframes) for agg in data.values())
        current = 0
        
        all_paths = {}
        
        for symbol, aggregated in data.items():
            symbol_paths = {}
            
            for tf, ohlcv in aggregated.timeframes.items():
                path = self._writer.write_ohlcv(ohlcv, tf)
                symbol_paths[tf] = path
                
                current += 1
                if self._progress_callback:
                    self._progress_callback(current, total)
            
            all_paths[symbol] = symbol_paths
        
        return all_paths

