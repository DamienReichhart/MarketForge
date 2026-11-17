import pandas as pd
import pyarrow as pa
import pyarrow.feather as feather
import pyarrow.parquet as pq
import pytest

import marketforge as mf

KWARGS = {
    "start": "2024-01-02",
    "end": "2024-01-04",
    "seed": 2,
    "timeframes": "m5,H1",
    "include_regime": True,
}


def test_feather_files_hold_the_same_candles_as_parquet(tmp_path):
    a = mf.generate_to_disk(tmp_path / "f", "EURUSD", fmt="feather", **KWARGS)
    b = mf.generate_to_disk(tmp_path / "p", "EURUSD", fmt="parquet", **KWARGS)
    path = a.paths["forex"]["EURUSD"]["H1"]
    assert path.name == "EURUSD_H1.feather"
    assert feather.read_table(path).equals(pq.read_table(b.paths["forex"]["EURUSD"]["H1"]))


@pytest.mark.parametrize("fmt", ["parquet", "feather"])
def test_datetime_timestamps_are_a_native_utc_time_column(tmp_path, fmt):
    report = mf.generate_to_disk(tmp_path, "EURUSD", fmt=fmt, timestamps="datetime", **KWARGS)
    path = report.paths["forex"]["EURUSD"]["H1"]
    table = pq.read_table(path) if fmt == "parquet" else feather.read_table(path)
    kind = table.schema.field("timestamp").type
    # Parquet has no seconds unit: pyarrow stores seconds as milliseconds.
    assert pa.types.is_timestamp(kind) and kind.tz == "UTC"
    memory = mf.generate("EURUSD", **KWARGS)["EURUSD"]["H1"]
    stamps = pd.DatetimeIndex(table["timestamp"].to_pandas())
    assert stamps.as_unit("s").equals(memory.index.as_unit("s").rename(None))


@pytest.mark.parametrize("timestamps", ["unix", "datetime"])
def test_feather_and_datetime_datasets_read_back_and_extend(tmp_path, timestamps):
    whole = mf.generate_to_disk(
        tmp_path / "whole", "EURUSD,BTCUSD", fmt="feather", timestamps=timestamps, **KWARGS
    )
    part = dict(KWARGS, end="2024-01-03")
    mf.generate_to_disk(
        tmp_path / "part", "EURUSD,BTCUSD", fmt="feather", timestamps=timestamps, **part
    )
    mf.extend(tmp_path / "part", KWARGS["end"])
    for symbol in ("EURUSD", "BTCUSD"):
        market = "forex" if symbol == "EURUSD" else "crypto"
        for tf in ("m5", "H1"):
            name = f"{market}/{symbol}_{tf}.feather"
            assert feather.read_table(tmp_path / "part" / name).equals(
                feather.read_table(tmp_path / "whole" / name)
            )
    data = mf.read(tmp_path / "whole")
    pd.testing.assert_index_equal(
        data["EURUSD"]["H1"].index, mf.generate("EURUSD", **KWARGS)["EURUSD"]["H1"].index
    )
    assert whole.n_files == 4


def test_datetime_timestamps_are_refused_for_csv(tmp_path):
    with pytest.raises(ValueError, match="datetime timestamps are for Parquet and Feather"):
        mf.generate_to_disk(tmp_path, "EURUSD", fmt="csv", timestamps="datetime", **KWARGS)
