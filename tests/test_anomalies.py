# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the MIT License. See the LICENSE file in the project
# root for full license information.

"""Guard tests for anomaly injection vectorization (Task 11)."""

import numpy as np
from marketforge.config.settings import AnomalyConfig, AnomalyType, MarketType
from marketforge.generators.anomalies import AnomalyInjector
from marketforge.generators.ohlcv import OHLCVData
from marketforge.utils.random import RandomState


def _ohlcv(n=10000):
    rng = RandomState(1)
    close = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.001, n)))
    openp = np.concatenate([[close[0]], close[:-1]])
    high = np.maximum(openp, close) * 1.0005
    low = np.minimum(openp, close) * 0.9995
    vol = np.full(n, 1000.0)
    ts = np.arange(n, dtype=np.int64) * 60
    return OHLCVData("X", ts, openp, high, low, close, vol)


def test_invariants_hold_after_spike_injection():
    cfg = AnomalyConfig(types=frozenset({AnomalyType.SPIKES}), spike_probability=0.01)
    inj = AnomalyInjector(cfg, market_type=MarketType.CRYPTO)
    out, report = inj.inject(RandomState(2), _ohlcv())
    out.validate()
    assert report.n_events > 0


def test_spike_injection_is_reproducible():
    cfg = AnomalyConfig(types=frozenset({AnomalyType.SPIKES}), spike_probability=0.01)
    inj = AnomalyInjector(cfg, market_type=MarketType.CRYPTO)
    a, _ = inj.inject(RandomState(5), _ohlcv())
    b, _ = inj.inject(RandomState(5), _ohlcv())
    assert np.allclose(a.high, b.high) and np.allclose(a.low, b.low)


def test_invariants_hold_after_gap_injection():
    cfg = AnomalyConfig(types=frozenset({AnomalyType.GAPS}), gap_probability=0.01)
    inj = AnomalyInjector(cfg, market_type=MarketType.STOCKS)
    out, report = inj.inject(RandomState(3), _ohlcv())
    out.validate()
