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


def _subset_matches_full(spec, symbols, start, end, seed=4):
    full = list(MarketSimulator(spec, seed).run(start, end))
    sub = MarketSimulator(spec, seed, instruments=symbols)
    assert sub.instruments == tuple(symbols)
    cols = [spec.symbols.index(s) for s in symbols]
    days = list(sub.run(start, end))
    assert len(days) == len(full)
    for a, b in zip(days, full, strict=True):
        np.testing.assert_array_equal(a.timestamps, b.timestamps)
        np.testing.assert_array_equal(a.regime, b.regime)
        for field in ("open", "high", "low", "close", "volume"):
            np.testing.assert_array_equal(getattr(a, field), getattr(b, field)[:, cols])


@pytest.mark.parametrize(
    ("market", "symbols"),
    [
        ("crypto", ["SOLUSD", "BTCUSD"]),  # identity projection, reordered
        ("stocks", ["MSFT"]),
        ("forex", ["GBPJPY", "EURUSD", "AUDNZD", "USDCHF"]),  # anchors and two-term crosses
    ],
)
def test_simulating_a_subset_is_bit_identical_to_the_whole_market(market, symbols):
    anomalies = frozenset({AnomalyType.SPIKES, AnomalyType.FLASH_CRASH})
    spec = build_market_spec(load_market_config(market), anomalies)
    _subset_matches_full(spec, symbols, JAN_1_2024, JAN_1_2024 + 4 * DAY)


def test_subset_of_a_forex_structure_with_three_term_crosses(tmp_path):
    from marketforge.config.loader import load_catalog

    # GRX is linked to USD through EUR, so GRXJPY = GRXEUR + EURUSD + USDJPY:
    # the general (matrix product) projection.
    cfg = tmp_path / "o.toml"
    cfg.write_text(
        '[instruments.GRXJPY]\nmarket = "forex"\nstart_price = 650000\nvolatility = 0.2\n'
    )
    spec = build_market_spec(load_catalog(cfg)[MarketType.FOREX])
    row = spec.structure.weights[spec.symbols.index("GRXJPY")]
    assert np.count_nonzero(row) == 3
    _subset_matches_full(spec, ["GRXJPY", "EURJPY"], JAN_1_2024, JAN_1_2024 + 3 * DAY)


def test_instrument_selection_is_validated():
    spec = build_market_spec(load_market_config("crypto"))
    with pytest.raises(ValueError, match="Not instruments"):
        MarketSimulator(spec, 1, instruments=["AAPL"])
    with pytest.raises(ValueError, match="Duplicate"):
        MarketSimulator(spec, 1, instruments=["BTCUSD", "BTCUSD"])
    with pytest.raises(ValueError, match="At least one"):
        MarketSimulator(spec, 1, instruments=[])


def test_cached_regime_calibration_is_shared_but_never_mutated():
    spec = build_market_spec(load_market_config("stocks"))
    a, b = MarketSimulator(spec, 1), MarketSimulator(spec, 2)
    np.testing.assert_array_equal(a._regime_vol, b._regime_vol)
    a._regime_vol[0] = -1.0  # a private copy: the cache and other simulators are untouched
    assert MarketSimulator(spec, 3)._regime_vol[0] != -1.0 and b._regime_vol[0] != -1.0


def test_flash_crash_dips_and_recovers():
    # Seed 0 crashes XRPUSD on 2024-01-03 (crypto: 0.2% chance per instrument-day).
    spec_crash = build_market_spec(
        load_market_config("crypto"), frozenset({AnomalyType.FLASH_CRASH})
    )
    spec_base = build_market_spec(load_market_config("crypto"))
    start, end = JAN_1_2024 + DAY, JAN_1_2024 + 4 * DAY
    crash = np.vstack([d.close for d in MarketSimulator(spec_crash, 0, ["XRPUSD"]).run(start, end)])
    base = np.vstack([d.close for d in MarketSimulator(spec_base, 0, ["XRPUSD"]).run(start, end)])
    ratio = (crash / base)[:, 0]
    hit = np.nonzero(ratio != 1.0)[0]
    assert 0 < hit.size <= spec_crash.anomaly.flash_crash_recovery_candles
    assert ratio.min() == pytest.approx(1.0 - spec_crash.anomaly.flash_crash_magnitude)
    assert np.all(np.diff(hit) == 1)  # one contiguous episode, back to the base path after
