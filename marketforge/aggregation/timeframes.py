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
Timeframe aggregation for OHLCV data.

Aggregates minute-level (m1) OHLCV data to higher timeframes
using standard OHLCV aggregation rules.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional
import numpy as np
import pandas as pd

from marketforge.generators.ohlcv import OHLCVData, MultiAssetOHLCVData


class Timeframe(Enum):
    """
    Supported timeframes with their minute equivalents.
    
    Naming convention:
    - m = minutes (m1, m5, m15, m30)
    - H = hours (H1, H4)
    - D = days (D1)
    - W = weeks (W1)
    - M = months (M1)
    """
    m1 = 1
    m5 = 5
    m15 = 15
    m30 = 30
    H1 = 60
    H4 = 240
    D1 = 1440        # 24 * 60
    W1 = 10080       # 7 * 24 * 60
    M1 = 43200       # 30 * 24 * 60 (approximate)
    
    @property
    def minutes(self) -> int:
        """Return timeframe in minutes."""
        return self.value
    
    @property
    def seconds(self) -> int:
        """Return timeframe in seconds."""
        return self.value * 60
    
    @classmethod
    def from_string(cls, s: str) -> "Timeframe":
        """
        Parse timeframe from string.
        
        Args:
            s: Timeframe string (e.g., "m1", "H4", "D1").
            
        Returns:
            Corresponding Timeframe enum.
            
        Raises:
            ValueError: If string doesn't match any timeframe.
        """
        try:
            return cls[s]
        except KeyError:
            raise ValueError(f"Unknown timeframe: {s}. Valid: {[t.name for t in cls]}")
    
    @classmethod
    def all_timeframes(cls) -> list["Timeframe"]:
        """Return list of all timeframes in ascending order."""
        return sorted(cls, key=lambda t: t.value)


@dataclass
class AggregatedData:
    """
    Container for aggregated OHLCV data across multiple timeframes.
    
    Attributes:
        symbol: Asset symbol.
        timeframes: Dictionary mapping timeframe to OHLCVData.
    """
    symbol: str
    timeframes: dict[Timeframe, OHLCVData]
    
    def __getitem__(self, tf: Timeframe | str) -> OHLCVData:
        """Get data for a specific timeframe."""
        if isinstance(tf, str):
            tf = Timeframe.from_string(tf)
        return self.timeframes[tf]
    
    @property
    def available_timeframes(self) -> list[Timeframe]:
        """Return list of available timeframes."""
        return list(self.timeframes.keys())


