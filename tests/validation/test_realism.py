# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

"""
Modelled properties of generated data, measured from the public API.

The expected values are the catalog's stated relationships (literal numbers
from marketforge/config/catalog), or properties of real markets.
"""

import numpy as np
import pandas as pd
import pytest

import marketforge as mf


def _returns(data, timeframe: str) -> pd.DataFrame:
    closes = data.panel("close", timeframe)
    return np.log(closes).diff().dropna()


@pytest.fixture(scope="module")
def forex():
    return mf.generate(
        "EURUSD,GBPUSD,USDCHF,USDJPY,AUDUSD,NZDUSD,AUDNZD,EURGBP",
        start="2024-01-01",
        end="2024-07-01",
        seed=11,
        timeframes="H1",
    )


# Ranges of hourly return correlations in real markets over recent years. The
# catalog's own point values cannot all hold together (EURUSD-USDCHF -0.92
# would make EURCHF far calmer than its stated 5%), so they are no test; the
# old eigenvalue clipping gave -0.45 and 0.41 for the first and third pairs.
@pytest.mark.parametrize(
    ("a", "b", "low", "high"),
    [
        ("EURUSD", "USDCHF", -0.95, -0.6),
        ("EURUSD", "GBPUSD", 0.55, 0.9),
        ("AUDUSD", "NZDUSD", 0.7, 0.95),
        ("EURUSD", "USDJPY", -0.7, -0.2),
    ],
)
def test_forex_anchor_correlations_are_those_of_real_markets(forex, a, b, low, high):
    realised = _returns(forex, "H1")[[a, b]].corr().iloc[0, 1]
    assert low <= realised <= high


@pytest.mark.parametrize(("cross", "stated"), [("AUDNZD", 0.070), ("EURGBP", 0.060)])
def test_forex_crosses_have_about_their_catalog_volatility(forex, cross, stated):
    # Relative to EURUSD (stated 0.065), so the regimes' common scaling cancels.
    returns = _returns(forex, "H1")
    ratio = returns[cross].std() / returns["EURUSD"].std()
    assert ratio == pytest.approx(stated / 0.065, rel=0.25)


@pytest.mark.parametrize(
    ("market", "a", "b", "stated"),
    [
        ("crypto", "BTCUSD", "ETHUSD", 0.88),
        ("crypto", "BTCUSD", "LTCUSD", 0.85),
        ("stocks", "AAPL", "MSFT", 0.78),
    ],
)
def test_stated_correlations_survive_into_the_data(market, a, b, stated):
    data = mf.generate([a, b], start="2024-01-01", end="2024-04-01", seed=5, timeframes="H1")
    realised = _returns(data, "H1").corr().iloc[0, 1]
    assert realised == pytest.approx(stated, abs=0.1)


def _spell_returns(frame: pd.DataFrame) -> pd.DataFrame:
    """Log return and regime of every spell (run of one regime) of a frame."""
    spell = (frame["regime"] != frame["regime"].shift()).cumsum()
    log_close = np.log(frame["close"])
    out = pd.DataFrame(
        {
            "regime": frame["regime"].groupby(spell).first().astype(str),
            "ret": log_close.groupby(spell).last() - np.log(frame["open"]).groupby(spell).first(),
        }
    )
    return out


@pytest.fixture(scope="module")
def crypto_year():
    return mf.generate(
        "BTCUSD,ETHUSD",
        start="2023-01-01",
        end="2024-01-01",
        seed=2,
        timeframes="H1",
        include_regime=True,
    )


def test_trend_regimes_trend(crypto_year):
    # A label is only ground truth for a classifier if it shows in the data: over a
    # spell, trend_up rises and trend_down falls more often than not.
    for symbol in ("BTCUSD", "ETHUSD"):
        spells = _spell_returns(crypto_year[symbol]["H1"])
        up = spells.loc[spells.regime == "trend_up", "ret"]
        down = spells.loc[spells.regime == "trend_down", "ret"]
        assert (up > 0).mean() > 0.65, symbol
        assert (down < 0).mean() > 0.65, symbol
        crash = spells.loc[spells.regime == "crash", "ret"]
        assert crash.mean() < down.mean() < 0 < up.mean(), symbol


def test_forex_trends_move_pairs_with_their_correlation():
    # A trend is the market's main factor moving: EURUSD and USDCHF, which move
    # against each other, trend in opposite directions, even with no catalog drift.
    data = mf.generate(
        "EURUSD,USDCHF",
        start="2023-01-01",
        end="2024-01-01",
        seed=4,
        timeframes="H1",
        include_regime=True,
    )
    up = {s: _spell_returns(data[s]["H1"]).query("regime == 'trend_up'")["ret"] for s in data}
    assert np.sign(up["EURUSD"].mean()) == -np.sign(up["USDCHF"].mean())
    assert (np.sign(up["EURUSD"]) != np.sign(up["USDCHF"])).mean() > 0.65


