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
