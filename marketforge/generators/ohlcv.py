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
OHLCV candle construction from price and return series.

Generates realistic Open-High-Low-Close-Volume candles. Intrabar High/Low are
simulated with a Brownian bridge from open to close scaled by the bar's
conditional volatility, guaranteeing High >= max(open, close) and
Low <= min(open, close) by construction. Also models gaps and volume
correlation with price movement.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import numpy as np
import pandas as pd

from marketforge.config.settings import GeneratorConfig, MarketType
from marketforge.core.returns import ReturnSeriesResult, ReturnGenerator
from marketforge.generators.volume import VolumeGenerator
from marketforge.utils.random import RandomState


def intrabar_high_low(
    rng: RandomState,
    open_prices: np.ndarray,
    close_prices: np.ndarray,
    bar_volatility: np.ndarray,
    k: int = 8,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Vectorized intrabar High/Low via a Brownian bridge from open to close.

    The within-bar log-price is modeled as a Brownian bridge pinned at
    log(open) and log(close) with per-bar diffusion ``bar_volatility`` (the
    per-minute conditional volatility). High/Low are the running max/min of the
    bridge over ``k`` interior sub-steps. Guarantees High >= max(O,C) and
    Low <= min(O,C) by construction, with range scaling with volatility.

    Args:
        rng: Random state.
        open_prices, close_prices: shape (n,) price arrays (> 0).
        bar_volatility: shape (n,) per-bar log-volatility (std over the bar).
        k: number of interior sub-steps.

    Returns:
        (high, low) arrays of shape (n,).
    """
    n = open_prices.shape[0]
    log_o = np.log(open_prices)
    log_c = np.log(close_prices)

    # Brownian bridge on grid t_j = j/(k+1), j=1..k (interior points).
    # Build a standard BM via cumulative normal increments, then subtract the
    # linear interpolation of its endpoints to pin it to zero at both ends.
    incs = rng.standard_normal((n, k + 1)) * np.sqrt(1.0 / (k + 1))
    bm = np.cumsum(incs, axis=1)                      # (n, k+1); bm[:, -1] = B(1)
    t = np.linspace(1.0 / (k + 1), 1.0, k + 1)        # times of bm columns
    bridge = bm - t[None, :] * bm[:, -1:]             # pin endpoint to 0
    bridge = bridge[:, :-1]                            # drop endpoint (==0); (n, k)
    t_int = t[:-1]                                     # interior times; (k,)

    # Scale bridge by per-bar volatility -> intrabar log deviations.
    deviations = bridge * bar_volatility[:, None]      # (n, k)

    # Linear log-price interpolation between open and close at interior times.
    base = log_o[:, None] + np.outer(log_c - log_o, t_int)  # (n, k)
    log_path = base + deviations

    # Candidate extremes include the two endpoints (open, close) and interior path.
    path_high = np.maximum(np.exp(log_path.max(axis=1)), np.maximum(open_prices, close_prices))
    path_low = np.minimum(np.exp(log_path.min(axis=1)), np.minimum(open_prices, close_prices))
    return path_high, path_low


@dataclass
class OHLCVData:
    """
    OHLCV data container for a single asset.
    
    Attributes:
        symbol: Asset symbol.
        timestamps: Unix timestamps for each candle.
        open: Opening prices.
        high: High prices.
        low: Low prices.
        close: Closing prices.
        volume: Trading volumes.
    """
    symbol: str
    timestamps: np.ndarray
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    volume: np.ndarray
    
    def __len__(self) -> int:
        """Return number of candles."""
        return len(self.timestamps)
    
    @property
    def n_candles(self) -> int:
        """Return number of candles."""
        return len(self.timestamps)
    
    def to_dataframe(self) -> pd.DataFrame:
        """
        Convert to pandas DataFrame.
        
        Returns:
            DataFrame with OHLCV columns.
        """
        return pd.DataFrame({
            "timestamp": self.timestamps,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
        })
    
    def validate(self) -> bool:
        """
        Validate OHLCV data integrity.
        
        Returns:
            True if valid, raises ValueError otherwise.
        """
        # Check lengths match
        n = len(self.timestamps)
        if not all(len(arr) == n for arr in [self.open, self.high, self.low, self.close, self.volume]):
            raise ValueError("Array lengths do not match")
        
        # Check high >= max(open, close) and low <= min(open, close)
        max_oc = np.maximum(self.open, self.close)
        min_oc = np.minimum(self.open, self.close)
        
        if not np.all(self.high >= max_oc - 1e-10):
            raise ValueError("High must be >= max(open, close)")
        
        if not np.all(self.low <= min_oc + 1e-10):
            raise ValueError("Low must be <= min(open, close)")
        
        # Check high >= low
        if not np.all(self.high >= self.low - 1e-10):
            raise ValueError("High must be >= low")
        
        # Check volume >= 0
        if not np.all(self.volume >= 0):
            raise ValueError("Volume must be non-negative")
        
        return True


@dataclass
class MultiAssetOHLCVData:
    """
    Container for OHLCV data of multiple assets.
    
    Attributes:
        assets: Dictionary mapping symbol to OHLCVData.
    """
    assets: dict[str, OHLCVData]
    
    def __getitem__(self, symbol: str) -> OHLCVData:
        """Get OHLCV data for a symbol."""
        return self.assets[symbol]
    
    @property
    def symbols(self) -> list[str]:
        """Return list of asset symbols."""
        return list(self.assets.keys())
    
    def to_dataframes(self) -> dict[str, pd.DataFrame]:
        """Convert all assets to DataFrames."""
        return {symbol: data.to_dataframe() for symbol, data in self.assets.items()}


class OHLCVBuilder:
    """
    Builder for constructing realistic OHLCV candles.

    Takes close prices from the return generator and constructs
    realistic OHLC candles with:
    - Open prices that may gap from previous close
    - High/Low simulated via a Brownian bridge from open to close, scaled by
      the bar's conditional volatility (running max/min over sub-steps),
      guaranteeing High >= max(open, close) and Low <= min(open, close)
    - Volume correlated with price movement

    Attributes:
        config: Generator configuration.
        volume_generator: Generator for volume data.

    Example:
        >>> config = GeneratorConfig(...)
        >>> builder = OHLCVBuilder(config)
        >>> rng = RandomState(42)
        >>> ohlcv = builder.build(rng)
    """
    
    def __init__(
        self,
        config: GeneratorConfig,
        volume_generator: Optional[VolumeGenerator] = None
    ) -> None:
        """
        Initialize the OHLCV builder.
        
        Args:
            config: Generator configuration.
            volume_generator: Optional volume generator. Creates default if None.
        """
        self._config = config
        self._return_generator = ReturnGenerator(config)
        
        if volume_generator is None:
            volume_generator = VolumeGenerator(config)
        self._volume_generator = volume_generator
    
    @property
    def config(self) -> GeneratorConfig:
        """Return generator configuration."""
        return self._config
    
    def build(
        self,
        rng: RandomState,
        return_result: Optional[ReturnSeriesResult] = None
    ) -> MultiAssetOHLCVData:
        """
        Build OHLCV data for all configured assets.
        
        Args:
            rng: Random state for reproducibility.
            return_result: Optional pre-generated return data.
                          If None, generates new returns.
                          
        Returns:
            MultiAssetOHLCVData containing OHLCV for all assets.
        """
        # Generate returns if not provided
        if return_result is None:
            return_result = self._return_generator.generate(rng)
        
        n_steps = return_result.n_steps
        
        # Generate volumes
        volumes = self._volume_generator.generate(
            rng,
            n_steps,
            np.abs(return_result.returns),  # Absolute returns for volume correlation
            return_result.volatilities,
        )
        
        # Build OHLCV for each asset
        assets = {}
        for i, symbol in enumerate(return_result.asset_symbols):
            ohlcv = self._build_single_asset(
                rng=rng,
                symbol=symbol,
                close_prices=return_result.prices[:, i],
                returns=return_result.returns[:, i],
                volatilities=return_result.volatilities[:, i],
                volumes=volumes[:, i],
                timestamps=return_result.timestamps,
            )
            assets[symbol] = ohlcv
        
        return MultiAssetOHLCVData(assets=assets)
    
    def _build_single_asset(
        self,
        rng: RandomState,
        symbol: str,
        close_prices: np.ndarray,
        returns: np.ndarray,
        volatilities: np.ndarray,
        volumes: np.ndarray,
        timestamps: np.ndarray,
    ) -> OHLCVData:
        """
        Build OHLCV data for a single asset.
        
        Args:
            rng: Random state for reproducibility.
            symbol: Asset symbol.
            close_prices: Array of close prices.
            returns: Array of log returns.
            volatilities: Array of conditional volatilities.
            volumes: Array of volumes.
            timestamps: Array of Unix timestamps.
            
        Returns:
            OHLCVData for the asset.
        """
        n = len(close_prices)

        # Initialize arrays
        open_prices = np.zeros(n)

        # First candle: open = close (no gap)
        open_prices[0] = close_prices[0] / np.exp(returns[0])

        # Generate opens with potential gaps (for non-crypto markets)
        if self._config.market_type != MarketType.CRYPTO:
            gap_probs = self._get_gap_probabilities(timestamps)
            gaps = self._generate_gaps(rng, n - 1, volatilities[1:], gap_probs)
            open_prices[1:] = close_prices[:-1] * (1 + gaps)
        else:
            # Crypto: open = previous close (no gaps)
            open_prices[1:] = close_prices[:-1]

        # Vectorized intrabar high/low via Brownian bridge
        high_prices, low_prices = intrabar_high_low(
            rng,
            open_prices=open_prices,
            close_prices=close_prices,
            bar_volatility=volatilities,
            k=8,
        )
        
        return OHLCVData(
            symbol=symbol,
            timestamps=timestamps,
            open=open_prices,
            high=high_prices,
            low=low_prices,
            close=close_prices,
            volume=volumes,
        )
    
    def _get_gap_probabilities(self, timestamps: np.ndarray) -> np.ndarray:
        """
        Get gap probabilities based on time-of-day and session transitions.
        
        Args:
            timestamps: Array of Unix timestamps.
            
        Returns:
            Array of gap probabilities for each timestamp transition.
        """
        n = len(timestamps) - 1
        probs = np.zeros(n)
        
        # Base gap probability
        base_prob = 0.001
        
        for i in range(n):
            # Higher probability at session changes
            hour = (timestamps[i] // 3600) % 24
            
            # Common session change hours (simplified)
            if hour in [0, 8, 14, 22]:  # Major session opens
                probs[i] = base_prob * 5
            else:
                probs[i] = base_prob
        
        return probs
    
    def _generate_gaps(
        self,
        rng: RandomState,
        n: int,
        volatilities: np.ndarray,
        gap_probs: np.ndarray,
    ) -> np.ndarray:
        """
        Generate gap values for open prices.
        
        Args:
            rng: Random state for reproducibility.
            n: Number of gaps to generate.
            volatilities: Volatilities for scaling gap sizes.
            gap_probs: Probability of gap at each point.
            
        Returns:
            Array of gap values (as fraction of price).
        """
        gaps = np.zeros(n)
        
        # Determine which points have gaps
        has_gap = rng.uniform(size=n) < gap_probs
        n_gaps = has_gap.sum()
        
        if n_gaps > 0:
            # Generate gap sizes (normal distribution)
            gap_sizes = rng.normal(0, volatilities[has_gap] * 2)
            gaps[has_gap] = gap_sizes
        
        return gaps


def build_ohlcv_from_config(
    config: GeneratorConfig,
    seed: Optional[int] = None
) -> MultiAssetOHLCVData:
    """
    Convenience function to build OHLCV data from configuration.
    
    Args:
        config: Generator configuration.
        seed: Optional random seed.
        
    Returns:
        MultiAssetOHLCVData for all configured assets.
    """
    rng = RandomState(seed if seed is not None else config.seed)
    builder = OHLCVBuilder(config)
    return builder.build(rng)

