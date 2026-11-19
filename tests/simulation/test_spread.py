import numpy as np
import pytest

from marketforge.calendars.trading_calendar import get_calendar
from marketforge.config.loader import load_catalog, load_market_config
from marketforge.domain.bars import Bars
from marketforge.domain.markets import MarketType
from marketforge.simulation.simulator import MarketSimulator
from marketforge.simulation.spec import build_market_spec
from marketforge.simulation.spread import minutes_since_reopen
from tests.support import simulate_days

DAY = 86400
JAN_1_2024 = 1704067200  # a Monday


def _run(market, symbols, days=14, end_offset=0, spread=True, catalog=None):
    config = (catalog or load_catalog())[MarketType(market)]
    sim = MarketSimulator(build_market_spec(config), 11, symbols, spread=spread)
    return Bars.concat(simulate_days(sim, JAN_1_2024, JAN_1_2024 + days * DAY + end_offset))


@pytest.mark.parametrize(
    ("market", "symbols"),
    [
        ("crypto", ["BTCUSD", "DOGEUSD"]),
        ("forex", ["EURUSD", "EURJPY"]),
        ("stocks", ["AAPL", "VZ"]),
    ],
)
def test_spread_is_positive_and_leaves_every_candle_untouched(market, symbols):
    quoted, plain = _run(market, symbols), _run(market, symbols, spread=False)
    assert plain.spread is None
    assert quoted.spread.shape == quoted.close.shape and np.all(quoted.spread > 0)
    for field in ("timestamps", "open", "high", "low", "close", "volume", "regime"):
        np.testing.assert_array_equal(getattr(quoted, field), getattr(plain, field))


def test_spread_does_not_depend_on_the_selection_or_the_end_of_the_range():
    both = _run("forex", ["EURUSD", "EURJPY"])
    alone = _run("forex", ["EURJPY"])
    np.testing.assert_array_equal(alone.spread[:, 0], both.spread[:, 1])
    cut = _run("forex", ["EURUSD", "EURJPY"], days=9, end_offset=15 * 3600 + 420)
    np.testing.assert_array_equal(cut.spread, both.spread[: len(cut)])


def test_typical_levels_follow_the_catalog_or_the_market_rule():
    def median_bps(bars):
        return 1e4 * np.median(bars.spread / bars.close, axis=0)

    eurusd, usdtry = median_bps(_run("forex", ["EURUSD", "USDTRY"]))
    assert 0.3 < eurusd < 0.9  # about 0.6 pip
    assert usdtry > 5 * eurusd  # exotics are far wider than majors
    custom = load_catalog({"EURUSD": {"spread_bps": 2.2}})
    assert median_bps(_run("forex", ["EURUSD"], catalog=custom))[0] == pytest.approx(
        4 * eurusd, rel=1e-9
    )


def test_stock_spreads_never_go_below_one_cent_and_widen_at_the_open():
    bars = _run("stocks", ["AAPL", "VZ"])
    assert bars.spread.min() == 0.01
    opening = np.diff(bars.timestamps, prepend=0) > 60  # first minute of each session
    assert opening.sum() == 9  # trading days in two weeks with New Year's Day off
    aapl, vz = bars.spread[:, 0], bars.spread[:, 1]
    assert aapl[opening].mean() > 2 * np.median(aapl)
    assert np.all(vz[opening] == 0.01)  # a $42 stock stays one cent wide even then


def test_forex_spreads_widen_when_the_week_opens():
    bars = _run("forex", ["EURUSD"], days=7)
    week_open = np.nonzero(np.diff(bars.timestamps) > 3600)[0] + 1
    assert week_open.size == 1
    first_minutes = bars.spread[week_open[0] : week_open[0] + 5, 0].mean()
    assert first_minutes > 2.5 * np.median(bars.spread)


def test_spread_widens_with_turbulence():
    bars = _run("forex", ["EURUSD"], days=90)
    relative = bars.spread[:, 0] / bars.close[:, 0]
    calm, wild = np.isin(bars.regime, [2]), np.isin(bars.regime, [3, 4])  # range vs high vol/crash
    assert calm.any() and wild.any()
    assert relative[wild].mean() > 1.3 * relative[calm].mean()


def test_crypto_spreads_sit_on_a_tick_like_the_measured_ones():
    # Binance futures, Feb 2024: 0.024 bp on BTC (at 43k), 1.2 bp on DOGE, and
    # a 99th percentile within 1.02-2.2 times the median.
    bars = _run("crypto", ["BTCUSD", "DOGEUSD"], days=30)
    btc, doge = 1e4 * np.median(bars.spread / bars.close, axis=0)
    assert 0.012 < btc < 0.04 and 0.6 < doge < 2.4
    assert np.all(np.quantile(bars.spread, 0.99, axis=0) < 1.5 * np.median(bars.spread, axis=0))
    # A tick is a price increment: the spread does not follow the price down.
    cheap = bars.close[:, 1] < np.quantile(bars.close[:, 1], 0.2)
    assert np.median(bars.spread[cheap, 1]) == pytest.approx(np.median(bars.spread[:, 1]), rel=0.05)


def test_minutes_since_reopen_counts_from_the_first_open_minute():
    nyse = minutes_since_reopen(get_calendar(MarketType.STOCKS), JAN_1_2024 // DAY + 1)
    assert nyse[14 * 60 + 30] == 1 and nyse[14 * 60 + 31] == 2  # 09:30 New York
    always_open = minutes_since_reopen(get_calendar(MarketType.CRYPTO), JAN_1_2024 // DAY)
    assert always_open.min() > 200  # never reopened: no widening


def test_only_the_selected_market_config_is_needed():
    assert load_market_config("stocks").get_instrument("AAPL").spread_bps is None
