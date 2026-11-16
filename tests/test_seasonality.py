import numpy as np
from marketforge.config.settings import MarketType
from marketforge.core.seasonality import SeasonalityModel


def _one_day_minutely():
    # 1440 one-minute timestamps starting at a Monday 00:00 UTC (2024-01-01 is Monday)
    start = 1704067200
    return np.arange(start, start + 1440 * 60, 60, dtype=np.int64)


def test_multiplier_is_positive_and_variance_neutral():
    ts = _one_day_minutely()
    for mt in (MarketType.STOCKS, MarketType.FOREX, MarketType.CRYPTO):
        s = SeasonalityModel(mt).multiplier_series(ts)
        assert s.shape == ts.shape
        assert np.all(s > 0)
        assert abs(np.mean(s ** 2) - 1.0) < 1e-6


def test_stocks_open_close_exceed_midday():
    ts = _one_day_minutely()
    s = SeasonalityModel(MarketType.STOCKS).multiplier_series(ts)
    minutes = (ts % 86400) // 60
    open_v = s[np.argmin(np.abs(minutes - 870))]
    close_v = s[np.argmin(np.abs(minutes - 1260))]
    midday = s[np.argmin(np.abs(minutes - 1065))]
    assert open_v > midday
    assert close_v > midday


def test_crypto_weekend_below_weekday():
    sat = np.array([1704542400], dtype=np.int64)   # 2024-01-06 Saturday 12:00 UTC (dow=5)
    wed = np.array([1704283200], dtype=np.int64)   # 2024-01-03 Wednesday 12:00 UTC (dow=2)
    model = SeasonalityModel(MarketType.CRYPTO)
    combo = np.concatenate([sat, wed])
    s = model.multiplier_series(combo)
    assert s[0] < s[1]


def test_session_seasonality_is_window_independent_and_u_shaped():
    from marketforge.core.seasonality import SessionSeasonality
    from marketforge.trading_calendar import get_calendar

    cal = get_calendar(MarketType.STOCKS)
    model = SessionSeasonality(cal)
    day = cal.open_minutes(1704240000, 1704326400)  # 2024-01-03, one session
    week = cal.open_minutes(1704067200, 1704067200 + 7 * 86400)
    # Same minute, same factor, whatever window it was requested in.
    np.testing.assert_allclose(model.factor(day), model.factor(week[np.isin(week, day)]))
    f = model.factor(day)
    mid = f[len(f) // 2]
    assert f[0] > 1.3 * mid and f[-1] > 1.2 * mid
