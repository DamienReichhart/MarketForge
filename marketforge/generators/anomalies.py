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
Anomaly injection for realistic market events.

Injects various market anomalies into OHLCV data:
- Gaps: Price jumps between candles (overnight, weekend, news events)
- Spikes: Sudden price moves within candles (fat tail events)
- Flash crashes: Sharp drops with V-shaped recovery
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional
import numpy as np

from marketforge.config.settings import AnomalyConfig, AnomalyType, MarketType
from marketforge.generators.ohlcv import OHLCVData, MultiAssetOHLCVData
from marketforge.utils.random import RandomState


@dataclass
class AnomalyEvent:
    """
    Record of an injected anomaly.
    
    Attributes:
        type: Type of anomaly.
        index: Candle index where anomaly was injected.
        magnitude: Size of the anomaly (as price fraction).
        direction: Direction of move (+1 up, -1 down).
        duration: Duration in candles (for multi-candle events).
    """
    type: AnomalyType
    index: int
    magnitude: float
    direction: int
    duration: int = 1


@dataclass
class AnomalyReport:
    """
    Report of all anomalies injected into a dataset.
    
    Attributes:
        events: List of anomaly events.
        asset_symbol: Asset the anomalies were applied to.
    """
    events: list[AnomalyEvent]
    asset_symbol: str
    
    @property
    def n_events(self) -> int:
        """Return number of events."""
        return len(self.events)
    
    def get_events_by_type(self, anomaly_type: AnomalyType) -> list[AnomalyEvent]:
        """Get events of a specific type."""
        return [e for e in self.events if e.type == anomaly_type]


