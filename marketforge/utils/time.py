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
Timestamp and datetime utilities for MarketForge.

Provides functions for converting between Unix timestamps and datetime objects,
as well as generating sequences of timestamps at minute intervals.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Iterator
import numpy as np


def timestamp_to_datetime(timestamp: int | float) -> datetime:
    """
    Convert Unix timestamp to timezone-aware UTC datetime.
    
    Args:
        timestamp: Unix timestamp in seconds.
        
    Returns:
        Timezone-aware datetime in UTC.
        
    Example:
        >>> dt = timestamp_to_datetime(1704067200)
        >>> dt.isoformat()
        '2024-01-01T00:00:00+00:00'
    """
    return datetime.fromtimestamp(timestamp, tz=timezone.utc)


def datetime_to_timestamp(dt: datetime) -> int:
    """
    Convert datetime to Unix timestamp in seconds.
    
    Args:
        dt: Datetime object. If naive, assumes UTC.
        
    Returns:
        Unix timestamp in seconds.
        
    Example:
        >>> dt = datetime(2024, 1, 1, tzinfo=timezone.utc)
        >>> datetime_to_timestamp(dt)
        1704067200
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def generate_minute_timestamps(
    start_timestamp: int,
    end_timestamp: int,
    interval_seconds: int = 60
) -> np.ndarray:
    """
    Generate array of timestamps at regular intervals.
    
    Args:
        start_timestamp: Start Unix timestamp (inclusive).
        end_timestamp: End Unix timestamp (exclusive).
        interval_seconds: Interval between timestamps in seconds.
        
    Returns:
        Numpy array of timestamps.
        
    Example:
        >>> timestamps = generate_minute_timestamps(0, 300, 60)
        >>> list(timestamps)
        [0, 60, 120, 180, 240]
    """
    # Align to interval boundaries
    aligned_start = (start_timestamp // interval_seconds) * interval_seconds
    
    return np.arange(aligned_start, end_timestamp, interval_seconds, dtype=np.int64)


def iter_minute_timestamps(
    start_timestamp: int,
    end_timestamp: int,
    interval_seconds: int = 60
) -> Iterator[int]:
    """
    Iterate over timestamps at regular intervals (memory-efficient).
    
    Args:
        start_timestamp: Start Unix timestamp (inclusive).
        end_timestamp: End Unix timestamp (exclusive).
        interval_seconds: Interval between timestamps in seconds.
        
    Yields:
        Unix timestamps at each interval.
    """
    aligned_start = (start_timestamp // interval_seconds) * interval_seconds
    current = aligned_start
    
    while current < end_timestamp:
        yield current
        current += interval_seconds


def get_timestamp_range_info(start_timestamp: int, end_timestamp: int) -> dict:
    """
    Get information about a timestamp range.
    
    Args:
        start_timestamp: Start Unix timestamp.
        end_timestamp: End Unix timestamp.
        
    Returns:
        Dictionary with range information including duration and candle counts.
    """
    duration_seconds = end_timestamp - start_timestamp
    duration_minutes = duration_seconds // 60
    duration_hours = duration_seconds // 3600
    duration_days = duration_seconds // 86400
    
    start_dt = timestamp_to_datetime(start_timestamp)
    end_dt = timestamp_to_datetime(end_timestamp)
    
    return {
        "start_timestamp": start_timestamp,
        "end_timestamp": end_timestamp,
        "start_datetime": start_dt.isoformat(),
        "end_datetime": end_dt.isoformat(),
        "duration_seconds": duration_seconds,
        "duration_minutes": duration_minutes,
        "duration_hours": duration_hours,
        "duration_days": duration_days,
        "m1_candles": duration_minutes,
        "m5_candles": duration_minutes // 5,
        "m15_candles": duration_minutes // 15,
        "m30_candles": duration_minutes // 30,
        "h1_candles": duration_hours,
        "h4_candles": duration_hours // 4,
        "d1_candles": duration_days,
    }


def align_timestamp_to_timeframe(timestamp: int, timeframe_minutes: int) -> int:
    """
    Align a timestamp to the start of its timeframe period.
    
    Args:
        timestamp: Unix timestamp in seconds.
        timeframe_minutes: Timeframe in minutes (e.g., 5 for m5, 60 for H1).
        
    Returns:
        Aligned timestamp at the start of the period.
        
    Example:
        >>> align_timestamp_to_timeframe(1704067234, 60)  # Align to hour
        1704067200
    """
    interval_seconds = timeframe_minutes * 60
    return (timestamp // interval_seconds) * interval_seconds


def get_day_of_week(timestamp: int) -> int:
    """
    Get the day of week for a timestamp (0=Monday, 6=Sunday).
    
    Args:
        timestamp: Unix timestamp.
        
    Returns:
        Day of week as integer (0-6).
    """
    dt = timestamp_to_datetime(timestamp)
    return dt.weekday()


def is_weekend(timestamp: int) -> bool:
    """
    Check if a timestamp falls on a weekend (Saturday or Sunday).
    
    Args:
        timestamp: Unix timestamp.
        
    Returns:
        True if weekend, False otherwise.
    """
    return get_day_of_week(timestamp) >= 5


def get_hour_of_day(timestamp: int) -> int:
    """
    Get the hour of day (0-23) for a timestamp in UTC.
    
    Args:
        timestamp: Unix timestamp.
        
    Returns:
        Hour of day (0-23).
    """
    dt = timestamp_to_datetime(timestamp)
    return dt.hour


def calculate_candle_count(
    start_timestamp: int,
    end_timestamp: int,
    timeframe_minutes: int = 1
) -> int:
    """
    Calculate the number of candles in a time range.
    
    Args:
        start_timestamp: Start Unix timestamp.
        end_timestamp: End Unix timestamp.
        timeframe_minutes: Timeframe in minutes.
        
    Returns:
        Number of complete candles in the range.
    """
    duration_seconds = end_timestamp - start_timestamp
    interval_seconds = timeframe_minutes * 60
    return duration_seconds // interval_seconds

