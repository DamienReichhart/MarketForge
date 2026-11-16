import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import pytest

from marketforge.aggregation.streaming import Bars
from marketforge.aggregation.timeframes import Timeframe
from marketforge.output.writers import CandleWriter, OutputFormat


def _bars(t0: int, n: int) -> Bars:
    ts = t0 + 60 * np.arange(n, dtype=np.int64)
    p = np.column_stack([np.linspace(1.0851234567891, 1.09, n), np.linspace(150.0, 151.0, n)])
    return Bars(
        ts, p, p * 1.001, p * 0.999, p, np.full((n, 2), 1234.567891), np.zeros(n, dtype=np.int8)
    )


@pytest.mark.parametrize("fmt", list(OutputFormat))
def test_appends_are_equivalent_to_one_write(tmp_path, fmt):
    w = CandleWriter(
        tmp_path, "forex", ["EURUSD", "USDJPY"], [0, 1], [Timeframe.m1, Timeframe.D1], fmt, True
    )
    w.write(Timeframe.m1, _bars(0, 3))
    w.write(Timeframe.m1, _bars(180, 2))
    paths = w.close()
    p = paths["USDJPY"]["m1"]
    assert p.name == f"USDJPY_m1.{fmt.value}"
    df = pd.read_csv(p) if fmt == OutputFormat.CSV else pq.read_table(p).to_pandas()
    assert list(df.columns) == ["timestamp", "open", "high", "low", "close", "volume", "regime"]
    assert df["timestamp"].tolist() == [0, 60, 120, 180, 240]
    assert df["volume"].iloc[0] == 1234.5679  # rounded to 4 decimals
    # A timeframe that received nothing is still a valid empty file.
    d1 = paths["EURUSD"]["D1"]
    empty = pd.read_csv(d1) if fmt == OutputFormat.CSV else pq.read_table(d1).to_pandas()
    assert len(empty) == 0 and "close" in empty.columns


def test_csv_prices_are_rounded_to_8_decimals(tmp_path):
    w = CandleWriter(tmp_path, "forex", ["EURUSD"], [0], [Timeframe.m1])
    w.write(Timeframe.m1, _bars(0, 1))
    line = w.close()["EURUSD"]["m1"].read_text().splitlines()
    assert line[0] == "timestamp,open,high,low,close,volume"
    assert line[1].split(",")[1] == "1.08512346"
