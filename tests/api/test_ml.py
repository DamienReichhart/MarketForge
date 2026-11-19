import numpy as np
import pandas as pd
import pytest

import marketforge as mf


@pytest.fixture(scope="module")
def data():
    return mf.generate(
        "BTCUSD,ETHUSD,AAPL",
        start="2024-01-02",
        days=5,
        seed=2,
        timeframes="m5,H1",
        with_regime=True,
    )


def test_to_numpy_takes_a_dtype_and_matches_the_frames(data):
    x, index, symbols = data.to_numpy("H1", ["close", "regime"], dtype=np.float32)
    assert x.dtype == np.float32 and symbols == ["AAPL", "BTCUSD", "ETHUSD"]
    btc = data["BTCUSD"]["H1"]
    np.testing.assert_array_equal(x[:, 1, 0], btc["close"].reindex(index).to_numpy(np.float32))
    assert index.is_monotonic_increasing and index.tz is not None


def test_windows_never_mix_instruments_and_label_the_last_candle(data):
    w = data.windows("m5", 32, stride=4)
    btc = data["BTCUSD"]["m5"]
    assert w.x.dtype == np.float32 and w.x.shape[1:] == (32, 2) and w.y.dtype == np.int64
    first = np.flatnonzero(w.symbols == "BTCUSD")[0]
    returns = np.diff(np.log(btc["close"].to_numpy()))
    np.testing.assert_allclose(w.x[first, :, 0], returns[:32], rtol=1e-6)
    assert w.times[first] == btc.index[32]  # the window's last candle
    assert w.y[first] == btc["regime"].cat.codes.iloc[32]
    assert set(w.symbols) == {"AAPL", "BTCUSD", "ETHUSD"}
    x, y, times, symbols = w  # unpacks
    assert len(x) == len(y) == len(times) == len(symbols)


def test_windows_forecast_a_column_ahead(data):
    w = data.windows(
        "H1", 8, features=["return", "range", "close"], target="return", horizon=1, symbols="BTCUSD"
    )
    close = data["BTCUSD"]["H1"]["close"].to_numpy()
    assert w.y[0] == pytest.approx(np.log(close[9] / close[8]), rel=1e-5)
    assert (
        mf.generate("BTCUSD", start="2024-01-02", days=1, seed=1, timeframes="H1")
        .windows(length=4, target=None)
        .y
        is None
    )
    with pytest.raises(ValueError, match="Unknown feature 'rsi'"):
        data.windows("H1", 8, features=["rsi"])


def test_arrow_and_polars_views(data):
    table = data.to_arrow("H1")
    assert table.column_names[:2] == ["symbol", "time"] and table.num_rows == sum(
        len(data[s]["H1"]) for s in data
    )
    pl = pytest.importorskip("polars")
    frame = data.to_polars("H1")
    assert isinstance(frame, pl.DataFrame) and frame.height == table.num_rows


def test_concat_stacks_seeds():
    results = list(
        mf.generate_many("BTCUSD", seeds=[3, 4], start="2024-01-02", days=1, timeframes="H1")
    )
    long = mf.concat(results)
    assert long.index.names == ["seed", "symbol", "time"]
    assert len(long.loc[3]) == len(long.loc[4]) == 24
    pd.testing.assert_frame_equal(long.loc[(4, "BTCUSD")], results[1]["BTCUSD"]["H1"])
    with pytest.raises(ValueError, match="share a seed"):
        mf.concat([results[0], results[0]])
