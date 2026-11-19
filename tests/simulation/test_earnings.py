import numpy as np
import pandas as pd
import pytest

import marketforge as mf
from marketforge.calendars.trading_calendar import get_calendar
from marketforge.domain.markets import MarketType
from marketforge.simulation.earnings import earnings_days, volatility_boost


def test_every_stock_reports_four_times_a_year_on_trading_days_of_its_own():
    nyse = get_calendar(MarketType.STOCKS)
    aapl, msft = earnings_days("AAPL", 2024, nyse), earnings_days("MSFT", 2024, nyse)
    assert len(aapl) == 4 and aapl != msft
    assert all(nyse.session_close_minute(np.array(aapl)) > 0)
    months = [pd.Timestamp(d * 86_400, unit="s").month for d in aapl]
    assert (
        months[0] in (1, 2)
        and months[1] in (4, 5)
        and months[2] in (7, 8)
        and months[3] in (10, 11)
    )


def test_volatility_is_raised_for_a_few_days_after_a_report():
    boost = volatility_boost(np.array([-1, 0, 1, 3, 9, 11]))
    assert boost[0] == 1.0 and boost[1] == 2.0 and boost[-1] == 1.0
    assert np.all(np.diff(boost[1:5]) < 0)


@pytest.fixture(scope="module")
def stocks():
    return mf.generate(
        "AAPL,NVDA,BTCUSD", start="2023-01-03", end="2024-01-01", seed=3, timeframes="D1"
    )


def test_the_open_after_a_report_gaps_more_than_other_opens(stocks):
    events = stocks.earnings()
    assert set(events["symbol"]) == {"AAPL", "NVDA"} and len(events) == 8
    for symbol in ("AAPL", "NVDA"):
        d1 = stocks[symbol]["D1"]
        gaps = pd.Series(
            np.log(d1["open"].to_numpy()[1:] / d1["close"].to_numpy()[:-1]), index=d1.index[1:]
        )
        on_report = gaps.index.normalize().isin(
            events.loc[events.symbol == symbol, "opens"].dt.normalize()
        )
        assert gaps[on_report].abs().mean() > 3 * gaps[~on_report].abs().mean()


def test_earnings_can_be_switched_off(stocks):
    # Without reports, the opens after the report days gap like any other
    # open (a crash regime may still gap 10% overnight: that is not a report).
    quiet = mf.generate(
        "AAPL",
        start="2023-01-03",
        end="2024-01-01",
        seed=3,
        timeframes="D1",
        overrides={"AAPL": {"earnings_move": 0.0}},
    )
    d1 = quiet["AAPL"]["D1"]
    gaps = pd.Series(
        np.abs(np.log(d1["open"].to_numpy()[1:] / d1["close"].to_numpy()[:-1])), index=d1.index[1:]
    )
    assert quiet.earnings().empty  # nothing was reported
    events = stocks.earnings()
    opens = events.loc[events.symbol == "AAPL", "opens"].dt.normalize()
    on_report = gaps.index.normalize().isin(opens)
    assert on_report.sum() == 4
    assert gaps[on_report].mean() < 2 * gaps[~on_report].mean()
