import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import pytest

from marketforge.domain.bars import Bars
from marketforge.domain.timeframes import Timeframe
from marketforge.output.formats import OutputFormat
from marketforge.output.writer import CandleWriter


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


def _read(path, fmt):
    return pd.read_csv(path) if fmt == OutputFormat.CSV else pq.read_table(path).to_pandas()


@pytest.mark.parametrize("fmt", list(OutputFormat))
def test_rerunning_into_the_same_directory_leaves_no_stale_file(tmp_path, fmt):
    first = CandleWriter(tmp_path, "forex", ["EURUSD"], [0], [Timeframe.D1], fmt)
    first.write(Timeframe.D1, _bars(0, 3))
    path = first.close()["EURUSD"]["D1"]
    assert len(_read(path, fmt)) == 3
    # A second run whose range holds no complete daily candle.
    CandleWriter(tmp_path, "forex", ["EURUSD"], [0], [Timeframe.D1], fmt).close()
    assert len(_read(path, fmt)) == 0


@pytest.mark.parametrize("fmt", list(OutputFormat))
def test_memory_cap_flushes_early_without_changing_the_output(tmp_path, fmt, monkeypatch):
    import marketforge.output.writer as writers

    monkeypatch.setattr(writers, "ROW_GROUP_ROWS", 40)
    tfs = [Timeframe.m1, Timeframe.m5]
    capped = CandleWriter(tmp_path / "a", "forex", ["EURUSD", "USDJPY"], [0, 1], tfs, fmt, True, 50)
    free = CandleWriter(tmp_path / "b", "forex", ["EURUSD", "USDJPY"], [0, 1], tfs, fmt, True)
    peak = 0
    for k in range(12):
        for w in (capped, free):
            w.write(Timeframe.m1, _bars(600 * k, 10))
            w.write(Timeframe.m5, _bars(600 * k, 2))
        peak = max(peak, capped._total_buffered)
    assert peak <= 50
    a, b = capped.close(), free.close()
    for sym in ("EURUSD", "USDJPY"):
        for tf in ("m1", "m5"):
            pd.testing.assert_frame_equal(_read(a[sym][tf], fmt), _read(b[sym][tf], fmt))


def test_written_columns_follow_the_requested_order(tmp_path):
    w = CandleWriter(tmp_path, "forex", ["USDJPY", "EURUSD"], [1, 0], [Timeframe.m1])
    w.write(Timeframe.m1, _bars(0, 2))
    paths = w.close()
    assert pd.read_csv(paths["USDJPY"]["m1"])["open"].iloc[0] == 150.0
    assert pd.read_csv(paths["EURUSD"]["m1"])["open"].iloc[0] == 1.08512346


def test_open_file_limit_is_raised_when_parquet_needs_it(monkeypatch):
    resource = pytest.importorskip("resource")  # POSIX only
    from marketforge.output import file_limits as writers

    calls = []
    monkeypatch.setattr(resource, "getrlimit", lambda _: (256, 100_000))
    monkeypatch.setattr(resource, "setrlimit", lambda _, lim: calls.append(lim))
    writers.ensure_open_file_capacity(1664)
    assert calls and calls[0][0] >= 1664 and calls[0][1] == 100_000
    calls.clear()
    writers.ensure_open_file_capacity(100)  # already enough: untouched
    assert not calls


def test_open_file_limit_that_cannot_be_raised_fails_upfront(monkeypatch):
    resource = pytest.importorskip("resource")  # POSIX only
    from marketforge.output import file_limits as writers

    monkeypatch.setattr(resource, "getrlimit", lambda _: (256, 512))
    monkeypatch.setattr(resource, "setrlimit", lambda *_: None)
    with pytest.raises(OSError, match="use CSV"):
        writers.ensure_open_file_capacity(1664)
