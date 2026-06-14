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
