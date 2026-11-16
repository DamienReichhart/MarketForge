import datetime as dt

import numpy as np
import pytest

from marketforge.config.loader import load_market_config
from marketforge.config.settings import AnomalyType, MarketType
from marketforge.engine import DayResult, MarketSimulator, build_market_spec

JAN_1_2024 = 1704067200
DAY = 86400


def _run(market: str, seed: int, start: int, end: int, anomalies=frozenset()) -> DayResult:
    spec = build_market_spec(load_market_config(market), anomalies)
    days = list(MarketSimulator(spec, seed).run(start, end))
    return DayResult(
        timestamps=np.concatenate([d.timestamps for d in days]),
        open=np.vstack([d.open for d in days]),
        high=np.vstack([d.high for d in days]),
        low=np.vstack([d.low for d in days]),
        close=np.vstack([d.close for d in days]),
        volume=np.vstack([d.volume for d in days]),
        regime=np.concatenate([d.regime for d in days]),
    )


@pytest.fixture(scope="module")
def stocks_two_weeks():
    return _run("stocks", 11, JAN_1_2024, JAN_1_2024 + 14 * DAY)


@pytest.mark.parametrize("market", ["crypto", "forex", "stocks"])
def test_ohlc_invariants(market):
    r = _run(market, 3, JAN_1_2024, JAN_1_2024 + 3 * DAY)
    assert np.all(r.high >= np.maximum(r.open, r.close))
    assert np.all(r.low <= np.minimum(r.open, r.close))
    assert np.all(r.low > 0) and np.all(r.volume > 0)
    assert np.all(np.diff(r.timestamps) > 0)


def test_same_seed_same_output_and_different_seed_differs():
    a = _run("crypto", 5, JAN_1_2024, JAN_1_2024 + DAY)
    b = _run("crypto", 5, JAN_1_2024, JAN_1_2024 + DAY)
    c = _run("crypto", 6, JAN_1_2024, JAN_1_2024 + DAY)
    np.testing.assert_array_equal(a.close, b.close)
    assert not np.allclose(a.close, c.close)


@pytest.mark.parametrize("market", ["crypto", "forex", "stocks"])
def test_extending_the_range_never_changes_earlier_candles(market):
    short = _run(market, 9, JAN_1_2024, JAN_1_2024 + 3 * DAY + 5000)
    long = _run(market, 9, JAN_1_2024, JAN_1_2024 + 6 * DAY)
    n = short.timestamps.size
    np.testing.assert_array_equal(short.timestamps, long.timestamps[:n])
    for field in ("open", "high", "low", "close", "volume"):
        np.testing.assert_array_equal(getattr(short, field), getattr(long, field)[:n])


def test_stocks_have_no_candles_outside_the_nyse_session(stocks_two_weeks):
    ts = stocks_two_weeks.timestamps
    when = [dt.datetime.fromtimestamp(int(t), dt.timezone.utc) for t in ts[::30]]
    assert all(w.weekday() < 5 for w in when)
    # 2024-01-01 and 2024-01-15 are NYSE holidays; 9 sessions remain.
    assert ts.size == 9 * 390


def test_stocks_gap_only_at_session_open(stocks_two_weeks):
    r = stocks_two_weeks
    jumps = r.open[1:] != r.close[:-1]
    new_session = np.diff(r.timestamps) > 60
    assert not jumps[~new_session].any()
    assert jumps[new_session].all()


def test_forex_has_no_saturday_candles_and_crosses_are_arbitrage_free():
    r = _run("forex", 2, JAN_1_2024, JAN_1_2024 + 7 * DAY)
    sat = [dt.datetime.fromtimestamp(int(t), dt.timezone.utc).weekday() == 5 for t in r.timestamps]
    assert not any(sat)
    syms = build_market_spec(load_market_config("forex")).symbols
    i, j, k = (syms.index(s) for s in ("EURJPY", "EURUSD", "USDJPY"))
    np.testing.assert_allclose(r.close[:, i], r.close[:, j] * r.close[:, k], rtol=1e-12)
    np.testing.assert_allclose(r.open[:, i], r.open[:, j] * r.open[:, k], rtol=1e-12)


def test_no_minute_dominates_volume(stocks_two_weeks):
    v = stocks_two_weeks.volume
    # v2 put ~50% of a period's volume in one minute; turbulent minutes may still
    # reach a few hundred times the median, as in real markets.
    assert (v.max(axis=0) / v.sum(axis=0)).max() < 0.05


def test_spikes_and_flash_crashes_are_injected():
    base = _run("crypto", 4, JAN_1_2024, JAN_1_2024 + 5 * DAY)
    spiky = _run(
        "crypto",
        4,
        JAN_1_2024,
        JAN_1_2024 + 5 * DAY,
        frozenset({AnomalyType.SPIKES, AnomalyType.FLASH_CRASH}),
    )
    np.testing.assert_array_equal(base.timestamps, spiky.timestamps)
    wick = (spiky.high - spiky.low) / (base.high - base.low)
    assert (wick > 2).sum() > 10
    assert np.all(spiky.high >= np.maximum(spiky.open, spiky.close))
    assert np.all(spiky.low <= np.minimum(spiky.open, spiky.close))


def test_regime_labels_cover_known_states():
    r = _run("crypto", 1, JAN_1_2024, JAN_1_2024 + DAY)
    assert set(np.unique(r.regime)) <= set(range(5))


def test_negative_seed_is_rejected():
    spec = build_market_spec(load_market_config(MarketType.CRYPTO))
    with pytest.raises(ValueError):
        MarketSimulator(spec, -1)


def test_regimes_persist_for_hours():
    r = _run("crypto", 8, JAN_1_2024, JAN_1_2024 + 14 * DAY)
    switches = np.count_nonzero(np.diff(r.regime))
    assert r.regime.size / max(switches, 1) > 120  # mean regime length > 2 h


def test_volume_units_per_market():
    fx = _run("forex", 1, JAN_1_2024 + DAY, JAN_1_2024 + 2 * DAY)
    assert np.all(fx.volume == np.rint(fx.volume)) and fx.volume.min() >= 1
    syms = build_market_spec(load_market_config("forex")).symbols
    eurusd = fx.volume[:, syms.index("EURUSD")]
    assert 20 < eurusd.mean() < 150  # ticks per minute
    btc = _run("crypto", 1, JAN_1_2024, JAN_1_2024 + DAY)
    i = build_market_spec(load_market_config("crypto")).symbols.index("BTCUSD")
    assert 5 < btc.volume[:, i].mean() < 80  # BTC per minute