class AnomalyInjector:
    """
    Injector for market anomalies into OHLCV data.
    
    Supports three types of anomalies:
    
    1. **Gaps**: Price discontinuities between candles
       - Caused by overnight/weekend closures
       - News events, earnings announcements
       - Applied to open price of next candle
    
    2. **Spikes**: Sudden intrabar price moves
       - Fat-tail events (tail risk)
       - Large wicks with quick reversal
       - Affects high/low of single candle
    
    3. **Flash Crashes**: Multi-candle sharp decline and recovery
       - Cascading sell-offs
       - V-shaped or U-shaped recovery
       - Affects multiple consecutive candles
    
    Attributes:
        config: Anomaly configuration.
        market_type: Type of market (affects gap behavior).
        
    Example:
        >>> config = AnomalyConfig(types={AnomalyType.GAPS, AnomalyType.SPIKES})
        >>> injector = AnomalyInjector(config)
        >>> rng = RandomState(42)
        >>> modified_ohlcv, report = injector.inject(rng, ohlcv_data)
    """
    
    def __init__(
        self,
        config: AnomalyConfig,
        market_type: MarketType = MarketType.CRYPTO
    ) -> None:
        """
        Initialize the anomaly injector.
        
        Args:
            config: Anomaly configuration.
            market_type: Market type for context-aware injection.
        """
        self._config = config
        self._market_type = market_type
    
    @property
    def config(self) -> AnomalyConfig:
        """Return anomaly configuration."""
        return self._config
    
    @property
    def enabled_types(self) -> frozenset[AnomalyType]:
        """Return set of enabled anomaly types."""
        return self._config.types
    
    def inject(
        self,
        rng: RandomState,
        ohlcv: OHLCVData,
    ) -> tuple[OHLCVData, AnomalyReport]:
        """
        Inject anomalies into OHLCV data.
        
        Creates a modified copy of the OHLCV data with anomalies injected.
        The original data is not modified.
        
        Args:
            rng: Random state for reproducibility.
            ohlcv: OHLCV data to modify.
            
        Returns:
            Tuple of (modified_ohlcv, anomaly_report).
        """
        # Create copies of the data
        open_prices = ohlcv.open.copy()
        high_prices = ohlcv.high.copy()
        low_prices = ohlcv.low.copy()
        close_prices = ohlcv.close.copy()
        volumes = ohlcv.volume.copy()
        
        events: list[AnomalyEvent] = []
        n = len(ohlcv)
        
        # Inject gaps
        if AnomalyType.GAPS in self._config.types:
            gap_events = self._inject_gaps(
                rng, open_prices, close_prices, high_prices, low_prices, n
            )
            events.extend(gap_events)
        
        # Inject spikes
        if AnomalyType.SPIKES in self._config.types:
            spike_events = self._inject_spikes(
                rng, open_prices, close_prices, high_prices, low_prices, volumes, n
            )
            events.extend(spike_events)
        
        # Inject flash crashes
        if AnomalyType.FLASH_CRASH in self._config.types:
            crash_events = self._inject_flash_crashes(
                rng, open_prices, close_prices, high_prices, low_prices, volumes, n
            )
            events.extend(crash_events)
        
        # Create modified OHLCV
        modified = OHLCVData(
            symbol=ohlcv.symbol,
            timestamps=ohlcv.timestamps.copy(),
            open=open_prices,
            high=high_prices,
            low=low_prices,
            close=close_prices,
            volume=volumes,
        )
        
        report = AnomalyReport(events=events, asset_symbol=ohlcv.symbol)
        
        return modified, report
    
    def inject_multi_asset(
        self,
        rng: RandomState,
        data: MultiAssetOHLCVData,
    ) -> tuple[MultiAssetOHLCVData, dict[str, AnomalyReport]]:
        """
        Inject anomalies into multi-asset OHLCV data.
        
        Args:
            rng: Random state for reproducibility.
            data: Multi-asset OHLCV data.
            
        Returns:
            Tuple of (modified_data, reports_by_symbol).
        """
        modified_assets = {}
        reports = {}
        
        for symbol, ohlcv in data.assets.items():
            modified, report = self.inject(rng, ohlcv)
            modified_assets[symbol] = modified
            reports[symbol] = report
        
        return MultiAssetOHLCVData(assets=modified_assets), reports
    
    def _inject_gaps(
        self,
        rng: RandomState,
        open_prices: np.ndarray,
        close_prices: np.ndarray,
        high_prices: np.ndarray,
        low_prices: np.ndarray,
        n: int,
    ) -> list[AnomalyEvent]:
        """
        Inject price gaps.
        
        Gaps are applied to the open price, creating a discontinuity
        from the previous close.
        """
        events = []
        
        # Skip gaps for crypto (24/7 market)
        if self._market_type == MarketType.CRYPTO:
            return events
        
        gap_prob = self._config.gap_probability
        min_mag, max_mag = self._config.gap_magnitude_range
        
        for i in range(1, n):
            if rng.uniform() < gap_prob:
                # Determine gap direction and magnitude
                direction = rng.choice([-1, 1])
                magnitude = rng.uniform(min_mag, max_mag)
                
                # Apply gap to open price
                gap_amount = close_prices[i - 1] * magnitude * direction
                open_prices[i] += gap_amount
                
                # Adjust high/low if needed
                if direction > 0:
                    high_prices[i] = max(high_prices[i], open_prices[i])
                else:
                    low_prices[i] = min(low_prices[i], open_prices[i])
                
                events.append(AnomalyEvent(
                    type=AnomalyType.GAPS,
                    index=i,
                    magnitude=magnitude,
                    direction=direction,
                ))
        
        return events
    
    def _inject_spikes(
        self,
        rng: RandomState,
        open_prices: np.ndarray,
        close_prices: np.ndarray,
        high_prices: np.ndarray,
        low_prices: np.ndarray,
        volumes: np.ndarray,
        n: int,
    ) -> list[AnomalyEvent]:
        """
        Inject price spikes (fat tail events).
        
        Spikes extend the high or low of a candle significantly,
        creating a long wick.
        """
        events = []
        
        spike_prob = self._config.spike_probability
        min_mag, max_mag = self._config.spike_magnitude_range
        
        for i in range(n):
            if rng.uniform() < spike_prob:
                # Determine spike direction and magnitude
                direction = rng.choice([-1, 1])
                magnitude = rng.uniform(min_mag, max_mag)
                
                mid_price = (open_prices[i] + close_prices[i]) / 2
                spike_amount = mid_price * magnitude
                
                if direction > 0:
                    # Upward spike - extend high
                    high_prices[i] += spike_amount
                else:
                    # Downward spike - extend low
                    new_low = low_prices[i] - spike_amount
                    low_prices[i] = max(new_low, mid_price * 0.5)  # Don't go below 50%
                
                # Increase volume on spike candle
                volumes[i] *= 2.0
                
                events.append(AnomalyEvent(
                    type=AnomalyType.SPIKES,
                    index=i,
                    magnitude=magnitude,
                    direction=direction,
                ))
        
        return events
    
    def _inject_flash_crashes(
        self,
        rng: RandomState,
        open_prices: np.ndarray,
        close_prices: np.ndarray,
        high_prices: np.ndarray,
        low_prices: np.ndarray,
        volumes: np.ndarray,
        n: int,
    ) -> list[AnomalyEvent]:
        """
        Inject flash crash events.
        
        Flash crashes are multi-candle events with:
        1. Sharp initial drop
        2. Continued decline for a few candles
        3. V-shaped or U-shaped recovery
        """
        events = []
        
        # Flash crashes are per-day probability
        candles_per_day = 24 * 60  # 1-minute candles
        n_days = n // candles_per_day
        expected_crashes = n_days * self._config.flash_crash_probability
        
        if expected_crashes < 0.01:
            return events  # Too short a period for crashes
        
        # Determine number of crashes
        n_crashes = rng.poisson(expected_crashes)
        n_crashes = min(n_crashes, 3)  # Cap at 3 crashes
        
        if n_crashes == 0:
            return events
        
        crash_magnitude = self._config.flash_crash_magnitude
        recovery_candles = self._config.flash_crash_recovery_candles
        crash_duration = recovery_candles * 2  # Total event duration
        
        # Minimum spacing between crashes
        min_spacing = crash_duration * 2
        
        # Select crash start points
        available_range = n - crash_duration - 100  # Leave buffer at end
        if available_range <= 0:
            return events
        
        crash_starts = []
        for _ in range(n_crashes):
            attempts = 0
            while attempts < 100:
                start = rng.integers(100, available_range)
                
                # Check spacing from existing crashes
                if all(abs(start - s) >= min_spacing for s in crash_starts):
                    crash_starts.append(start)
                    break
                attempts += 1
        
        # Inject each crash
        for start in crash_starts:
            self._apply_flash_crash(
                rng=rng,
                open_prices=open_prices,
                close_prices=close_prices,
                high_prices=high_prices,
                low_prices=low_prices,
                volumes=volumes,
                start_index=start,
                magnitude=crash_magnitude,
                recovery_candles=recovery_candles,
            )
            
            events.append(AnomalyEvent(
                type=AnomalyType.FLASH_CRASH,
                index=start,
                magnitude=crash_magnitude,
                direction=-1,
                duration=crash_duration,
            ))
        
        return events
    
    def _apply_flash_crash(
        self,
        rng: RandomState,
        open_prices: np.ndarray,
        close_prices: np.ndarray,
        high_prices: np.ndarray,
        low_prices: np.ndarray,
        volumes: np.ndarray,
        start_index: int,
        magnitude: float,
        recovery_candles: int,
    ) -> None:
        """
        Apply a flash crash pattern to the data.
        
        Creates a V-shaped price pattern:
        1. Rapid decline (magnitude drop over ~1/3 of recovery_candles)
        2. Bottom (brief consolidation)
        3. Recovery (back to near original levels)
        """
        # Price at crash start
        start_price = close_prices[start_index - 1]
        bottom_price = start_price * (1 - magnitude)
        
        # Crash phase: rapid decline
        crash_candles = recovery_candles // 3
        for i in range(crash_candles):
            idx = start_index + i
            if idx >= len(close_prices):
                break
            
            # Exponential decline curve
            progress = (i + 1) / crash_candles
            decay = 1 - magnitude * (1 - np.exp(-3 * progress)) / (1 - np.exp(-3))
            
            price_level = start_price * decay
            
            # Adjust prices
            close_prices[idx] = price_level
            open_prices[idx] = close_prices[idx - 1] if idx > 0 else start_price
            high_prices[idx] = max(open_prices[idx], close_prices[idx]) * 1.01
            low_prices[idx] = min(open_prices[idx], close_prices[idx]) * 0.995
            
            # Spike volume during crash
            volumes[idx] *= 3.0
        
        # Bottom phase: brief consolidation
        bottom_start = start_index + crash_candles
        bottom_candles = recovery_candles // 6
        for i in range(bottom_candles):
            idx = bottom_start + i
            if idx >= len(close_prices):
                break
            
            # Small fluctuations around bottom
            noise = rng.uniform(-0.01, 0.01)
            close_prices[idx] = bottom_price * (1 + noise)
            open_prices[idx] = close_prices[idx - 1]
            high_prices[idx] = max(open_prices[idx], close_prices[idx]) * 1.005
            low_prices[idx] = min(open_prices[idx], close_prices[idx]) * 0.995
            volumes[idx] *= 2.0
        
        # Recovery phase
        recovery_start = bottom_start + bottom_candles
        actual_recovery = recovery_candles - crash_candles - bottom_candles
        for i in range(actual_recovery):
            idx = recovery_start + i
            if idx >= len(close_prices):
                break
            
            # Exponential recovery (doesn't quite reach original price)
            progress = (i + 1) / actual_recovery
            recovery_factor = magnitude * 0.9 * (1 - np.exp(-2 * progress))
            
            price_level = bottom_price * (1 + recovery_factor)
            
            close_prices[idx] = price_level
            open_prices[idx] = close_prices[idx - 1]
            high_prices[idx] = max(open_prices[idx], close_prices[idx]) * 1.008
            low_prices[idx] = min(open_prices[idx], close_prices[idx]) * 0.997
            
            # Elevated but declining volume
            volumes[idx] *= (2.0 - progress)

