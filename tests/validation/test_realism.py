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
