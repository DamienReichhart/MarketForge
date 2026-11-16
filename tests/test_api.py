import datetime as dt

import pandas as pd
import pytest

import marketforge as mf
from marketforge.api.parsing import parse_time


def test_parse_time_accepts_common_forms():
    assert parse_time(1704067200) == 1704067200
    assert parse_time("1704067200") == 1704067200
    assert parse_time("2024-01-01") == 1704067200
    assert parse_time("2024-01-01T00:00Z") == 1704067200
    assert parse_time("2024-01-01T09:00+09:00") == 1704067200
    assert parse_time(dt.date(2024, 1, 1)) == 1704067200
    with pytest.raises(ValueError, match="ISO 8601"):
        parse_time("next tuesday")


def test_generate_returns_utc_indexed_frames():
    data = mf.generate(
        ["BTCUSD"], start="2024-01-01", end="2024-01-03", seed=1, timeframes=["m1", "H1", "D1"]
    )
    assert data.seed == 1
    h1 = data["BTCUSD"]["H1"]
    assert list(h1.columns) == ["open", "high", "low", "close", "volume"]
    assert str(h1.index.tz) == "UTC" and h1.index.name == "time"
    assert len(h1) == 48 and len(data["BTCUSD"]["D1"]) == 2 and len(data["BTCUSD"]["m1"]) == 2880


def test_output_does_not_depend_on_what_else_is_selected():
    kw = {"start": "2024-01-02", "end": "2024-01-04", "seed": 7, "timeframes": ["m1"]}
    alone = mf.generate(["EURUSD"], **kw)["EURUSD"]["m1"]
    with_others = mf.generate(["GBPUSD", "EURUSD", "AAPL"], **kw)["EURUSD"]["m1"]
    whole_market = mf.generate(markets=["forex"], **kw)["EURUSD"]["m1"]
    pd.testing.assert_frame_equal(alone, with_others)
    pd.testing.assert_frame_equal(alone, whole_market)


def test_random_seed_is_reported_and_reproduces():
    a = mf.generate(["AAPL"], start="2024-01-02", end="2024-01-03")
    b = mf.generate(["AAPL"], start="2024-01-02", end="2024-01-03", seed=a.seed)
    pd.testing.assert_frame_equal(a["AAPL"]["m1"], b["AAPL"]["m1"])


def test_regime_column():
    df = mf.generate(["ETHUSD"], start="2024-01-01", end="2024-01-02", seed=3, include_regime=True)[
        "ETHUSD"
    ]["m1"]
    assert set(df["regime"].cat.categories) == {
        "trend_up",
        "trend_down",
        "range",
        "high_volatility",
        "crash",
    }


def test_market_filter_and_errors():
    with pytest.raises(ValueError, match="Unknown instrument"):
        mf.generate(["NOPE"], start="2024-01-01", end="2024-01-02")
    with pytest.raises(ValueError, match="belong to the requested markets"):
        mf.generate(["AAPL"], markets=["crypto"], start="2024-01-01", end="2024-01-02")
    with pytest.raises(ValueError, match="Unknown anomaly"):
        mf.generate(["AAPL"], start="2024-01-01", end="2024-01-02", anomalies=["gaps"])
    with pytest.raises(ValueError, match="before end"):
        mf.generate(["AAPL"], start="2024-01-02", end="2024-01-01")


def test_closed_market_range_returns_empty_frames():
    df = mf.generate(["AAPL"], start="2024-01-06", end="2024-01-08", seed=1)["AAPL"]["m1"]
    assert df.empty and list(df.columns) == ["open", "high", "low", "close", "volume"]


@pytest.mark.parametrize("fmt", ["csv", "parquet"])
def test_generate_to_disk_matches_in_memory(tmp_path, fmt):
    kw = {"start": "2024-01-02", "end": "2024-01-04", "seed": 5, "timeframes": ["m1", "H1"]}
    report = mf.generate_to_disk(tmp_path, ["AAPL", "BTCUSD"], fmt=fmt, jobs=2, **kw)
    assert report.seed == 5 and report.n_files == 4
    path = report.paths["stocks"]["AAPL"]["H1"]
    assert path == tmp_path / "stocks" / f"AAPL_H1.{fmt}"
    disk = pd.read_csv(path) if fmt == "csv" else pd.read_parquet(path)
    mem = mf.generate(["AAPL"], **kw)["AAPL"]["H1"]
    assert disk["timestamp"].tolist() == [int(t.timestamp()) for t in mem.index]
    assert (disk["close"] - mem["close"].to_numpy()).abs().max() < 1e-8


def test_markets_accept_enum_values():
    from marketforge.domain.markets import MarketType

    data = mf.generate(markets=[MarketType.STOCKS], start="2024-01-02", end="2024-01-03", seed=1)
    assert "AAPL" in data


def test_frames_are_independent_of_each_other():
    data = mf.generate(["EURUSD", "USDJPY"], start="2024-01-02", end="2024-01-03", seed=2)
    eur, jpy = data["EURUSD"]["m1"], data["USDJPY"]["m1"]
    before = jpy.copy()
    eur.iloc[0, 0] = -1.0
    pd.testing.assert_frame_equal(jpy, before)


def test_generation_error_is_not_masked_by_closing_writers(tmp_path, monkeypatch):
    import marketforge.api.disk as api

    def boom(*args, **kwargs):
        raise RuntimeError("simulation failed")

    monkeypatch.setattr(api, "execute", boom)
    with pytest.raises(RuntimeError, match="simulation failed"):
        mf.generate_to_disk(tmp_path, ["EURUSD"], start="2024-01-02", end="2024-01-03", seed=1)
    # Writers were still closed: every file exists and is valid (empty).
    assert pd.read_csv(tmp_path / "forex" / "EURUSD_m1.csv").empty
