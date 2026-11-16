import numpy as np
from marketforge.config.settings import MarketType
from marketforge.validation.report import validate_returns, ValidationReport


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
    from marketforge.validation.reference import REFERENCES, bands_for

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
