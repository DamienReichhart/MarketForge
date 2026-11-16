import datetime as dt

import numpy as np
import pytest

from marketforge.aggregation.streaming import BarAggregator, Bars
from marketforge.aggregation.timeframes import Timeframe
from marketforge.config.loader import load_market_config
from marketforge.config.settings import MarketType
from marketforge.engine import MarketSimulator, build_market_spec
from marketforge.trading_calendar import get_calendar


def _ts(s: str) -> int:
    return int(dt.datetime.fromisoformat(s).replace(tzinfo=dt.timezone.utc).timestamp())


def _iso(t) -> str:
    return dt.datetime.fromtimestamp(int(t), dt.timezone.utc).strftime("%Y-%m-%dT%H:%M")


def _days(market: str, start: int, end: int, seed: int = 1) -> list[Bars]:
    sim = MarketSimulator(build_market_spec(load_market_config(market)), seed)
    return [
        Bars(d.timestamps, d.open, d.high, d.low, d.close, d.volume, d.regime)
        for d in sim.run(start, end)
    ]


def _aggregate(market: str, tf: Timeframe, start: str, end: str) -> tuple[Bars, Bars]:
    s, e = _ts(start), _ts(end)
    days = _days(market, s, e)
    agg = BarAggregator(get_calendar(MarketType(market)), tf, s, e)
    out = [b for d in days for b in [agg.push(d)] if b is not None]
    tail = agg.finish()
    if tail is not None:
        out.append(tail)
    return Bars.concat(out), Bars.concat(days)


def test_crypto_daily_bars_match_utc_days():
    bars, m1 = _aggregate("crypto", Timeframe.D1, "2024-01-01T00:00", "2024-01-04T00:00")
    assert [_iso(t) for t in bars.timestamps] == [
        "2024-01-01T00:00",
        "2024-01-02T00:00",
        "2024-01-03T00:00",
    ]
    day0 = slice(0, 1440)
    np.testing.assert_allclose(bars.open[0], m1.open[0])
    np.testing.assert_allclose(bars.close[0], m1.close[1439])
    np.testing.assert_allclose(bars.high[0], m1.high[day0].max(axis=0))
    np.testing.assert_allclose(bars.low[0], m1.low[day0].min(axis=0))
    np.testing.assert_allclose(bars.volume[0], m1.volume[day0].sum(axis=0))


def test_partial_first_and_last_candles_are_dropped():
    bars, _ = _aggregate("crypto", Timeframe.D1, "2024-01-03T03:00", "2024-01-06T12:00")
    assert [_iso(t) for t in bars.timestamps] == ["2024-01-04T00:00", "2024-01-05T00:00"]


def test_forex_days_start_at_17h_new_york_and_weeks_have_five_days():
    bars, _ = _aggregate("forex", Timeframe.D1, "2024-01-05T00:00", "2024-01-13T00:00")
    stamps = [_iso(t) for t in bars.timestamps]
    assert stamps == [
        "2024-01-07T22:00",
        "2024-01-08T22:00",
        "2024-01-09T22:00",
        "2024-01-10T22:00",
        "2024-01-11T22:00",
    ]


def test_forex_week_starts_sunday_17h_new_york_in_summer():
    bars, _ = _aggregate("forex", Timeframe.W1, "2024-07-05T00:00", "2024-07-20T00:00")
    assert [_iso(t) for t in bars.timestamps] == ["2024-07-07T21:00", "2024-07-14T21:00"]


def test_stocks_days_start_at_the_open_and_skip_holidays():
    bars, _ = _aggregate("stocks", Timeframe.D1, "2024-01-12T00:00", "2024-01-18T00:00")
    # 2024-01-15 is Martin Luther King Jr. Day.
    assert [_iso(t) for t in bars.timestamps] == [
        "2024-01-12T14:30",
        "2024-01-16T14:30",
        "2024-01-17T14:30",
    ]


def test_stocks_hourly_bars_align_to_the_half_hour_open():
    bars, _ = _aggregate("stocks", Timeframe.H1, "2024-01-03T00:00", "2024-01-04T00:00")
    stamps = [_iso(t)[-5:] for t in bars.timestamps]
    assert stamps == ["14:30", "15:30", "16:30", "17:30", "18:30", "19:30", "20:30"]
    assert np.all(bars.high >= np.maximum(bars.open, bars.close))


def test_crypto_weeks_start_on_monday():
    bars, _ = _aggregate("crypto", Timeframe.W1, "2024-01-01T00:00", "2024-01-29T00:00")
    assert [
        dt.datetime.fromtimestamp(int(t), dt.timezone.utc).weekday() for t in bars.timestamps
    ] == [0] * 4


@pytest.mark.parametrize("tf", [Timeframe.m5, Timeframe.H4, Timeframe.D1])
def test_streaming_equals_one_shot(tf):
    s, e = _ts("2024-01-01T00:00"), _ts("2024-01-05T00:00")
    days = _days("crypto", s, e, seed=3)
    cal = get_calendar(MarketType.CRYPTO)
    streamed = BarAggregator(cal, tf, s, e)
    parts = [p for d in days for p in [streamed.push(d)] if p is not None] + [streamed.finish()]
    one_shot = BarAggregator(cal, tf, s, e)
    whole = [one_shot.push(Bars.concat(days)), one_shot.finish()]
    a = Bars.concat([p for p in parts if p is not None])
    b = Bars.concat([p for p in whole if p is not None])
    np.testing.assert_array_equal(a.timestamps, b.timestamps)
    np.testing.assert_allclose(a.high, b.high)
    np.testing.assert_allclose(a.volume, b.volume)
