import pandas as pd
import pytest

import marketforge as mf


@pytest.fixture(scope="module")
def btc():
    return mf.generate("BTCUSD", start="2024-01-01", end="2024-01-15", seed=1, timeframes="m1,H1")[
        "BTCUSD"
    ]


def test_validate_accepts_generated_frames(btc):
    report = mf.validate(btc["m1"], "crypto")
    assert report.passed, report.summary()
    assert "at most" in report.summary() and "None" not in report.summary()


def test_validate_refuses_candles_that_are_not_m1(btc, tmp_path):
    with pytest.raises(ValueError, match="60-minute candles; the validation bands describe m1"):
        mf.validate(btc["H1"], "crypto")
    path = tmp_path / "BTCUSD_H1.csv"
    btc["H1"].rename_axis("timestamp").to_csv(path)  # ISO timestamps, as real data often has
    with pytest.raises(ValueError, match="60-minute candles"):
        mf.validate(path)


def test_validate_reads_the_market_from_a_marketforge_path(tmp_path):
    report = mf.generate_to_disk(
        tmp_path, "BTCUSD", start="2024-01-01", end="2024-01-15", seed=1, timeframes="m1"
    )
    path = report.paths["crypto"]["BTCUSD"]["m1"]
    assert mf.validate(path).market_type == "crypto"
    moved = tmp_path / "BTCUSD_m1.csv"
    path.rename(moved)
    assert mf.validate(moved).market_type == "crypto"  # from the symbol
    unknown = tmp_path / "mine.csv"
    moved.rename(unknown)
    with pytest.raises(ValueError, match="Cannot tell which market"):
        mf.validate(unknown)
    assert mf.validate(unknown, "crypto").passed


def test_validate_explains_unusable_input(btc):
    with pytest.raises(ValueError, match="market is required"):
        mf.validate(btc["m1"])
    with pytest.raises(ValueError, match="Unknown market 'fx'"):
        mf.validate(btc["m1"], "fx")
    with pytest.raises(ValueError, match="lacks column"):
        mf.validate(btc["m1"].drop(columns=["high"]), "crypto")
    with pytest.raises(ValueError, match="nothing to validate"):
        mf.validate(pd.DataFrame(columns=["open", "high", "low", "close"]), "crypto")
