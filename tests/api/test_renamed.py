import pytest
from click.testing import CliRunner

import marketforge as mf
from marketforge.cli.main import cli

RANGE = {"start": "2024-01-02", "days": 1}


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("include_regime", "with_regime"),
        ("include_spread", "with_spread"),
        ("include_bid_ask", "with_bid_ask"),
    ],
)
def test_old_argument_names_say_what_they_became(old, new):
    for function in (mf.generate, mf.estimate):
        with pytest.raises(TypeError, match=f"got {old}=, which MarketForge 5.0 renamed {new}="):
            function("BTCUSD", **RANGE, **{old: True})


def test_fmt_became_format(tmp_path):
    with pytest.raises(TypeError, match="renamed format="):
        mf.generate_to_disk(tmp_path, "BTCUSD", **RANGE, fmt="csv")


@pytest.mark.parametrize(
    ("args", "instead"),
    [
        (["generate", "--market", "crypto"], "use --markets"),
        (["generate", "--config", "x.toml"], "use --overrides"),
        (["list-instruments", "--market", "crypto"], "use --markets"),
        (["validate", "--input", "a.csv"], "marketforge validate PATH"),
    ],
)
def test_old_options_say_what_they_became(args, instead):
    res = CliRunner().invoke(cli, args)
    assert res.exit_code == 2
    assert "MarketForge 5.0 replaced" in res.output and instead in res.output


def test_timeframes_default_to_the_standard_eight_and_all_gives_every_one():
    data = mf.generate("BTCUSD", start="2024-01-01", days=7, seed=1)
    assert data.timeframes == ("m1", "m5", "m15", "m30", "H1", "H4", "D1", "W1")
    every = mf.estimate("BTCUSD", start="2024-01-01", days=7, timeframes="all")
    assert every.files == 17


def test_formats_take_any_letter_case(tmp_path):
    mf.generate_to_disk(tmp_path, "BTCUSD", **RANGE, seed=1, format="PARQUET", timeframes="m1")
    assert (tmp_path / "crypto" / "BTCUSD_m1.parquet").exists()
    with pytest.raises(
        ValueError, match="Unknown format 'xlsx'; choose from csv, parquet, feather"
    ):
        mf.generate_to_disk(tmp_path / "x", "BTCUSD", **RANGE, format="xlsx")
