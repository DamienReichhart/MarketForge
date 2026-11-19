"""Datasets in backtesting engines' file layouts (mf.export, marketforge export)."""

import io
import zipfile

import numpy as np
import pandas as pd
import pytest
from click.testing import CliRunner

import marketforge as mf
from marketforge.cli.main import cli


@pytest.fixture(scope="module")
def dataset(tmp_path_factory):
    root = tmp_path_factory.mktemp("export") / "ds"
    mf.generate_to_disk(
        root,
        "AAPL,EURUSD,BTCUSD,SPXUSD,XAUUSD",
        start="2024-03-07",
        days=4,
        seed=1,
        timeframes="m1,m2,H1,D1",
        with_bid_ask=True,
    )
    return root


@pytest.fixture(scope="module")
def data(dataset):
    return mf.read(dataset)


def _csv(path, name=None):
    with zipfile.ZipFile(path) as archive:
        (entry,) = archive.namelist()
        assert name is None or entry == name
        return pd.read_csv(io.BytesIO(archive.read(entry)), header=None)


# ---------------------------------------------------------------- freqtrade
def test_freqtrade_files_are_what_its_feather_handler_reads(dataset, data, tmp_path):
    report = mf.export("freqtrade", dataset, tmp_path, quote="USDT")
    btc = pd.read_feather(tmp_path / "BTC_USDT-1h.feather")
    assert list(btc.columns) == ["date", "open", "high", "low", "close", "volume"]
    assert str(btc["date"].dtype) == "datetime64[ms, UTC]"
    theirs = data["BTCUSD"]["H1"]
    np.testing.assert_array_equal(btc["close"], theirs["close"])
    assert (btc["date"] == theirs.index).all()
    names = {p.name for p in report.files}
    # Only coins take the renamed dollar: forex by its codes, stocks against USD.
    assert {"AAPL_USD-1m.feather", "EUR_USD-1d.feather", "BTC_USDT-1m.feather"} <= names
    assert not any("2m" in n for n in names)
    assert "BTCUSD m2: freqtrade has no such timeframe" in report.skipped


# --------------------------------------------------------------------- LEAN
@pytest.fixture(scope="module")
def lean(dataset, tmp_path_factory):
    root = tmp_path_factory.mktemp("lean")
    mf.export("lean", dataset, root)
    return root


def test_lean_equity_minutes_are_new_york_milliseconds_and_ten_thousandths(lean, data):
    m1 = data["AAPL"]["m1"]
    day = m1.index.tz_convert("America/New_York").normalize()[0]
    rows = _csv(
        lean / "equity/usa/minute/aapl" / f"{day:%Y%m%d}_trade.zip",
        f"{day:%Y%m%d}_aapl_minute_trade.csv",
    )
    first = m1[m1.index.tz_convert("America/New_York").normalize() == day]
    assert rows[0].iloc[0] == 9.5 * 3_600_000  # 09:30 New York
    np.testing.assert_allclose(rows[4] / 10_000, first["close"], atol=5e-5)
    assert rows[1].dtype == np.int64 and rows[5].dtype == np.int64  # whole numbers
    # Quotes too, and LEAN finds the ticker through its map and factor files.
    quotes = _csv(lean / "equity/usa/minute/aapl" / f"{day:%Y%m%d}_quote.zip")
    assert (quotes[4] < quotes[9]).all()  # bid close below ask close
    assert (lean / "equity/usa/map_files/aapl.csv").read_text().endswith("20501231,aapl,Q\n")
    assert (lean / "equity/usa/factor_files/aapl.csv").is_file()


def test_lean_hour_and_daily_bars_are_built_from_minutes(lean, data):
    hours = _csv(lean / "equity/usa/hour/aapl.zip", "aapl.csv")
    assert hours[0].iloc[0].endswith("09:00")  # 09:30-10:00, on the clock hour as LEAN's
    assert hours.shape[1] == 6  # trades only
    daily = _csv(lean / "crypto/coinbase/daily/btcusd_trade.zip", "btcusd.csv")
    m1 = data["BTCUSD"]["m1"]
    first = m1.loc[: m1.index[0].normalize() + pd.Timedelta(hours=23, minutes=59)]
    assert daily[0].iloc[0].endswith("00:00")
    assert daily[2].iloc[0] == pytest.approx(first["high"].max())
    assert daily[5].iloc[0] == pytest.approx(first["volume"].sum(), rel=1e-9)


def test_lean_forex_has_quote_bars_and_cfds_their_own_tree(lean, data):
    minutes = sorted((lean / "forex/oanda/minute/eurusd").iterdir())
    assert all(p.name.endswith("_quote.zip") for p in minutes)
    rows = _csv(minutes[0])
    assert rows.shape[1] == 11 and (rows[5] == 0).all()  # bid OHLC, size, ask OHLC, size
    assert (rows[4] < rows[9]).all()
    first = data["EURUSD"]["m1"].iloc[0]
    assert rows[4].iloc[0] == pytest.approx(first["bid"]) and rows[9].iloc[0] == pytest.approx(
        first["ask"]
    )
    for symbol in ("spxusd", "xauusd"):  # an index and gold are Oanda CFDs in LEAN
        assert (lean / "cfd/oanda/minute" / symbol).is_dir()
        assert not (lean / "forex/oanda/minute" / symbol).exists()


def test_lean_needs_minutes(tmp_path):
    hourly = tmp_path / "hourly"
    mf.generate_to_disk(hourly, "EURUSD", start="2024-03-07", days=1, seed=1, timeframes="H1")
    with pytest.raises(ValueError, match="no m1 candles"):
        mf.export("lean", hourly, tmp_path / "out")


def test_export_command(dataset, tmp_path):
    res = CliRunner().invoke(cli, ["export", "freqtrade", str(dataset), str(tmp_path / "ft")])
    assert res.exit_code == 0, res.output
    assert "Wrote" in res.output and (tmp_path / "ft" / "EUR_USD-1h.feather").is_file()
    res = CliRunner().invoke(cli, ["export", "zipline", str(dataset), str(tmp_path / "z")])
    assert res.exit_code != 0 and "zipline" in res.output
