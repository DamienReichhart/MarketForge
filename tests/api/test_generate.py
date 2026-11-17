import datetime as dt

import numpy as np
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
    with pytest.warns(UserWarning, match="No candles for AAPL m1"):
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


def test_names_may_be_one_string_in_any_case():
    listed = mf.generate(
        ["EURUSD", "AAPL"], start="2024-01-02", end="2024-01-04", seed=5, timeframes=["H1", "D1"]
    )
    loose = mf.generate(
        "eurusd, aapl", start="2024-01-02", end="2024-01-04", seed=5, timeframes="h1,d1"
    )
    assert list(loose) == list(listed) and list(loose["AAPL"]) == ["H1", "D1"]
    pd.testing.assert_frame_equal(loose["EURUSD"]["H1"], listed["EURUSD"]["H1"])
    one = mf.generate("EURUSD", markets="all", start="2024-01-02", end="2024-01-03", seed=5)
    assert list(one) == ["EURUSD"]


@pytest.mark.parametrize("seed", [1.5, 2.0, True, "7"])
def test_seed_must_be_an_integer(seed):
    with pytest.raises(TypeError, match="seed must be an integer"):
        mf.generate("EURUSD", start="2024-01-02", end="2024-01-03", seed=seed)


def test_unknown_names_say_what_is_valid():
    with pytest.raises(ValueError, match=r"APPL \(did you mean AAPL\?\)"):
        mf.generate("APPL", start="2024-01-02", end="2024-01-03")
    with pytest.raises(ValueError, match="Unknown market 'fx'; choose from crypto, forex, stocks"):
        mf.generate(markets="fx", start="2024-01-02", end="2024-01-03")


def test_outputs_without_a_candle_are_warned_about(tmp_path):
    # 2024-01-01 is an NYSE holiday, and half a day holds no complete forex D1 candle.
    kwargs = {"start": "2024-01-01", "end": "2024-01-01T12:00", "seed": 1, "timeframes": "m1,D1"}
    with pytest.warns(UserWarning, match="No candles for EURUSD D1, AAPL m1, AAPL D1"):
        mf.generate("EURUSD,AAPL", **kwargs)
    with pytest.warns(UserWarning, match="No candles for EURUSD D1, AAPL m1, AAPL D1"):
        mf.generate_to_disk(tmp_path, "EURUSD,AAPL", **kwargs)


def test_panel_puts_one_column_per_instrument_without_filling_closures():
    data = mf.generate(
        "BTCUSD,AAPL", start="2024-01-05", end="2024-01-09", seed=2, timeframes="H1,D1"
    )
    closes = data.panel("close", "h1")
    assert list(closes.columns) == ["BTCUSD", "AAPL"]
    # Stock hours start at :30, crypto hours at :00: the index is the union of both.
    assert len(closes) == len(data["BTCUSD"]["H1"]) + len(data["AAPL"]["H1"])
    assert closes.index.is_monotonic_increasing
    assert closes.loc["2024-01-06", "AAPL"].isna().all()  # a Saturday
    pd.testing.assert_series_equal(
        closes["AAPL"].dropna(), data["AAPL"]["H1"]["close"], check_names=False
    )
    with pytest.raises(ValueError, match="Choose a timeframe: H1, D1"):
        data.panel()
    with pytest.raises(ValueError, match="Timeframe m1 was not generated"):
        data.panel("volume", "m1")


def test_spread_column_in_memory_and_on_disk(tmp_path):
    kwargs = {"start": "2024-01-02", "end": "2024-01-04", "seed": 9, "timeframes": "m1,H1"}
    plain = mf.generate("EURUSD", **kwargs)["EURUSD"]
    data = mf.generate("EURUSD", include_spread=True, include_regime=True, **kwargs)["EURUSD"]
    assert list(data["m1"].columns) == [
        "open",
        "high",
        "low",
        "close",
        "volume",
        "spread",
        "regime",
    ]
    pd.testing.assert_frame_equal(data["m1"][list(plain["m1"].columns)], plain["m1"])
    # A candle's spread is the mean spread of its minutes.
    first = data["H1"].index[0]
    minutes = data["m1"].loc[first : first + pd.Timedelta(minutes=59), "spread"]
    assert data["H1"]["spread"].iloc[0] == pytest.approx(minutes.mean(), rel=1e-12)

    for fmt in ("csv", "parquet"):
        report = mf.generate_to_disk(
            tmp_path / fmt, "EURUSD", include_spread=True, include_regime=True, fmt=fmt, **kwargs
        )
        path = report.paths["forex"]["EURUSD"]["H1"]
        df = pd.read_csv(path) if fmt == "csv" else pd.read_parquet(path)
        assert list(df.columns) == [
            "timestamp", "open", "high", "low", "close", "volume", "spread", "regime",
        ]  # fmt: skip
        np.testing.assert_allclose(df["spread"], data["H1"]["spread"], atol=5e-9)


