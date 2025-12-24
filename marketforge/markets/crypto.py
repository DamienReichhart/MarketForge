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
Crypto market session handler.

Crypto markets trade 24/7 with no closures or gaps.
Session-based volume patterns still apply (Asia/Europe/US).
"""

from __future__ import annotations

from typing import Optional

from marketforge.markets.base import MarketSession, SessionInfo, MarketStatus
from marketforge.utils.time import get_hour_of_day


# Crypto trading sessions (informal, based on activity patterns)
CRYPTO_SESSIONS = [
    SessionInfo(
        name="Asia",
        start_hour_utc=0,
        end_hour_utc=8,
        volatility_multiplier=0.9,
        volume_multiplier=0.8,
    ),
    SessionInfo(
        name="Europe",
        start_hour_utc=8,
        end_hour_utc=14,
        volatility_multiplier=1.1,
        volume_multiplier=1.2,
    ),
    SessionInfo(
        name="US",
        start_hour_utc=14,
        end_hour_utc=22,
        volatility_multiplier=1.2,
        volume_multiplier=1.3,
    ),
    SessionInfo(
        name="Late",
        start_hour_utc=22,
        end_hour_utc=24,
        volatility_multiplier=0.8,
        volume_multiplier=0.7,
    ),
]


class CryptoSession(MarketSession):
    """
    Crypto market session handler.
    
    Crypto markets are unique in that they:
    - Trade 24 hours a day, 7 days a week
    - Have no official market hours or closures
    - Still exhibit session-based patterns (Asia/Europe/US activity)
    - Never have price gaps from market closures
    
    The session definitions are based on typical trading activity
    patterns rather than official exchange hours.
    
    Attributes:
        sessions: List of informal trading sessions.
        
    Example:
        >>> session = CryptoSession()
        >>> session.is_market_open(1704067200)  # Always True
        True
        >>> session.get_session(1704067200).name  # Session based on time
        'Asia'
    """
    
    def __init__(self) -> None:
        """Initialize crypto session handler."""
        self._sessions = CRYPTO_SESSIONS
    
    @property
    def market_name(self) -> str:
        """Return market name."""
        return "crypto"
    
    @property
    def is_continuous(self) -> bool:
        """Crypto trades continuously."""
        return True
    
    @property
    def has_weekend_closure(self) -> bool:
        """Crypto has no weekend closure."""
        return False
    
    @property
    def sessions(self) -> list[SessionInfo]:
        """Return list of trading sessions."""
        return self._sessions
    
    def is_market_open(self, timestamp: int) -> bool:
        """
        Check if market is open.
        
        Crypto is always open.
        
        Args:
            timestamp: Unix timestamp.
            
        Returns:
            Always True for crypto.
        """
        return True
    
    def get_session(self, timestamp: int) -> Optional[SessionInfo]:
        """
        Get current trading session.
        
        Returns the informal session based on time of day.
        
        Args:
            timestamp: Unix timestamp.
            
        Returns:
            Current SessionInfo.
        """
        hour = get_hour_of_day(timestamp)
        
        for session in self._sessions:
            if session.contains_hour(hour):
                return session
        
        # Fallback (shouldn't happen with complete session coverage)
        return self._sessions[0]
    
    def get_market_status(self, timestamp: int) -> MarketStatus:
        """
        Get market status.
        
        Crypto is always open with no pre/post market.
        
        Args:
            timestamp: Unix timestamp.
            
        Returns:
            MarketStatus indicating always open.
        """
        return MarketStatus(
            is_open=True,
            session=self.get_session(timestamp),
            time_to_open=0,
            time_to_close=0,  # Never closes
            is_pre_market=False,
            is_post_market=False,
        )

