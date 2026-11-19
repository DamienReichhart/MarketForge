import numpy as np
import pandas as pd
import pytest

import marketforge as mf
from marketforge.simulation import macro


def test_the_macro_state_is_stressed_about_one_day_in_nine():
    states = np.array([macro.macro_state(7, day) for day in range(4 * macro.ERA_DAYS)])
    share = states.mean()
    expected = macro.STRESSED_DAYS / (macro.CALM_DAYS + macro.STRESSED_DAYS)
    assert share == pytest.approx(expected, abs=0.05)
    spells = np.diff(np.flatnonzero(np.diff(states) != 0))
    assert 10 < spells.mean() < 300  # days, not minutes


def test_the_world_does_not_depend_on_the_market_or_the_range():
    assert macro.macro_state(3, 20000) == macro.macro_state(3, 20000)
    assert macro.global_shocks(3, 20000) is macro.global_shocks(3, 20000)  # cached
    assert not np.array_equal(macro.global_shocks(3, 20000), macro.global_shocks(4, 20000))


def test_a_closure_shock_is_a_unit_normal():
    starts = np.arange(200) * 1440 * 3 + 28_800_000
    values = [macro.closure_shock(1, int(s), int(s) + 1049) for s in starts]  # a stock night
    assert np.std(values) == pytest.approx(1.0, abs=0.15)


def test_a_direction_the_market_gives_no_weight_ties_nothing():
    mixing = macro.global_mixing(np.eye(3), np.zeros(3), (0.9, 0.9))
    z = np.random.default_rng(0).standard_normal((5, 3))
    np.testing.assert_array_equal(mixing.apply(z, np.ones(5), np.zeros(5, bool)), z)


def test_mixing_keeps_the_markets_own_correlations():
    rng = np.random.default_rng(1)
    corr = np.array([[1.0, 0.8, 0.3], [0.8, 1.0, 0.2], [0.3, 0.2, 1.0]])
    z = rng.standard_normal((200_000, 3)) @ np.linalg.cholesky(corr).T
    mixing = macro.global_mixing(corr, np.array([1.0, 1.0, 0.2]), (0.9, 0.9))
    mixed = mixing.apply(z, rng.standard_normal(200_000), np.zeros(200_000, bool))
    np.testing.assert_allclose(np.corrcoef(mixed.T), corr, atol=0.01)


@pytest.fixture(scope="module")
def world():
    return mf.generate(
        "BTCUSD,ETHUSD,AAPL,MSFT,SPXUSD,AUDUSD,USDJPY",
        start="2022-01-03",
        end="2023-01-01",
        seed=3,
        timeframes="H1",
    )


def _daily(data):
    closes = data.panel("close", "H1").ffill()
    returns = np.log(closes.groupby(closes.index.floor("D")).last()).diff()
    return returns[returns.index.dayofweek < 5].dropna()


@pytest.mark.parametrize(
    ("a", "b", "low", "high"),
    [
        ("BTCUSD", "AAPL", 0.03, 0.5),  # coins and stocks
        ("SPXUSD", "AAPL", 0.1, 0.9),  # the S&P CFD and a large cap
        ("AUDUSD", "SPXUSD", 0.1, 0.7),  # a risk currency and stocks
        ("USDJPY", "SPXUSD", 0.1, 0.8),  # the yen is a haven: USDJPY rises with risk
    ],
)
def test_markets_move_together(world, a, b, low, high):
    assert low < _daily(world)[[a, b]].corr().iloc[0, 1] < high


def test_a_market_alone_is_the_same_as_beside_others(world):
    alone = mf.generate("BTCUSD", start="2022-01-03", end="2022-02-01", seed=3, timeframes="H1")
    pd.testing.assert_frame_equal(
        alone["BTCUSD"]["H1"], world["BTCUSD"]["H1"].loc[:"2022-01-31 23:00"]
    )


def test_the_macro_state_is_a_label_of_the_data(world):
    labels = world.macro()
    assert set(labels.cat.categories) == {"calm", "stressed"}
    assert labels.index[0] == pd.Timestamp("2022-01-03", tz="UTC") and len(labels) == 363
    assert labels.iloc[0] == ("stressed" if macro.macro_state(3, 18995) else "calm")
