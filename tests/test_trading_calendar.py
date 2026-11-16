import datetime as dt

import numpy as np
import pytest

from marketforge.config.settings import MarketType
from marketforge.trading_calendar import (
    get_calendar,
    nyse_early_closes,
    nyse_holidays,
)


def _ts(s: str) -> int:
    return int(dt.datetime.fromisoformat(s).replace(tzinfo=dt.timezone.utc).timestamp())


def test_nyse_holidays_2024():
    expected = {
        dt.date(2024, 1, 1), dt.date(2024, 1, 15), dt.date(2024, 2, 19),
        dt.date(2024, 3, 29), dt.date(2024, 5, 27), dt.date(2024, 6, 19),
        dt.date(2024, 7, 4), dt.date(2024, 9, 2), dt.date(2024, 11, 28),
        dt.date(2024, 12, 25),
    }
    assert nyse_holidays(2024) == expected


def test_nyse_observance_rules():
    # Christmas 2022 fell on a Sunday -> observed Monday Dec 26.
    assert dt.date(2022, 12, 26) in nyse_holidays(2022)
    # New Year 2022 fell on a Saturday -> NOT observed on Friday Dec 31 2021.
    assert dt.date(2021, 12, 31) not in nyse_holidays(2021)
    assert not any(d.year == 2022 and d.month == 1 and d.day < 3 for d in nyse_holidays(2022))
    # Juneteenth only from 2022.
    assert dt.date(2021, 6, 18) not in nyse_holidays(2021)


def test_nyse_early_closes_2024():
    assert nyse_early_closes(2024) == {
        dt.date(2024, 7, 3), dt.date(2024, 11, 29), dt.date(2024, 12, 24),
    }


def test_crypto_is_always_open():
    cal = get_calendar(MarketType.CRYPTO)
    ts = cal.open_minutes(_ts("2024-01-06T00:00"), _ts("2024-01-08T00:00"))
    assert ts.size == 2 * 1440


def test_stocks_regular_session_respects_dst():
    cal = get_calendar(MarketType.STOCKS)
    # Winter: 09:30-16:00 New York == 14:30-21:00 UTC.
    jan = cal.open_minutes(_ts("2024-01-03T00:00"), _ts("2024-01-04T00:00"))
    assert jan.size == 390
    assert jan[0] == _ts("2024-01-03T14:30") and jan[-1] == _ts("2024-01-03T20:59")
    # Summer: 13:30-20:00 UTC.
    jul = cal.open_minutes(_ts("2024-07-10T00:00"), _ts("2024-07-11T00:00"))
    assert jul[0] == _ts("2024-07-10T13:30") and jul.size == 390


def test_stocks_closed_on_weekends_holidays_and_early_close():
    cal = get_calendar(MarketType.STOCKS)
    weekend = cal.open_minutes(_ts("2024-01-06T00:00"), _ts("2024-01-08T00:00"))
    assert weekend.size == 0
    assert cal.open_minutes(_ts("2024-07-04T00:00"), _ts("2024-07-05T00:00")).size == 0
    early = cal.open_minutes(_ts("2024-11-29T00:00"), _ts("2024-11-30T00:00"))
    assert early.size == 210  # 09:30-13:00


def test_stocks_trading_minutes_per_year():
    cal = get_calendar(MarketType.STOCKS)
    n = cal.count_open_minutes(_ts("2024-01-01T00:00"), _ts("2025-01-01T00:00"))
    # 252 trading days, 3 of them early closes.
    assert n == 252 * 390 - 3 * 180


def test_forex_week_is_sunday_to_friday_17h_new_york():
    cal = get_calendar(MarketType.FOREX)
    # Winter: opens Sunday 22:00 UTC, closes Friday 22:00 UTC.
    week = cal.open_minutes(_ts("2024-01-05T00:00"), _ts("2024-01-15T00:00"))
    sat = (week >= _ts("2024-01-06T00:00")) & (week < _ts("2024-01-07T00:00"))
    assert not sat.any()
    assert _ts("2024-01-05T21:59") in week and _ts("2024-01-05T22:00") not in week
    assert _ts("2024-01-07T21:59") not in week and _ts("2024-01-07T22:00") in week
    # Summer: one hour earlier in UTC.
    summer = cal.open_minutes(_ts("2024-07-05T00:00"), _ts("2024-07-08T00:00"))
    assert _ts("2024-07-05T20:59") in summer and _ts("2024-07-05T21:00") not in summer
    assert _ts("2024-07-07T21:00") in summer


def test_forex_open_minutes_per_week():
    cal = get_calendar(MarketType.FOREX)
    n = cal.count_open_minutes(_ts("2024-01-08T00:00"), _ts("2024-01-15T00:00"))
    assert n == 5 * 1440


@pytest.mark.parametrize(
    "market,when,anchor_midnight_utc",
    [
        (MarketType.CRYPTO, "2024-01-03T00:00", True),
        (MarketType.FOREX, "2024-01-02T22:00", True),   # 17:00 New York (EST)
        (MarketType.STOCKS, "2024-01-03T14:30", True),  # 09:30 New York (EST)
        (MarketType.FOREX, "2024-07-02T21:00", True),   # 17:00 New York (EDT)
    ],
)
def test_bar_anchor_puts_session_start_at_midnight(market, when, anchor_midnight_utc):
    cal = get_calendar(market)
    m = cal.anchor_minutes(np.array([_ts(when)]))[0]
    assert (m % 1440 == 0) == anchor_midnight_utc
