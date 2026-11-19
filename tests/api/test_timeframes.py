import numpy as np
import pandas as pd
import pytest

import marketforge as mf


def test_common_intraday_timeframes_can_be_generated():
    data = mf.generate(
        "EURUSD", start="2024-01-08", days=3, seed=1, timeframes="m1,m3,m10,H2,H8,H12"
    )
    assert list(data["EURUSD"]) == ["m1", "m3", "m10", "H2", "H8", "H12"]
    h12 = data["EURUSD"]["H12"]
    # Forex days start at 17:00 New York (22:00 UTC in winter): H12 at 22:00 and 10:00 UTC.
    assert set(h12.index.hour) == {22, 10}


@pytest.mark.parametrize(
    ("market", "symbol", "timeframe"),
    [("forex", "EURUSD", "H4"), ("stocks", "AAPL", "H1"), ("crypto", "BTCUSD", "m15")],
)
def test_resample_matches_generating_the_timeframe(market, symbol, timeframe):
    kwargs = {
        "start": "2024-01-08",
        "days": 5,
        "seed": 2,
        "include_regime": True,
        "include_spread": True,
    }
    data = mf.generate(symbol, timeframes=f"m1,{timeframe}", **kwargs)[symbol]
    got = mf.resample(data["m1"], timeframe, market)
    expected = data[timeframe]
    pd.testing.assert_index_equal(got.index, expected.index)
    numeric = ["open", "high", "low", "close", "volume", "spread"]
    np.testing.assert_allclose(got[numeric], expected[numeric], rtol=1e-12)
    pd.testing.assert_series_equal(got["regime"], expected["regime"])


def test_resample_drops_the_partial_candles_at_the_edges():
    m1 = mf.generate("BTCUSD", start="2024-01-08T00:30", end="2024-01-08T05:15", seed=3)["BTCUSD"][
        "m1"
    ]
    h1 = mf.resample(m1, "H1", "crypto")
    assert h1.index[0] == pd.Timestamp("2024-01-08T01:00Z") and h1.index[-1] == pd.Timestamp(
        "2024-01-08T04:00Z"
    )


@pytest.fixture(scope="module")
def aapl():
    return mf.generate(
        "AAPL", start="2024-01-08", days=5, seed=4, timeframes="m1,H1,D1", include_bid_ask=True
    )["AAPL"]


def test_resample_refuses_candles_that_are_not_m1(aapl):
    with pytest.raises(ValueError, match="needs m1 candles; these are 60 minutes apart"):
        mf.resample(aapl["H1"], "D1", "stocks")


def test_resample_refuses_candles_of_another_market(aapl):
    with pytest.raises(ValueError, match="1440 candle.s. fall in minutes when stocks is closed"):
        mf.resample(
            mf.generate("BTCUSD", start="2024-01-06", days=1, seed=1)["BTCUSD"]["m1"],
            "H1",
            "stocks",
        )
    # Crypto never closes, so stock candles read as crypto miss every night.
    with pytest.warns(UserWarning, match="miss .* open minute"):
        assert mf.resample(aapl["m1"], "D1", "crypto").empty


def test_resample_drops_the_candles_around_missing_minutes(aapl):
    holed = aapl["m1"].drop(aapl["m1"].index[100:160])  # an hour inside the first day
    with pytest.warns(UserWarning, match="miss 60 open minute"):
        d1 = mf.resample(holed, "D1", "stocks")
    assert list(d1.index) == list(aapl["D1"].index[1:])


def test_resample_keeps_bid_and_ask(aapl):
    d1 = mf.resample(aapl["m1"], "D1", "stocks")
    pd.testing.assert_frame_equal(d1, aapl["D1"], rtol=1e-12)
