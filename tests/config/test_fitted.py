"""The shipped correlation fits: daily matrix, minute matrix and the map between them."""

import numpy as np
import pandas as pd
import pytest

import marketforge as mf
from marketforge.config.catalog.fitted import horizon_table, minute_correlation
from marketforge.domain.markets import MarketType


def test_the_horizon_table_is_monotone_and_keeps_zero_and_the_bounds():
    rng = np.random.default_rng(0)
    minute = np.clip(rng.uniform(0.2, 0.9, (6, 6)), -1, 1)
    minute = (minute + minute.T) / 2
    np.fill_diagonal(minute, 1.0)
    daily = 0.7 * minute + 0.25  # common moves add to every pair
    np.fill_diagonal(daily, 1.0)
    days, minutes = horizon_table(daily, minute)
    assert days[0] == -1.0 and days[-1] == 1.0 and 0.0 in days
    assert minutes[days.index(0.0)] == 0.0
    assert np.all(np.diff(days) > 0) and np.all(np.diff(minutes) >= 0)


@pytest.mark.parametrize("market", list(MarketType))
def test_a_daily_correlation_maps_to_a_minute_one_within_bounds(market):
    assert minute_correlation(market, 0.0) == 0.0
    assert -0.99 <= minute_correlation(market, -0.999) <= minute_correlation(market, 0.999) <= 0.99
    # Common moves (trends, stress) correlate days more than minutes.
    assert minute_correlation(market, 0.6) <= 0.6 + 1e-9


def test_an_override_correlation_is_what_daily_returns_show():
    data = mf.generate(
        "BTCUSD,ETHUSD", start="2018-01-01", end="2022-01-01", seed=5, timeframes="D1",
        overrides={"ETHUSD": {"correlations": {"BTCUSD": 0.6}}},
    )  # fmt: skip
    closes = pd.DataFrame({s: data[s]["D1"]["close"] for s in data.symbols})
    daily = np.log(closes).diff().dropna().corr().iloc[0, 1]
    assert daily == pytest.approx(0.6, abs=0.08)
