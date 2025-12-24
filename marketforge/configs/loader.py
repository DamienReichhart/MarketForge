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
Configuration loader and registry for market configs.

Provides centralized access to all market configurations.
"""

from __future__ import annotations

from typing import Optional
import numpy as np

from marketforge.configs.base import MarketConfig, MarketType, AssetParams
from marketforge.config.settings import (
    GeneratorConfig,
    AssetConfig,
    GARCHParams,
    AnomalyConfig,
    AnomalyType,
)
from marketforge.config.defaults import get_market_defaults


class ConfigRegistry:
    """
    Registry for all market configurations.
    
    Provides lazy loading and caching of market configs.
    
    Example:
        >>> registry = ConfigRegistry()
        >>> forex_config = registry.get_config(MarketType.FOREX)
        >>> print(f"Forex has {forex_config.n_assets} pairs")
    """
    
    _instance: Optional["ConfigRegistry"] = None
    _configs: dict[MarketType, MarketConfig] = {}
    
    def __new__(cls) -> "ConfigRegistry":
        """Singleton pattern for registry."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def get_config(self, market_type: MarketType) -> MarketConfig:
        """
        Get configuration for a market type.
        
        Lazy loads and caches the configuration.
        
        Args:
            market_type: Type of market.
            
        Returns:
            MarketConfig for the specified market.
        """
        if market_type not in self._configs:
            self._configs[market_type] = self._load_config(market_type)
        return self._configs[market_type]
    
    def _load_config(self, market_type: MarketType) -> MarketConfig:
        """Load configuration for a market type."""
        if market_type == MarketType.FOREX:
            from marketforge.configs.forex_config import get_forex_config
            return get_forex_config()
        elif market_type == MarketType.CRYPTO:
            from marketforge.configs.crypto_config import get_crypto_config
            return get_crypto_config()
        elif market_type == MarketType.STOCKS:
            from marketforge.configs.stocks_config import get_stocks_config
            return get_stocks_config()
        else:
            raise ValueError(f"Unknown market type: {market_type}")
    
    def get_all_configs(self) -> dict[MarketType, MarketConfig]:
        """Load and return all market configurations."""
        for market_type in MarketType:
            self.get_config(market_type)
        return self._configs.copy()
    
    def clear_cache(self) -> None:
        """Clear cached configurations."""
        self._configs.clear()


def load_market_config(market_type: MarketType | str) -> MarketConfig:
    """
    Convenience function to load a market configuration.
    
    Args:
        market_type: Market type as enum or string.
        
    Returns:
        MarketConfig for the specified market.
    """
    if isinstance(market_type, str):
        market_type = MarketType(market_type.lower())
    
    registry = ConfigRegistry()
    return registry.get_config(market_type)


def get_available_markets() -> list[str]:
    """Return list of available market type names."""
    return [mt.value for mt in MarketType]


def get_asset_market_mapping() -> dict[str, MarketType]:
    """
    Create a mapping of asset symbols to their market types.
    
    Loads all market configurations and creates a dictionary that maps
    each asset symbol to its corresponding MarketType. This is used for
    asset validation and auto-detection of markets.
    
    Returns:
        Dictionary mapping asset symbol (str) to MarketType.
        
    Example:
        >>> mapping = get_asset_market_mapping()
        >>> mapping["BTCUSD"]
        <MarketType.CRYPTO: 'crypto'>
        >>> mapping["EURUSD"]
        <MarketType.FOREX: 'forex'>
        >>> mapping["AAPL"]
        <MarketType.STOCKS: 'stocks'>
    """
    registry = ConfigRegistry()
    asset_to_market: dict[str, MarketType] = {}
    
    # Load all market configs
    for market_type in MarketType:
        market_config = registry.get_config(market_type)
        # Map each asset symbol to its market type
        for symbol in market_config.symbols:
            if symbol in asset_to_market:
                # Asset exists in multiple markets (shouldn't happen, but handle gracefully)
                # Keep the first one found, but this is a data integrity issue
                pass
            else:
                asset_to_market[symbol] = market_type
    
    return asset_to_market


