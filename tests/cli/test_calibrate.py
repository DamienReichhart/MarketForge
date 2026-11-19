import tomllib

import pytest
from click.testing import CliRunner

import marketforge as mf
from marketforge.cli.main import cli


@pytest.fixture(scope="module")
def real(tmp_path_factory):
    # Stand-in for a user's real files: MarketForge data, whose parameters are known.
    root = tmp_path_factory.mktemp("real")
    mf.generate_to_disk(
        root, "BTCUSD,ETHUSD", start="2024-01-01", days=120, seed=3, timeframes="m1"
    )
    return root


def test_calibrate_writes_an_override_file_that_reproduces_the_data(real, tmp_path):
    out = tmp_path / "mine.toml"
    files = [str(real / "crypto" / f"{s}_m1.csv") for s in ("BTCUSD", "ETHUSD")]
    res = CliRunner().invoke(cli, ["calibrate", *files, "--market", "crypto", "-o", str(out)])
    assert res.exit_code == 0, res.output
    doc = tomllib.loads(out.read_text())["instruments"]
    catalog = mf.instruments("crypto")
    for symbol in ("BTCUSD", "ETHUSD"):
        fitted = doc[symbol]
        assert fitted["volatility"] == pytest.approx(catalog.loc[symbol, "volatility"], rel=0.25)
        # 120 days of one seed: the regimes, and the world, move the mean volume.
        assert fitted["volume_base"] == pytest.approx(catalog.loc[symbol, "volume_base"], rel=0.2)
    assert doc["ETHUSD"]["correlations"]["BTCUSD"] == pytest.approx(0.88, abs=0.1)
    # The file is a valid override: generation uses it.
    data = mf.generate("BTCUSD", start="2024-06-01", days=1, seed=1, overrides=out)
    assert data["BTCUSD"]["m1"]["open"].iloc[0] == pytest.approx(doc["BTCUSD"]["start_price"])


def test_calibrate_names_new_instruments_by_their_file(real, tmp_path):
    path = tmp_path / "MYCOIN_m1.csv"
    path.write_bytes((real / "crypto" / "BTCUSD_m1.csv").read_bytes())
    out = tmp_path / "new.toml"
    res = CliRunner().invoke(cli, ["calibrate", str(path), "--market", "crypto", "-o", str(out)])
    assert res.exit_code == 0, res.output
    doc = tomllib.loads(out.read_text())["instruments"]
    assert doc["MYCOIN"]["market"] == "crypto"
    mf.generate("MYCOIN", start="2024-06-01", days=1, seed=1, overrides=out)


def test_calibrating_identical_series_writes_a_correlation_generation_accepts(real, tmp_path):
    source = (real / "crypto" / "BTCUSD_m1.csv").read_bytes()
    files = [tmp_path / "COINA_m1.csv", tmp_path / "COINB_m1.csv"]
    for path in files:
        path.write_bytes(source)
    overrides = mf.calibrate(files, "crypto")
    assert overrides["COINB"]["correlations"]["COINA"] == 0.99
    mf.generate("COINA,COINB", start="2024-06-01", days=1, seed=1, overrides=overrides)


def test_calibrate_refuses_files_not_named_by_their_symbol(real, tmp_path):
    path = tmp_path / "data.csv"
    path.write_bytes((real / "crypto" / "BTCUSD_m1.csv").read_bytes())
    with pytest.raises(ValueError, match="SYMBOL_m1"):
        mf.calibrate([path], "crypto")


def test_calibrate_refuses_instruments_the_market_would_reject(real, tmp_path):
    path = tmp_path / "MYFX_m1.csv"
    path.write_bytes((real / "crypto" / "BTCUSD_m1.csv").read_bytes())
    with pytest.raises(ValueError, match="six"):
        mf.calibrate([path], "forex")
    res = CliRunner().invoke(cli, ["calibrate", str(path), "--market", "forex"])
    assert res.exit_code != 0
    assert "six" in res.output
    assert "Traceback" not in res.output