class TimeframeAggregator:
    """
    Aggregator for converting minute data to higher timeframes.
    
    Implements standard OHLCV aggregation:
    - Open: First candle's open
    - High: Maximum of all highs
    - Low: Minimum of all lows
    - Close: Last candle's close
    - Volume: Sum of all volumes
    
    Supports all standard timeframes from m1 to M1 (monthly).
    
    Attributes:
        source_timeframe: Base timeframe of input data.
        target_timeframes: List of timeframes to generate.
        
    Example:
        >>> aggregator = TimeframeAggregator()
        >>> aggregated = aggregator.aggregate(m1_data)
        >>> h1_data = aggregated[Timeframe.H1]
    """
    
    # Default timeframes to generate
    DEFAULT_TIMEFRAMES = [
        Timeframe.m1,
        Timeframe.m5,
        Timeframe.m15,
        Timeframe.m30,
        Timeframe.H1,
        Timeframe.H4,
        Timeframe.D1,
        Timeframe.W1,
        Timeframe.M1,
    ]
    
    def __init__(
        self,
        source_timeframe: Timeframe = Timeframe.m1,
        target_timeframes: Optional[list[Timeframe]] = None
    ) -> None:
        """
        Initialize the timeframe aggregator.
        
        Args:
            source_timeframe: Timeframe of input data (default m1).
            target_timeframes: Timeframes to generate. Default is all.
        """
        self._source_tf = source_timeframe
        self._target_tfs = target_timeframes or self.DEFAULT_TIMEFRAMES
        
        # Filter out timeframes smaller than source
        self._target_tfs = [
            tf for tf in self._target_tfs
            if tf.minutes >= source_timeframe.minutes
        ]
    
    @property
    def source_timeframe(self) -> Timeframe:
        """Return source timeframe."""
        return self._source_tf
    
    @property
    def target_timeframes(self) -> list[Timeframe]:
        """Return list of target timeframes."""
        return self._target_tfs
    
    def aggregate(self, data: OHLCVData) -> AggregatedData:
        """
        Aggregate OHLCV data to all target timeframes.
        
        Args:
            data: Source OHLCV data at source timeframe.
            
        Returns:
            AggregatedData containing all timeframes.
        """
        timeframes = {}
        
        for tf in self._target_tfs:
            if tf == self._source_tf:
                # No aggregation needed
                timeframes[tf] = data
            else:
                timeframes[tf] = self._aggregate_to_timeframe(data, tf)
        
        return AggregatedData(symbol=data.symbol, timeframes=timeframes)
    
    def aggregate_multi_asset(
        self,
        data: MultiAssetOHLCVData
    ) -> dict[str, AggregatedData]:
        """
        Aggregate multi-asset OHLCV data to all timeframes.
        
        Args:
            data: Multi-asset OHLCV data.
            
        Returns:
            Dictionary mapping symbol to AggregatedData.
        """
        result = {}
        for symbol, ohlcv in data.assets.items():
            result[symbol] = self.aggregate(ohlcv)
        return result
    
    def _aggregate_to_timeframe(
        self,
        data: OHLCVData,
        target_tf: Timeframe
    ) -> OHLCVData:
        """
        Aggregate data to a specific target timeframe.
        
        Args:
            data: Source OHLCV data.
            target_tf: Target timeframe.
            
        Returns:
            Aggregated OHLCVData.
        """
        # Calculate aggregation ratio
        ratio = target_tf.minutes // self._source_tf.minutes
        
        if ratio <= 1:
            return data
        
        n_source = len(data)
        n_target = n_source // ratio
        
        if n_target == 0:
            raise ValueError(
                f"Not enough data to aggregate from {self._source_tf.name} "
                f"to {target_tf.name}. Have {n_source} candles, need at least {ratio}."
            )
        
        # Truncate to complete periods
        n_used = n_target * ratio
        
        # Aggregate using numpy operations for efficiency
        timestamps = data.timestamps[:n_used:ratio].copy()
        
        # Reshape for aggregation
        open_reshaped = data.open[:n_used].reshape(n_target, ratio)
        high_reshaped = data.high[:n_used].reshape(n_target, ratio)
        low_reshaped = data.low[:n_used].reshape(n_target, ratio)
        close_reshaped = data.close[:n_used].reshape(n_target, ratio)
        volume_reshaped = data.volume[:n_used].reshape(n_target, ratio)
        
        # Apply aggregation rules
        open_prices = open_reshaped[:, 0]           # First open
        high_prices = high_reshaped.max(axis=1)     # Max high
        low_prices = low_reshaped.min(axis=1)       # Min low
        close_prices = close_reshaped[:, -1]        # Last close
        volumes = volume_reshaped.sum(axis=1)       # Sum volume
        
        return OHLCVData(
            symbol=data.symbol,
            timestamps=timestamps,
            open=open_prices,
            high=high_prices,
            low=low_prices,
            close=close_prices,
            volume=volumes,
        )
    
    def aggregate_single_timeframe(
        self,
        data: OHLCVData,
        target_tf: Timeframe
    ) -> OHLCVData:
        """
        Aggregate to a single target timeframe.
        
        Convenience method for aggregating to just one timeframe.
        
        Args:
            data: Source OHLCV data.
            target_tf: Target timeframe.
            
        Returns:
            Aggregated OHLCVData.
        """
        return self._aggregate_to_timeframe(data, target_tf)


def aggregate_ohlcv_pandas(
    df: pd.DataFrame,
    target_minutes: int,
    timestamp_col: str = "timestamp"
) -> pd.DataFrame:
    """
    Aggregate OHLCV DataFrame using pandas.
    
    Alternative implementation using pandas for flexibility.
    
    Args:
        df: DataFrame with OHLCV columns.
        target_minutes: Target timeframe in minutes.
        timestamp_col: Name of timestamp column.
        
    Returns:
        Aggregated DataFrame.
    """
    # Convert timestamp to datetime for resampling
    df = df.copy()
    df["datetime"] = pd.to_datetime(df[timestamp_col], unit="s", utc=True)
    df = df.set_index("datetime")
    
    # Resample rule
    rule = f"{target_minutes}min"
    
    # Aggregate
    agg_dict = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }
    
    resampled = df.resample(rule).agg(agg_dict).dropna()
    
    # Convert back to timestamp
    resampled[timestamp_col] = resampled.index.astype(np.int64) // 10**9
    resampled = resampled.reset_index(drop=True)
    
    return resampled[[timestamp_col, "open", "high", "low", "close", "volume"]]


def parse_timeframe_list(timeframe_str: str) -> list[Timeframe]:
    """
    Parse comma-separated timeframe string.
    
    Args:
        timeframe_str: Comma-separated timeframes (e.g., "m1,m5,H1,D1").
        
    Returns:
        List of Timeframe enums.
    """
    parts = [p.strip() for p in timeframe_str.split(",")]
    return [Timeframe.from_string(p) for p in parts if p]


def get_standard_timeframes() -> list[Timeframe]:
    """Return list of standard timeframes."""
    return TimeframeAggregator.DEFAULT_TIMEFRAMES.copy()

