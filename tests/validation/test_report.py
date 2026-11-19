import numpy as np

import marketforge as mf
from marketforge.domain.markets import MarketType
from marketforge.validation.reference import REFERENCES, bands_for
from marketforge.validation.report import ValidationReport, validate_returns


def test_report_flags_gaussian_as_too_thin_for_crypto():
    rng = np.random.default_rng(0)
    gaussian = rng.standard_normal(100_000) * 0.001
    report = validate_returns(gaussian, MarketType.CRYPTO)
    assert isinstance(report, ValidationReport)
    k = report.get("excess_kurtosis")
    assert k is not None and not k.passed


def test_report_overall_pass_property_aggregates():
    rng = np.random.default_rng(1)
    r = rng.standard_t(3.5, size=200_000) * 0.001
    report = validate_returns(r, MarketType.CRYPTO)
    assert isinstance(report.passed, bool)
    assert "excess_kurtosis" in report.metrics


def test_crypto_bands_are_anchored_to_real_data_and_others_marked_provisional():
    assert bands_for(MarketType.CRYPTO).anchored
    assert MarketType.CRYPTO in REFERENCES
    assert not bands_for(MarketType.STOCKS).anchored
    rng = np.random.default_rng(2)
    report = validate_returns(rng.standard_t(4, 50_000) * 1e-3, MarketType.STOCKS)
    assert "provisional" in report.summary()


def test_iid_returns_fail_long_memory():
    rng = np.random.default_rng(3)
    report = validate_returns(rng.standard_t(4, 100_000) * 1e-3, MarketType.CRYPTO)
    assert not report.get("long_memory").passed


def test_spread_checks_flag_absurd_levels_and_spreads_that_narrow_in_turbulence():
    frame = mf.generate("BTCUSD", start="2024-01-01", end="2024-01-15", seed=1, with_spread=True)[
        "BTCUSD"
    ]["m1"]
    good = mf.validate(frame, "crypto")
    assert good.passed and 1.0 < good.get("spread_widening").value < 1.35  # as measured
    # Crypto spread bands are anchored to measured quotes; the others are not.
    assert "spread_bps" in good.summary() and "provisional" not in good.summary()
    assert bands_for(MarketType.CRYPTO).spread_anchored
    assert not bands_for(MarketType.FOREX).spread_anchored
    assert "spread_bps" not in mf.validate(frame.drop(columns="spread"), "crypto").metrics

    wide = mf.validate(frame.assign(spread=frame["spread"] * 1000), "crypto")
    assert not wide.get("spread_bps").passed
    moves = np.log(frame["close"] / frame["open"]).abs().rolling(30).mean().fillna(0)
    inverted = frame.assign(spread=frame["close"] * 1e-4 / (1 + 2000 * moves))
    assert not mf.validate(inverted, "crypto").get("spread_widening").passed
