# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the MIT License. See the LICENSE file in the project
# root for full license information.

"""
Base configuration structures for market instruments.

Defines the core dataclasses used across all market configurations.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from marketforge.domain.markets import MarketType


@dataclass
class InstrumentParams:
    """
    Parameters for a single instrument.

    Attributes:
        symbol: Instrument symbol (e.g., 'EURUSD', 'BTCUSD', 'AAPL').
        start_price: Initial price.
        volatility: Annualized volatility (e.g., 0.25 for 25%).
        drift: Annualized log drift (e.g., 0.08).
        volume_base: Mean volume per open minute, in the market's unit:
            base-asset units (crypto), ticks (forex), shares (stocks).
        volume_volatility: Lognormal sigma of the volume noise.
        spread_bps: Typical quoted spread in basis points of the price (0.55
            is 0.6 pip on EURUSD). None: the market's rule, from volatility.
    """

    symbol: str
    start_price: float
    volatility: float
    drift: float = 0.0
    volume_base: float = 1000.0
    volume_volatility: float = 0.5
    spread_bps: float | None = None

    def __post_init__(self) -> None:
        """Validate instrument parameters."""
        if self.start_price <= 0:
            raise ValueError(f"start_price must be positive, got {self.start_price}")
        if self.volatility <= 0:
            raise ValueError(f"volatility must be positive, got {self.volatility}")
        if self.volume_base <= 0:
            raise ValueError(f"volume_base must be positive, got {self.volume_base}")
        if self.spread_bps is not None and self.spread_bps <= 0:
            raise ValueError(f"spread_bps must be positive, got {self.spread_bps}")


@dataclass
class MarketConfig:
    """
    Complete configuration for a market.

    Contains all instruments and their correlation matrix for a specific market type.

    Attributes:
        market_type: Type of market (forex, crypto, stocks).
        instruments: Dictionary mapping symbol to InstrumentParams.
        correlation_matrix: Full correlation matrix for all instruments.
        symbol_order: List of symbols defining matrix row/column order.
    """

    market_type: MarketType
    instruments: dict[str, InstrumentParams]
    correlation_matrix: np.ndarray
    symbol_order: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Validate market configuration."""
        if not self.symbol_order:
            self.symbol_order = list(self.instruments.keys())

        n_instruments = len(self.instruments)

        if self.correlation_matrix.shape != (n_instruments, n_instruments):
            raise ValueError(
                f"Correlation matrix shape {self.correlation_matrix.shape} "
                f"doesn't match number of instruments ({n_instruments})"
            )

        # Verify matrix is symmetric
        if not np.allclose(self.correlation_matrix, self.correlation_matrix.T, atol=1e-10):
            raise ValueError("Correlation matrix must be symmetric")

        # Verify diagonal is ones
        if not np.allclose(np.diag(self.correlation_matrix), 1.0, atol=1e-10):
            raise ValueError("Correlation matrix diagonal must be 1.0")

    @property
    def n_instruments(self) -> int:
        """Return number of instruments."""
        return len(self.instruments)

    @property
    def symbols(self) -> list[str]:
        """Return the instrument symbols in order."""
        return self.symbol_order

    def get_instrument(self, symbol: str) -> InstrumentParams:
        """Get instrument parameters by symbol."""
        return self.instruments[symbol]