@pytest.mark.parametrize(("symbol", "seed"), [("AAPL", 3), ("BTCUSD", 2), ("EURUSD", 4)])
def test_crashes_are_the_most_volatile_regime(symbol, seed):
    frame = mf.generate(
        symbol,
        start="2022-01-01",
        end="2024-01-01",
        seed=seed,
        timeframes="m5",
        include_regime=True,
    )[symbol]["m5"]
    r = np.log(frame["close"]).diff()
    vol = r.groupby(frame["regime"], observed=True).std()
    assert vol["crash"] > vol["high_volatility"] > vol["range"]


@pytest.mark.parametrize(
    ("pair", "seed"), [(("BTCUSD", "SANDUSD"), 2), (("AAPL", "XOM"), 3), (("EURUSD", "AUDUSD"), 4)]
)
def test_correlations_rise_in_a_crash(pair, seed):
    # In real sell-offs everything moves together: diversification fails when needed.
    data = mf.generate(
        list(pair),
        start="2022-01-01",
        end="2024-01-01",
        seed=seed,
        timeframes="m5",
        include_regime=True,
    )
    r = _returns(data, "m5")
    regime = data[pair[0]]["m5"]["regime"].reindex(r.index)
    by_regime = {name: r[regime == name].corr().iloc[0, 1] for name in ("range", "crash")}
    assert abs(by_regime["crash"]) > abs(by_regime["range"]) + 0.1


# Stocks trade 390 minutes a day: three months give as many big minutes as one of crypto.
@pytest.mark.parametrize(
    ("symbol", "seed", "end"), [("BTCUSD", 1, "2024-02-01"), ("AAPL", 2, "2024-04-01")]
)
def test_big_moves_have_wicks(symbol, seed, end):
    # Real minutes that move a lot also retrace: their range exceeds their body
    # by a third or more. 3.x drew wicks from the expected volatility only, so
    # its biggest minutes were bare bodies (range/body 1.05).
    m1 = mf.generate(symbol, start="2024-01-01", end=end, seed=seed)[symbol]["m1"]
    body = (m1["close"] - m1["open"]).abs()
    z = body / body.rolling(240, min_periods=60).median()
    big = m1[z > 8]
    assert len(big) > 50
    assert ((big["high"] - big["low"]) / (big["close"] - big["open"]).abs()).median() > 1.25


def _abs_returns_by_minute(frame: pd.DataFrame) -> pd.Series:
    """Median |log return| per UTC minute of the day."""
    r = np.log(frame["close"]).diff().abs().dropna()
    return r.groupby(r.index.hour * 60 + r.index.minute).median()


def test_stocks_open_far_more_volatile_than_midday():
    # Real first minutes are 3-4 times as volatile as midday.
    m1 = mf.generate("AAPL", start="2024-01-02", end="2024-04-01", seed=8)["AAPL"]["m1"]
    r = np.log(m1["close"]).diff().abs()
    ny = r.index.tz_convert("America/New_York")
    minute = ny.hour * 60 + ny.minute
    first = r[(minute >= 570) & (minute < 575)].median()
    midday = r[(minute >= 720) & (minute < 840)].median()
    assert first > 2.5 * midday


def test_forex_london_open_follows_british_summer_time():
    # London opens at 08:00 local: 08:00 UTC in winter, 07:00 UTC in summer.
    def open_jump(start, end):
        by_minute = _abs_returns_by_minute(
            mf.generate("EURUSD", start=start, end=end, seed=6)["EURUSD"]["m1"]
        )
        return by_minute.loc[420:479].mean() / by_minute.loc[360:419].mean()

    assert open_jump("2024-06-03", "2024-08-03") > 1.3 * open_jump("2024-01-08", "2024-03-08")


def test_crypto_volatility_bumps_at_funding_times():
    # Perpetual futures settle funding at 00:00, 08:00 and 16:00 UTC.
    by_minute = _abs_returns_by_minute(
        mf.generate("BTCUSD", start="2024-01-01", end="2024-04-01", seed=9)["BTCUSD"]["m1"]
    )
    at_funding = by_minute.loc[[479, 480, 481]].mean()
    before = by_minute.loc[450:470].mean()
    assert at_funding > 1.15 * before


def test_forex_thins_out_on_friday_afternoon():
    m1 = mf.generate("EURUSD", start="2024-01-07", end="2024-04-07", seed=5)["EURUSD"]["m1"]
    r = np.log(m1["close"]).diff().abs()
    ny = r.index.tz_convert("America/New_York")
    afternoon = (ny.hour >= 13) & (ny.hour < 17)
    assert (
        r[afternoon & (ny.dayofweek == 4)].median()
        < 0.85 * r[afternoon & (ny.dayofweek == 2)].median()
    )