def test_generating_into_a_dataset_refuses_unless_asked_to_overwrite(tmp_path):
    mf.generate_to_disk(
        tmp_path, "EURUSD", start="2024-01-02", end="2024-01-03", seed=1, timeframes="m5,H1"
    )
    (tmp_path / "notes.txt").write_text("mine")
    with pytest.raises(
        FileExistsError, match=r"already holds a MarketForge dataset.*overwrite=True"
    ):
        mf.generate_to_disk(
            tmp_path, "AAPL", start="2024-01-02", end="2024-01-03", seed=1, timeframes="D1"
        )
    assert (tmp_path / "forex" / "EURUSD_m5.csv").exists()  # nothing was touched

    report = mf.generate_to_disk(
        tmp_path,
        "AAPL",
        start="2024-01-02",
        end="2024-01-03",
        seed=1,
        timeframes="D1",
        overwrite=True,
    )
    files = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file())
    # The old dataset's candles are gone, so the directory matches its manifest;
    # files MarketForge did not write are left alone.
    assert files == ["marketforge.json", "notes.txt", "stocks/AAPL_D1.csv"]
    assert report.n_files == 1


def test_candle_files_without_a_manifest_count_as_a_dataset(tmp_path):
    # An interrupted generation leaves candle files and no manifest.
    (tmp_path / "crypto").mkdir()
    (tmp_path / "crypto" / "BTCUSD_m1.csv").write_text("timestamp,open\n")
    with pytest.raises(FileExistsError):
        mf.generate_to_disk(
            tmp_path, "AAPL", start="2024-01-02", end="2024-01-03", seed=1, timeframes="D1"
        )


def test_generating_into_a_directory_of_other_files_is_allowed(tmp_path):
    (tmp_path / "README.txt").write_text("not a dataset")
    mf.generate_to_disk(
        tmp_path, "AAPL", start="2024-01-02", end="2024-01-03", seed=1, timeframes="D1"
    )
    assert (tmp_path / "stocks" / "AAPL_D1.csv").exists()


def test_iso_timestamps_in_parquet_are_refused_before_anything_is_written(tmp_path):
    out = tmp_path / "out"
    with pytest.raises(ValueError, match="ISO timestamps are for CSV"):
        mf.generate_to_disk(
            out, "AAPL", start="2024-01-02", end="2024-01-03", fmt="parquet", timestamps="iso"
        )
    assert not out.exists()


@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        (
            {"BTCUSD": {"volatility": "high"}},
            r"\[instruments\.BTCUSD\]\.volatility must be a number, got 'high'",
        ),
        ({"BTCUSD": {"drift": True}}, r"\[instruments\.BTCUSD\]\.drift must be a number, got True"),
        (
            {"BTCUSD": {"correlations": 0.5}},
            r"\[instruments\.BTCUSD\]\.correlations must be a table",
        ),
        (
            {"BTCUSD": {"correlations": {"ETHUSD": "x"}}},
            r"\[instruments\.BTCUSD\]\.correlations\.ETHUSD must be a number",
        ),
    ],
)
def test_override_values_of_the_wrong_type_say_where_they_are(overrides, match):
    with pytest.raises(ValueError, match=match):
        mf.generate("BTCUSD", start="2024-01-01", end="2024-01-02", overrides=overrides)


def test_override_errors_from_a_file_name_the_file(tmp_path):
    path = tmp_path / "mine.toml"
    path.write_text('[instruments.BTCUSD]\nvolatility = "x"\n')
    with pytest.raises(ValueError, match=r"mine\.toml: \[instruments\.BTCUSD\]\.volatility"):
        mf.generate("BTCUSD", start="2024-01-01", end="2024-01-02", overrides=path)


def test_overriding_what_a_forex_cross_derives_from_its_anchors_is_warned_about():
    with pytest.warns(
        UserWarning,
        match=r"EURJPY is a forex cross derived from EURUSD and USDJPY: its start_price, volatility override is ignored",
    ):
        data = mf.generate(
            "EURJPY",
            start="2024-01-02",
            end="2024-01-03",
            seed=1,
            overrides={"EURJPY": {"volatility": 0.5, "start_price": 100.0, "spread_bps": 3.0}},
        )
    assert data["EURJPY"]["m1"]["open"].iloc[0] != 100.0  # the anchors decide


def test_instruments_outside_the_requested_markets_are_warned_about():
    with pytest.warns(UserWarning, match=r"AAPL.*not in the requested markets"):
        data = mf.generate("BTCUSD,AAPL", markets="crypto", start="2024-01-02", end="2024-01-03")
    assert list(data) == ["BTCUSD"]


def test_ranges_before_1970_are_refused_with_a_clear_message():
    with pytest.raises(ValueError, match=r"starts before 1970-01-01"):
        mf.generate("BTCUSD", start="1969-12-31", end="1970-01-02")