def filter_market_config(
    market_config: MarketConfig,
    asset_symbols: list[str],
) -> MarketConfig:
    """
    Filter a MarketConfig to include only specified asset symbols.
    
    Creates a new MarketConfig with:
    - Only the requested assets
    - Filtered correlation matrix matching the filtered assets
    - Updated asset_order to match filtered symbols
    
    Args:
        market_config: Original market configuration.
        asset_symbols: List of asset symbols to include.
        
    Returns:
        New MarketConfig with only the specified assets.
        
    Raises:
        ValueError: If any asset symbol is not found in the market config.
        
    Example:
        >>> config = get_forex_config()
        >>> filtered = filter_market_config(config, ["EURUSD", "GBPUSD"])
        >>> len(filtered.assets)
        2
    """
    # Validate all symbols exist in the market config
    missing_symbols = [s for s in asset_symbols if s not in market_config.assets]
    if missing_symbols:
        raise ValueError(
            f"Assets not found in {market_config.market_type.value} market: {missing_symbols}"
        )
    
    # Filter assets dictionary
    filtered_assets = {symbol: market_config.assets[symbol] for symbol in asset_symbols}
    
    # Get correlation submatrix for filtered assets
    filtered_correlation = market_config.get_correlation_submatrix(asset_symbols)
    
    # Create new MarketConfig with filtered data
    return MarketConfig(
        market_type=market_config.market_type,
        assets=filtered_assets,
        correlation_matrix=filtered_correlation,
        asset_order=asset_symbols,
    )


def market_config_to_generator_config(
    market_config: MarketConfig,
    start_timestamp: int,
    end_timestamp: int,
    seed: Optional[int] = None,
    anomaly_types: Optional[frozenset[AnomalyType]] = None,
    timeframes: tuple[str, ...] = ("m1", "m5", "m15", "m30", "H1", "H4", "D1", "W1"),
    output_dir: str = "./output",
    show_progress: bool = True,
    batch_symbols: Optional[list[str]] = None,
) -> GeneratorConfig:
    """
    Convert a MarketConfig to a GeneratorConfig for the generator.
    
    Args:
        market_config: Market configuration with assets and correlations.
        start_timestamp: Start timestamp for generation.
        end_timestamp: End timestamp for generation.
        seed: Random seed for reproducibility.
        anomaly_types: Types of anomalies to inject.
        timeframes: Timeframes to generate.
        output_dir: Output directory.
        show_progress: Whether to show progress.
        batch_symbols: Optional subset of symbols to process (for batching).
        
    Returns:
        GeneratorConfig ready for the generator.
    """
    # Determine which symbols to use
    symbols = batch_symbols if batch_symbols else market_config.symbols
    
    # Convert AssetParams to AssetConfig
    asset_configs = []
    for symbol in symbols:
        params = market_config.get_asset(symbol)
        asset_configs.append(AssetConfig(
            symbol=params.symbol,
            start_price=params.start_price,
            volatility=params.volatility,
            drift=params.drift,
            volume_base=params.volume_base,
            volume_volatility=params.volume_volatility,
        ))
    
    # Get correlation submatrix for the batch
    correlation_matrix = market_config.get_correlation_submatrix(symbols)
    
    # Get market defaults for GARCH and regime params
    from marketforge.config.settings import MarketType as SettingsMarketType
    settings_market_type = SettingsMarketType(market_config.market_type.value)
    market_defaults = get_market_defaults(settings_market_type)
    
    # Build anomaly config
    if anomaly_types:
        anomaly_config = AnomalyConfig(types=anomaly_types)
    else:
        anomaly_config = market_defaults.anomaly_config
    
    return GeneratorConfig(
        assets=asset_configs,
        market_type=settings_market_type,
        start_timestamp=start_timestamp,
        end_timestamp=end_timestamp,
        correlation_matrix=correlation_matrix,
        garch_params=market_defaults.garch_params,
        regime_params=market_defaults.regime_params,
        anomaly_config=anomaly_config,
        output_dir=output_dir,
        seed=seed,
        timeframes=timeframes,
        show_progress=show_progress,
    )

