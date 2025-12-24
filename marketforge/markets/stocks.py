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
Stock market session handler.

US stock markets have defined trading hours with pre/post market sessions.
"""

from __future__ import annotations

from typing import Optional
from datetime import datetime

from marketforge.markets.base import MarketSession, SessionInfo, MarketStatus
from marketforge.utils.time import get_hour_of_day, get_day_of_week, timestamp_to_datetime


# US stock market sessions (all times in UTC, assuming ET = UTC-5 during EST)
# Note: Actual times shift with DST, this is simplified
STOCK_SESSIONS = [
    SessionInfo(
        name="PreMarket",
        start_hour_utc=9,   # 4:00 AM ET
        end_hour_utc=14,    # 9:00 AM ET
        volatility_multiplier=0.8,
        volume_multiplier=0.3,
    ),
    SessionInfo(
        name="Regular",
        start_hour_utc=14,  # 9:30 AM ET (simplified to 9:00)
        end_hour_utc=21,    # 4:00 PM ET
        volatility_multiplier=1.0,
        volume_multiplier=1.0,
    ),
    SessionInfo(
        name="PostMarket",
        start_hour_utc=21,  # 4:00 PM ET
        end_hour_utc=25,    # 8:00 PM ET (wraps to 1 AM next day)
        volatility_multiplier=0.7,
        volume_multiplier=0.2,
    ),
]

# Intraday patterns within regular session
REGULAR_SESSION_PATTERNS = {
    "open": SessionInfo(
        name="MarketOpen",
        start_hour_utc=14,
        end_hour_utc=16,
        volatility_multiplier=1.4,
        volume_multiplier=1.8,
    ),
    "midday": SessionInfo(
        name="Midday",
        start_hour_utc=16,
        end_hour_utc=19,
        volatility_multiplier=0.7,
        volume_multiplier=0.6,
    ),
    "close": SessionInfo(
        name="MarketClose",
        start_hour_utc=19,
        end_hour_utc=21,
        volatility_multiplier=1.3,
        volume_multiplier=1.5,
    ),
}

# Major US market holidays (simplified - month, day)
# Real implementation would use a proper holiday calendar
US_HOLIDAYS = [
    (1, 1),   # New Year's Day
    (1, 15),  # MLK Day (approx)
    (2, 19),  # Presidents Day (approx)
    (5, 27),  # Memorial Day (approx)
    (6, 19),  # Juneteenth
    (7, 4),   # Independence Day
    (9, 2),   # Labor Day (approx)
    (11, 28), # Thanksgiving (approx)
    (12, 25), # Christmas
]


class StockSession(MarketSession):
    """
    US stock market session handler.
    
    US stock markets operate with defined trading hours:
    
    1. **Pre-Market**: 4:00 AM - 9:30 AM ET
       - Lower volume, higher spreads
       - Reacts to overnight news
    
    2. **Regular Session**: 9:30 AM - 4:00 PM ET
       - Main trading hours
       - Highest liquidity
       - U-shaped volume pattern (high open/close, low midday)
    
    3. **Post-Market**: 4:00 PM - 8:00 PM ET
       - Earnings reactions
       - Lower liquidity
    
    Market closures:
    - Weekends (Saturday & Sunday)
    - Federal holidays
    - Early closes (day before holidays)
    
    Attributes:
        sessions: List of trading sessions.
        holidays: List of market holidays.
        
    Example:
        >>> session = StockSession()
        >>> session.is_market_open(1704067200)  # Depends on day/time
        True
        >>> session.get_session(1704067200).name
        'Regular'
    """
    
    def __init__(self, include_extended_hours: bool = True) -> None:
        """
        Initialize stock session handler.
        
        Args:
            include_extended_hours: Whether to include pre/post market.
        """
        self._include_extended_hours = include_extended_hours
        self._sessions = STOCK_SESSIONS
        self._regular_patterns = REGULAR_SESSION_PATTERNS
        self._holidays = US_HOLIDAYS
    
    @property
    def market_name(self) -> str:
        """Return market name."""
        return "stocks"
    
    @property
    def is_continuous(self) -> bool:
        """Stocks are not continuous."""
        return False
    
    @property
    def has_weekend_closure(self) -> bool:
        """Stocks close on weekends."""
        return True
    
    @property
    def sessions(self) -> list[SessionInfo]:
        """Return list of trading sessions."""
        if self._include_extended_hours:
            return self._sessions
        return [s for s in self._sessions if s.name == "Regular"]
    
    def is_holiday(self, timestamp: int) -> bool:
        """
        Check if timestamp falls on a market holiday.
        
        Args:
            timestamp: Unix timestamp.
            
        Returns:
            True if market holiday.
        """
        dt = timestamp_to_datetime(timestamp)
        return (dt.month, dt.day) in self._holidays
    
    def is_market_open(self, timestamp: int) -> bool:
        """
        Check if stock market is open.
        
        Args:
            timestamp: Unix timestamp.
            
        Returns:
            True if market is open.
        """
        # Check weekend
        day = get_day_of_week(timestamp)
        if day >= 5:  # Saturday or Sunday
            return False
        
        # Check holiday
        if self.is_holiday(timestamp):
            return False
        
        # Check trading hours
        hour = get_hour_of_day(timestamp)
        
        if self._include_extended_hours:
            # Extended hours: 9:00 - 25:00 UTC (4 AM - 8 PM ET)
            return 9 <= hour < 25 or hour < 1
        else:
            # Regular hours only: 14:00 - 21:00 UTC (9:30 AM - 4 PM ET)
            return 14 <= hour < 21
    
    def get_session(self, timestamp: int) -> Optional[SessionInfo]:
        """
        Get current trading session.
        
        Args:
            timestamp: Unix timestamp.
            
        Returns:
            Current SessionInfo, or None if closed.
        """
        if not self.is_market_open(timestamp):
            return None
        
        hour = get_hour_of_day(timestamp)
        
        # During regular session, use intraday patterns
        if 14 <= hour < 21:
            if 14 <= hour < 16:
                return self._regular_patterns["open"]
            elif 16 <= hour < 19:
                return self._regular_patterns["midday"]
            else:
                return self._regular_patterns["close"]
        
        # Extended hours
        for session in self._sessions:
            if session.contains_hour(hour):
                return session
        
        return None
    
    def get_market_status(self, timestamp: int) -> MarketStatus:
        """
        Get comprehensive market status.
        
        Args:
            timestamp: Unix timestamp.
            
        Returns:
            MarketStatus with current state.
        """
        is_open = self.is_market_open(timestamp)
        session = self.get_session(timestamp)
        
        hour = get_hour_of_day(timestamp)
        day = get_day_of_week(timestamp)
        
        # Determine if pre/post market
        is_pre = session is not None and session.name == "PreMarket"
        is_post = session is not None and session.name == "PostMarket"
        
        # Calculate time to open/close
        time_to_open = 0
        time_to_close = 0
        
        if not is_open:
            # Calculate minutes to next regular session open
            if day >= 5:  # Weekend
                days_to_monday = 7 - day
                time_to_open = (days_to_monday * 24 + 14 - hour) * 60
            elif hour < 14:
                time_to_open = (14 - hour) * 60
            else:  # After close
                time_to_open = ((24 - hour) + 14) * 60
        else:
            # Calculate minutes to regular session close
            if hour < 21:
                time_to_close = (21 - hour) * 60
            else:
                time_to_close = 0  # In post-market
        
        return MarketStatus(
            is_open=is_open,
            session=session,
            time_to_open=max(0, time_to_open),
            time_to_close=max(0, time_to_close),
            is_pre_market=is_pre,
            is_post_market=is_post,
        )

