import numpy as np
import pytest

from marketforge.core.seasonality import SessionSeasonality
from marketforge.domain.markets import MarketType
from marketforge.trading_calendar import get_calendar

JAN_1_2024 = 1704067200


@pytest.mark.parametrize("market", list(MarketType))
def test_factor_is_positive_and_variance_neutral_over_a_year(market):
    cal = get_calendar(market)
    ts = cal.open_minutes(JAN_1_2024, JAN_1_2024 + 365 * 86400)
    f = SessionSeasonality(cal).factor(ts)
    assert np.all(f > 0)
    assert abs(np.mean(f**2) - 1.0) < 0.02


def test_stocks_are_u_shaped_and_window_independent():
    cal = get_calendar(MarketType.STOCKS)
    model = SessionSeasonality(cal)
    day = cal.open_minutes(1704240000, 1704326400)  # 2024-01-03, one session
    week = cal.open_minutes(JAN_1_2024, JAN_1_2024 + 7 * 86400)
    np.testing.assert_allclose(model.factor(day), model.factor(week[np.isin(week, day)]))
    f = model.factor(day)
    mid = f[len(f) // 2]
    assert f[0] > 1.3 * mid and f[-1] > 1.2 * mid


def test_crypto_weekend_is_quieter_than_weekdays():
    cal = get_calendar(MarketType.CRYPTO)
    ts = cal.open_minutes(JAN_1_2024, JAN_1_2024 + 7 * 86400)  # Monday..Sunday
    f = SessionSeasonality(cal).factor(ts)
    weekday = ((ts // 86400) + 3) % 7
    assert f[weekday >= 5].mean() < f[weekday < 5].mean()


def test_forex_london_new_york_overlap_is_most_active():
    cal = get_calendar(MarketType.FOREX)
    ts = cal.open_minutes(JAN_1_2024, JAN_1_2024 + 86400)
    f = SessionSeasonality(cal).factor(ts)
    hour = (ts % 86400) // 3600
    assert f[(hour >= 13) & (hour < 16)].mean() > f[(hour >= 0) & (hour < 7)].mean()
