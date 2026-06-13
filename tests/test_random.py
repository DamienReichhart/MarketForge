import numpy as np
from marketforge.utils.random import RandomState


def test_chisquare_mean_and_reproducibility():
    rng = RandomState(7)
    x = rng.chisquare(df=5, size=200_000)
    # E[chi2_k] = k
    assert abs(x.mean() - 5.0) < 0.1
    assert np.all(x > 0)

    rng.reset()
    y = rng.chisquare(df=5, size=10)
    rng2 = RandomState(7)
    z = rng2.chisquare(df=5, size=10)
    assert np.allclose(y, z)
