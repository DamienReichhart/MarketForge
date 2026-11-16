import numpy as np
import pytest

from marketforge.config.defaults import get_market_defaults
from marketforge.config.model_params import GARCHParams, RegimeParams
from marketforge.domain.anomalies import AnomalyType
from marketforge.domain.markets import MarketType
from marketforge.domain.regimes import RegimeType
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
    with pytest.raises(ValueError):
        RegimeParams(minutes_per_step=0.5)


@pytest.mark.parametrize("market", list(MarketType))
def test_market_regimes_last_hours_not_minutes(market):
    rp = get_market_defaults(market).regime_params
    stay = np.diag(np.array(rp.per_minute_matrix()))
    durations = 1.0 / (1.0 - stay)  # mean length of each regime, in open minutes
    assert min(durations) >= 120  # even crashes last a couple of hours


@pytest.mark.parametrize(
    "member", [MarketType.FOREX, AnomalyType.SPIKES, RegimeType.RANGE, OutputFormat.CSV]
)
def test_public_enums_format_as_their_value(member):
    # StrEnum contract (3.1.0): str() and f-strings give the value, not "Class.MEMBER".
    assert str(member) == member.value
    assert f"{member}" == member.value
    assert member == member.value
