import numpy as np
import pandas as pd
import pytest

import marketforge as mf


@pytest.fixture(scope="module")
def decade():
    return mf.generate(
        "USDHKD,EURDKK,USDCNH", start="2014-01-01", end="2024-01-01", seed=5, timeframes="D1"
    )


def test_the_hong_kong_dollar_stays_in_its_band(decade):
    close = decade["USDHKD"]["D1"]
    assert close["low"].min() >= 7.75 * 0.9995 and close["high"].max() <= 7.85 * 1.0005


def test_the_krone_stays_within_erm_ii_of_the_euro(decade):
    close = decade["EURDKK"]["D1"]["close"]
    assert np.abs(close / 7.46038 - 1).max() <= 0.0226


def test_the_yuan_is_managed_not_pegged(decade):
    close = decade["USDCNH"]["D1"]["close"]
    start = mf.instruments("forex").loc["USDCNH", "start_price"]
    assert close.std() / close.mean() > 0.005  # it moves
    assert np.abs(close / start - 1).max() <= 0.081


def test_a_peg_does_not_depend_on_what_else_is_requested():
    kwargs = {"start": "2020-01-01", "days": 30, "seed": 5, "timeframes": "H1"}
    alone = mf.generate("USDDKK", **kwargs)["USDDKK"]["H1"]
    beside = mf.generate("USDDKK,EURUSD,EURDKK", **kwargs)["USDDKK"]["H1"]
    pd.testing.assert_frame_equal(alone, beside)


def test_forex_is_thin_on_christmas_and_new_years_day():
    m1 = mf.generate("EURUSD", start="2023-12-18", days=21, seed=5, timeframes="m1")["EURUSD"]["m1"]
    ny = m1.index.tz_convert("America/New_York")
    returns = np.log(m1["close"] / m1["open"])
    by_day = returns.groupby(ny.date).std()
    normal = by_day.median()
    assert by_day[pd.Timestamp("2023-12-25").date()] < 0.6 * normal
    assert by_day[pd.Timestamp("2024-01-01").date()] < 0.6 * normal
