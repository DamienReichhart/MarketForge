import numpy as np
import pandas as pd
import pytest

import marketforge as mf

KWARGS = {"start": "2024-01-02", "end": "2024-01-05", "seed": 4, "timeframes": "m5,H1"}


@pytest.mark.parametrize(
    ("fmt", "timestamps"), [("csv", "unix"), ("csv", "iso"), ("parquet", "unix")]
)
def test_read_returns_what_generate_returns(tmp_path, fmt, timestamps):
    options = {"with_regime": True, "with_spread": True, **KWARGS}
    mf.generate_to_disk(tmp_path, "EURUSD,AAPL", format=fmt, timestamps=timestamps, **options)
    data = mf.read(tmp_path)
    memory = mf.generate("EURUSD,AAPL", **options)
    assert data.seed == 4
    assert sorted(data) == ["AAPL", "EURUSD"]
    for symbol in memory:
        assert list(data[symbol]) == ["m5", "H1"]
        for tf, frame in memory[symbol].items():
            got = data[symbol][tf]
            pd.testing.assert_index_equal(got.index, frame.index)
            assert list(got.columns) == list(frame.columns)
            numeric = ["open", "high", "low", "close", "volume", "spread"]
            np.testing.assert_allclose(got[numeric], frame[numeric], rtol=0, atol=1e-4)
            pd.testing.assert_series_equal(got["regime"], frame["regime"])


def test_read_can_load_part_of_a_dataset(tmp_path):
    mf.generate_to_disk(tmp_path, "EURUSD,AAPL,BTCUSD", **KWARGS)
    data = mf.read(tmp_path, instruments="btcusd", timeframes="h1")
    assert list(data) == ["BTCUSD"] and list(data["BTCUSD"]) == ["H1"]
    with pytest.raises(ValueError, match="not in the dataset"):
        mf.read(tmp_path, instruments="SOLUSD")
