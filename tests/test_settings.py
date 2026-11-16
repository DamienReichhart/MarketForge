import numpy as np
import pytest

from marketforge.config.defaults import get_market_defaults
from marketforge.config.settings import (
    AnomalyType,
    GARCHParams,
    MarketType,
    RegimeParams,
    RegimeType,
)
from marketforge.output.writers import OutputFormat


def test_garch_requires_stationarity():
    with pytest.raises(ValueError):
        GARCHParams(alpha=0.1, beta=0.85, gamma=0.2)


def test_regime_time_scale_stretches_durations_not_destinations():
    rp = RegimeParams(minutes_per_step=60)
    m = np.array(rp.per_minute_matrix())
    np.testing.assert_allclose(m.sum(axis=1), 1.0)
    base = np.array(RegimeParams().transition_matrix)
    off = ~np.eye(5, dtype=bool)
    np.testing.assert_allclose(m[off], base[off] / 60)
    assert rp.expected_durations()[0] == pytest.approx(60 / 0.15)
    with pytest.raises(ValueError):
        RegimeParams(minutes_per_step=0.5)


@pytest.mark.parametrize("market", list(MarketType))
def test_market_regimes_last_hours_not_minutes(market):
    durations = get_market_defaults(market).regime_params.expected_durations()
    assert min(durations) >= 120  # even crashes last a couple of hours


@pytest.mark.parametrize(
    "member", [MarketType.FOREX, AnomalyType.SPIKES, RegimeType.RANGE, OutputFormat.CSV]
)
def test_public_enums_format_as_their_value(member):
    # StrEnum contract (3.1.0): str() and f-strings give the value, not "Class.MEMBER".
    assert str(member) == member.value
    assert f"{member}" == member.value
    assert member == member.value
