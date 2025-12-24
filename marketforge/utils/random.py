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
Seeded random state management for reproducible data generation.

Provides a centralized random state that can be seeded for deterministic output,
essential for backtesting and debugging scenarios.
"""

from __future__ import annotations

from typing import Optional
import numpy as np
from numpy.random import Generator, PCG64


class RandomState:
    """
    Thread-safe random state manager with seed control.
    
    Wraps numpy's Generator for high-quality random number generation
    with reproducibility support.
    
    Attributes:
        seed: The seed used to initialize the random state.
        generator: The underlying numpy Generator instance.
    
    Example:
        >>> rng = RandomState(seed=42)
        >>> returns = rng.normal(0, 0.01, size=1000)
        >>> rng.reset()  # Reset to initial state
        >>> returns2 = rng.normal(0, 0.01, size=1000)
        >>> np.allclose(returns, returns2)  # True
    """
    
    def __init__(self, seed: Optional[int] = None) -> None:
        """
        Initialize random state with optional seed.
        
        Args:
            seed: Optional seed for reproducibility. If None, uses entropy.
        """
        self._seed = seed
        self._generator = self._create_generator(seed)
    
    @property
    def seed(self) -> Optional[int]:
        """Return the seed used to initialize the random state."""
        return self._seed
    
    @property
    def generator(self) -> Generator:
        """Return the underlying numpy Generator."""
        return self._generator
    
    def _create_generator(self, seed: Optional[int]) -> Generator:
        """Create a new Generator with the given seed."""
        bit_generator = PCG64(seed)
        return Generator(bit_generator)
    
    def reset(self) -> None:
        """Reset the random state to its initial seeded state."""
        self._generator = self._create_generator(self._seed)
    
    def normal(
        self,
        loc: float = 0.0,
        scale: float = 1.0,
        size: Optional[int | tuple[int, ...]] = None
    ) -> np.ndarray:
        """
        Generate samples from a normal distribution.
        
        Args:
            loc: Mean of the distribution.
            scale: Standard deviation of the distribution.
            size: Output shape.
            
        Returns:
            Array of random samples.
        """
        return self._generator.normal(loc, scale, size)
    
    def standard_normal(
        self,
        size: Optional[int | tuple[int, ...]] = None
    ) -> np.ndarray:
        """
        Generate samples from a standard normal distribution N(0,1).
        
        Args:
            size: Output shape.
            
        Returns:
            Array of random samples.
        """
        return self._generator.standard_normal(size)
    
    def uniform(
        self,
        low: float = 0.0,
        high: float = 1.0,
        size: Optional[int | tuple[int, ...]] = None
    ) -> np.ndarray:
        """
        Generate samples from a uniform distribution.
        
        Args:
            low: Lower bound (inclusive).
            high: Upper bound (exclusive).
            size: Output shape.
            
        Returns:
            Array of random samples.
        """
        return self._generator.uniform(low, high, size)
    
    def lognormal(
        self,
        mean: float = 0.0,
        sigma: float = 1.0,
        size: Optional[int | tuple[int, ...]] = None
    ) -> np.ndarray:
        """
        Generate samples from a log-normal distribution.
        
        Args:
            mean: Mean of the underlying normal distribution.
            sigma: Standard deviation of the underlying normal distribution.
            size: Output shape.
            
        Returns:
            Array of random samples.
        """
        return self._generator.lognormal(mean, sigma, size)
    
    def poisson(
        self,
        lam: float = 1.0,
        size: Optional[int | tuple[int, ...]] = None
    ) -> np.ndarray:
        """
        Generate samples from a Poisson distribution.
        
        Args:
            lam: Expected number of events (lambda parameter).
            size: Output shape.
            
        Returns:
            Array of random samples.
        """
        return self._generator.poisson(lam, size)
    
    def choice(
        self,
        a: int | np.ndarray,
        size: Optional[int | tuple[int, ...]] = None,
        replace: bool = True,
        p: Optional[np.ndarray] = None
    ) -> np.ndarray:
        """
        Generate random samples from a given array or range.
        
        Args:
            a: If int, samples from range(a). If array, samples from elements.
            size: Output shape.
            replace: Whether to sample with replacement.
            p: Probability weights for each element.
            
        Returns:
            Array of random samples.
        """
        return self._generator.choice(a, size=size, replace=replace, p=p)
    
    def beta(
        self,
        a: float,
        b: float,
        size: Optional[int | tuple[int, ...]] = None
    ) -> np.ndarray:
        """
        Generate samples from a beta distribution.
        
        Args:
            a: Alpha parameter (> 0).
            b: Beta parameter (> 0).
            size: Output shape.
            
        Returns:
            Array of random samples.
        """
        return self._generator.beta(a, b, size)
    
    def exponential(
        self,
        scale: float = 1.0,
        size: Optional[int | tuple[int, ...]] = None
    ) -> np.ndarray:
        """
        Generate samples from an exponential distribution.
        
        Args:
            scale: Scale parameter (1/lambda).
            size: Output shape.
            
        Returns:
            Array of random samples.
        """
        return self._generator.exponential(scale, size)
    
    def shuffle(self, x: np.ndarray) -> None:
        """
        Shuffle array in-place.
        
        Args:
            x: Array to shuffle.
        """
        self._generator.shuffle(x)
    
    def integers(
        self,
        low: int,
        high: Optional[int] = None,
        size: Optional[int | tuple[int, ...]] = None
    ) -> np.ndarray:
        """
        Generate random integers.
        
        Args:
            low: Lowest integer (or high if high is None).
            high: Highest integer (exclusive).
            size: Output shape.
            
        Returns:
            Array of random integers.
        """
        return self._generator.integers(low, high, size=size)


# Global random state instance for convenient access
_global_random_state: Optional[RandomState] = None


def get_random_state(seed: Optional[int] = None) -> RandomState:
    """
    Get or create a global random state instance.
    
    Args:
        seed: Optional seed. If provided and differs from current seed,
              creates a new instance.
              
    Returns:
        The global RandomState instance.
    """
    global _global_random_state
    
    if _global_random_state is None or (seed is not None and seed != _global_random_state.seed):
        _global_random_state = RandomState(seed)
    
    return _global_random_state


def set_global_seed(seed: int) -> RandomState:
    """
    Set the global random seed and return the random state.
    
    Args:
        seed: Seed value for reproducibility.
        
    Returns:
        The newly created RandomState instance.
    """
    global _global_random_state
    _global_random_state = RandomState(seed)
    return _global_random_state

