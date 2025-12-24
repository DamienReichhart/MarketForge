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
Forex market session handler.

Forex markets trade 24/5 with distinct sessions and weekend closure.
"""

from __future__ import annotations

from typing import Optional

from marketforge.markets.base import MarketSession, SessionInfo, MarketStatus
from marketforge.utils.time import get_hour_of_day, get_day_of_week


# Major forex trading sessions
FOREX_SESSIONS = [
    SessionInfo(
        name="Sydney",
        start_hour_utc=22,  # 10 PM UTC (wraps to next day)
        end_hour_utc=7,
        volatility_multiplier=0.7,
        volume_multiplier=0.6,
    ),
    SessionInfo(
        name="Tokyo",
        start_hour_utc=0,
        end_hour_utc=9,
        volatility_multiplier=0.8,
        volume_multiplier=0.7,
    ),
    SessionInfo(
        name="London",
        start_hour_utc=8,
        end_hour_utc=17,
        volatility_multiplier=1.2,
        volume_multiplier=1.3,
    ),
    SessionInfo(
        name="NewYork",
        start_hour_utc=13,
        end_hour_utc=22,
        volatility_multiplier=1.1,
        volume_multiplier=1.2,
    ),
]

# London-NY overlap is highest activity
OVERLAP_SESSION = SessionInfo(
    name="London_NY_Overlap",
    start_hour_utc=13,
    end_hour_utc=17,
    volatility_multiplier=1.5,
    volume_multiplier=1.6,
)


class ForexSession(MarketSession):
    """
    Forex market session handler.
    
    The forex market operates 24 hours a day during weekdays,
    with four major overlapping sessions:
    
    1. **Sydney** (22:00-07:00 UTC): Low volatility
    2. **Tokyo** (00:00-09:00 UTC): Moderate volatility
    3. **London** (08:00-17:00 UTC): High volatility
    4. **New York** (13:00-22:00 UTC): High volatility
    
    The London-NY overlap (13:00-17:00 UTC) has the highest
    trading activity and volatility.
    
    Market closes:
    - Friday 22:00 UTC (NY close)
    - Opens Sunday 22:00 UTC (Sydney open)
    
    Attributes:
        sessions: List of major trading sessions.
        
    Example:
        >>> session = ForexSession()
        >>> session.is_market_open(1704067200)  # Depends on day/time
        True
        >>> session.get_session(1704067200).name
        'London'
    """
    
    def __init__(self) -> None:
        """Initialize forex session handler."""
        self._sessions = FOREX_SESSIONS
        self._overlap_session = OVERLAP_SESSION
    
    @property
    def market_name(self) -> str:
        """Return market name."""
        return "forex"
    
    @property
    def is_continuous(self) -> bool:
        """Forex is not fully continuous (weekend closure)."""
        return False
    
    @property
    def has_weekend_closure(self) -> bool:
        """Forex closes on weekends."""
        return True
    
    @property
    def sessions(self) -> list[SessionInfo]:
        """Return list of trading sessions."""
        return self._sessions
    
    def is_market_open(self, timestamp: int) -> bool:
        """
        Check if forex market is open.
        
        Closed during weekend (Sat 00:00 to Sun 22:00 UTC).
        
        Args:
            timestamp: Unix timestamp.
            
        Returns:
            True if market is open.
        """
        day = get_day_of_week(timestamp)  # 0=Mon, 6=Sun
        hour = get_hour_of_day(timestamp)
        
        # Saturday: closed
        if day == 5:
            return False
        
        # Sunday: opens at 22:00 UTC
        if day == 6:
            return hour >= 22
        
        # Friday: closes at 22:00 UTC
        if day == 4:
            return hour < 22
        
        # Mon-Thu: always open
        return True
    
    def get_session(self, timestamp: int) -> Optional[SessionInfo]:
        """
        Get current trading session.
        
        Returns the most relevant session based on time.
        During overlaps, returns the higher-activity session.
        
        Args:
            timestamp: Unix timestamp.
            
        Returns:
            Current SessionInfo, or None if market closed.
        """
        if not self.is_market_open(timestamp):
            return None
        
        hour = get_hour_of_day(timestamp)
        
        # Check for London-NY overlap first
        if self._overlap_session.contains_hour(hour):
            return self._overlap_session
        
        # Find primary session
        # Priority: London > NY > Tokyo > Sydney
        session_priority = ["London", "NewYork", "Tokyo", "Sydney"]
        
        for session_name in session_priority:
            for session in self._sessions:
                if session.name == session_name and session.contains_hour(hour):
                    return session
        
        # Fallback to any matching session
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
        session = self.get_session(timestamp) if is_open else None
        
        day = get_day_of_week(timestamp)
        hour = get_hour_of_day(timestamp)
        
        # Calculate time to open/close
        time_to_open = 0
        time_to_close = 0
        
        if not is_open:
            # Calculate minutes to Sunday 22:00 UTC
            if day == 5:  # Saturday
                # Hours until Sunday 22:00
                hours_remaining = 24 - hour + 22
                time_to_open = hours_remaining * 60
            elif day == 6 and hour < 22:  # Sunday before open
                time_to_open = (22 - hour) * 60
        else:
            # Calculate minutes to Friday 22:00 UTC
            if day == 4:  # Friday
                time_to_close = (22 - hour) * 60
            else:
                # Days until Friday + hours until 22:00
                days_to_friday = 4 - day
                time_to_close = (days_to_friday * 24 + (22 - hour)) * 60
        
        return MarketStatus(
            is_open=is_open,
            session=session,
            time_to_open=time_to_open,
            time_to_close=time_to_close,
            is_pre_market=False,  # Forex has no pre-market
            is_post_market=False,
        )

