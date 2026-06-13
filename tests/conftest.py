"""Shared pytest fixtures for MarketForge tests."""
import numpy as np
import pytest

from marketforge.utils.random import RandomState


@pytest.fixture
def rng():
    return RandomState(42)


@pytest.fixture
def small_corr():
    """A simple 3-asset positive-definite correlation matrix."""
    return np.array([
        [1.0, 0.6, 0.3],
        [0.6, 1.0, 0.5],
        [0.3, 0.5, 1.0],
    ])
