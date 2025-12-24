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
Abstract base class for market session handlers.

Defines the interface for market-specific session logic including
trading hours, holidays, and gap handling.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
import numpy as np

from marketforge.utils.time import (
    timestamp_to_datetime,
    get_day_of_week,
    get_hour_of_day,
    is_weekend,
)


@dataclass
class SessionInfo:
    """
    Information about a trading session.
    
    Attributes:
        name: Session name (e.g., "London", "NY", "Tokyo").
        start_hour_utc: Session start hour in UTC.
        end_hour_utc: Session end hour in UTC.
        volatility_multiplier: Relative volatility during this session.
        volume_multiplier: Relative volume during this session.
    """
    name: str
    start_hour_utc: int
    end_hour_utc: int
    volatility_multiplier: float = 1.0
    volume_multiplier: float = 1.0
    
    def contains_hour(self, hour: int) -> bool:
        """Check if hour falls within this session."""
        if self.start_hour_utc <= self.end_hour_utc:
            return self.start_hour_utc <= hour < self.end_hour_utc
        else:
            # Session crosses midnight
            return hour >= self.start_hour_utc or hour < self.end_hour_utc


@dataclass
class MarketStatus:
    """
    Current market status at a point in time.
    
    Attributes:
        is_open: Whether the market is open for trading.
        session: Current session info if market is open.
        time_to_open: Minutes until market opens (0 if open).
        time_to_close: Minutes until market closes (0 if closed).
        is_pre_market: Whether in pre-market hours.
        is_post_market: Whether in post-market hours.
    """
    is_open: bool
    session: Optional[SessionInfo] = None
    time_to_open: int = 0
    time_to_close: int = 0
    is_pre_market: bool = False
    is_post_market: bool = False


class MarketSession(ABC):
    """
    Abstract base class for market session handlers.
    
    Provides interface for determining:
    - Whether market is open at a given time
    - Current trading session
    - Gap locations (session boundaries, weekends)
    - Session-specific volatility/volume adjustments
    
    Subclasses implement market-specific logic for:
    - Crypto (24/7 trading)
    - Forex (session-based with weekend closure)
    - Stocks (market hours with holidays)
    """
    
    @property
    @abstractmethod
    def market_name(self) -> str:
        """Return market name identifier."""
        pass
    
    @property
    @abstractmethod
    def is_continuous(self) -> bool:
        """Return True if market trades 24/7."""
        pass
    
    @property
    @abstractmethod
    def has_weekend_closure(self) -> bool:
        """Return True if market closes on weekends."""
        pass
    
    @abstractmethod
    def is_market_open(self, timestamp: int) -> bool:
        """
        Check if market is open at given timestamp.
        
        Args:
            timestamp: Unix timestamp.
            
        Returns:
            True if market is open.
        """
        pass
    
    @abstractmethod
    def get_session(self, timestamp: int) -> Optional[SessionInfo]:
        """
        Get current trading session.
        
        Args:
            timestamp: Unix timestamp.
            
        Returns:
            SessionInfo if market is open, None otherwise.
        """
        pass
    
    @abstractmethod
    def get_market_status(self, timestamp: int) -> MarketStatus:
        """
        Get comprehensive market status.
        
        Args:
            timestamp: Unix timestamp.
            
        Returns:
            MarketStatus with current market state.
        """
        pass
    
    def filter_trading_times(self, timestamps: np.ndarray) -> np.ndarray:
        """
        Filter timestamps to only trading hours.
        
        Args:
            timestamps: Array of Unix timestamps.
            
        Returns:
            Boolean mask indicating trading times.
        """
        mask = np.array([self.is_market_open(ts) for ts in timestamps])
        return mask
    
    def get_gap_locations(self, timestamps: np.ndarray) -> np.ndarray:
        """
        Find locations where price gaps should occur.
        
        Gaps occur at session boundaries when market was closed.
        
        Args:
            timestamps: Array of Unix timestamps.
            
        Returns:
            Boolean mask indicating gap locations.
        """
        n = len(timestamps)
        gaps = np.zeros(n, dtype=bool)
        
        for i in range(1, n):
            prev_open = self.is_market_open(timestamps[i - 1])
            curr_open = self.is_market_open(timestamps[i])
            
            # Gap if transitioning from closed to open
            if not prev_open and curr_open:
                gaps[i] = True
        
        return gaps
    
    def get_volatility_multipliers(self, timestamps: np.ndarray) -> np.ndarray:
        """
        Get session-based volatility multipliers.
        
        Args:
            timestamps: Array of Unix timestamps.
            
        Returns:
            Array of volatility multipliers.
        """
        multipliers = np.ones(len(timestamps))
        
        for i, ts in enumerate(timestamps):
            session = self.get_session(ts)
            if session is not None:
                multipliers[i] = session.volatility_multiplier
        
        return multipliers
    
    def get_volume_multipliers(self, timestamps: np.ndarray) -> np.ndarray:
        """
        Get session-based volume multipliers.
        
        Args:
            timestamps: Array of Unix timestamps.
            
        Returns:
            Array of volume multipliers.
        """
        multipliers = np.ones(len(timestamps))
        
        for i, ts in enumerate(timestamps):
            session = self.get_session(ts)
            if session is not None:
                multipliers[i] = session.volume_multiplier
        
        return multipliers

