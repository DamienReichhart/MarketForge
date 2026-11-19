import pandas as pd
import pytest

import marketforge as mf


@pytest.fixture(scope="module")
def data():
    return mf.generate(
        "EURUSD,BTCUSD,AAPL",
        start="2024-01-02",
        days=8,
        seed=3,
        timeframes="m1,H1,D1",
        with_regime=True,
    )


def test_what_it_holds(data):
    assert data.seed == 3
    assert data.start == pd.Timestamp("2024-01-02", tz="UTC")
    assert data.end == pd.Timestamp("2024-01-10", tz="UTC")
    assert data.version == mf.__version__ and data.model_revision == mf.MODEL_REVISION
    assert data.symbols == ("AAPL", "BTCUSD", "EURUSD")
    assert data.markets == ("crypto", "forex", "stocks")
    assert data.timeframes == ("m1", "H1", "D1")
    assert data.columns == ("open", "high", "low", "close", "volume", "regime")
    assert data.market_of("eurusd") == "forex"
    assert len(data) == 3 and list(data) == ["AAPL", "BTCUSD", "EURUSD"]
    assert "btcusd" in data and "NOPE" not in data


def test_the_getters_agree(data):
    frame = data.frame("BTCUSD", "h1")
    assert frame is data["BTCUSD"]["H1"] is data["btcusd", "H1"] is data.instrument("BTCUSD")["h1"]
    btc = data.instrument("BTCUSD")
    assert (btc.symbol, btc.market, btc.timeframes) == ("BTCUSD", "crypto", ("m1", "H1", "D1"))
    assert "h1" in btc and "W1" not in btc


def test_unknown_keys_say_what_is_held(data):
    with pytest.raises(KeyError, match="did you mean BTCUSD"):
        data["BTCUSF"]
    with pytest.raises(KeyError, match="No timeframe W1 for BTCUSD"):
        data["BTCUSD"]["W1"]
    with pytest.raises(KeyError, match="'h7' is not a timeframe"):
        data["BTCUSD"]["h7"]


def test_it_is_read_only(data):
    with pytest.raises(TypeError):
        data["X"] = {}  # type: ignore[index]
    with pytest.raises(TypeError):
        data["BTCUSD"]["W1"] = pd.DataFrame()  # type: ignore[index]


def test_the_repr_fits_on_a_screen(data):
    text = repr(data)
    assert text.startswith("<GeneratedData seed=3, 2024-01-02 00:00 -> 2024-01-10 00:00 UTC")
    assert "crypto     1 instrument(s), 11,520 m1 candles each: BTCUSD" in text
    assert len(text.splitlines()) == 6 and "open  " not in text


def test_regime_and_spells(data):
    regime = data.regime("crypto", "m1")
    assert regime.equals(data["BTCUSD"]["m1"]["regime"])
    spells = data.spells("crypto")
    assert list(spells.columns) == ["start", "end", "regime", "candles", "duration"]
    assert spells["candles"].sum() == len(regime)
    assert (
        spells["regime"].astype(str).to_numpy()[1:] != spells["regime"].astype(str).to_numpy()[:-1]
    ).all()
    assert spells["start"].iloc[0] == regime.index[0]
    with pytest.raises(ValueError, match="with_regime=True"):
        mf.generate("BTCUSD", start="2024-01-02", days=1, seed=1, timeframes="m1").regime(
            "crypto", "m1"
        )


def test_select_and_between(data):
    some = data.select(["btcusd", "AAPL"], timeframes="H1")
    assert some.symbols == ("AAPL", "BTCUSD") and some.timeframes == ("H1",)
    assert data.select(markets="forex").symbols == ("EURUSD",)
    week = data.between("2024-01-03", "2024-01-05")
    h1 = week["BTCUSD"]["H1"]
    assert h1.index[0] == pd.Timestamp("2024-01-03", tz="UTC") and len(h1) == 48
    assert week.start == pd.Timestamp("2024-01-03", tz="UTC")


def test_copy_keeps_the_seed(data):
    copied = data.copy()
    assert copied.seed == 3 and copied.symbols == data.symbols and copied is not data


def test_summary(data):
    summary = data.summary()
    assert summary.loc[("AAPL", "D1"), "candles"] == 6  # 2-5, 8 and 9 January
    assert summary.loc[("BTCUSD", "m1"), "market"] == "crypto"


@pytest.mark.parametrize("fmt", ["csv", "parquet", "feather"])
def test_save_writes_what_generate_to_disk_writes(data, tmp_path, fmt):
    data.save(tmp_path / "saved", format=fmt)
    mf.generate_to_disk(
        tmp_path / "direct",
        "EURUSD,BTCUSD,AAPL",
        start="2024-01-02",
        days=8,
        seed=3,
        timeframes="m1,H1,D1",
        with_regime=True,
        format=fmt,
    )
    if fmt == "csv":
        for path in sorted((tmp_path / "direct").rglob(f"*.{fmt}")):
            rel = path.relative_to(tmp_path / "direct")
            assert (tmp_path / "saved" / rel).read_bytes() == path.read_bytes(), rel
    assert mf.verify(tmp_path / "saved").passed
    mf.extend(tmp_path / "saved", days=2)  # and it continues like any dataset


def test_a_read_dataset_saves_in_another_format(tmp_path):
    mf.generate_to_disk(tmp_path / "csv", "BTCUSD", start="2024-01-02", days=3, seed=1)
    mf.read(tmp_path / "csv").save(tmp_path / "pq", format="parquet")
    assert mf.info(tmp_path / "pq").format == "parquet"
    assert mf.verify(tmp_path / "pq").passed


def test_a_slice_in_time_cannot_be_saved(data, tmp_path):
    with pytest.raises(ValueError, match="cut in time"):
        data.between("2024-01-03").save(tmp_path)


def test_read_can_keep_only_a_time_range(tmp_path):
    for fmt in ("csv", "parquet"):
        mf.generate_to_disk(tmp_path / fmt, "AAPL", start="2024-01-02", days=7, seed=1, format=fmt)
        part = mf.read(tmp_path / fmt, timeframes="D1", start="2024-01-04", end="2024-01-06")
        assert list(part["AAPL"]["D1"].index.day) == [4, 5]
