# MarketForge v2.0.0 Statistical Realism — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade MarketForge's synthetic OHLCV engine to reproduce real-market stylized facts (fat tails, leverage effect, intraday seasonality, realistic intrabar range, coherent volume) and add a validation harness that measures it.

**Architecture:** Keep the existing pipeline shape (config → ReturnGenerator → OHLCVBuilder → VolumeGenerator → AnomalyInjector → aggregation → CSV). Replace the *statistical core* of each model with a more realistic, vectorized implementation, add two new core modules (`innovations`, `seasonality`) and a new `validation` package. Specialized libs (`arch`, `statsmodels`) are used only in validation; the hot generation path stays numpy/scipy.

**Tech Stack:** Python 3.10+, numpy, scipy (incl. `scipy.signal.lfilter`), pandas, click, tqdm; `arch` + `statsmodels` for validation; pytest for tests.

**Reference spec:** `docs/superpowers/specs/2026-06-13-marketforge-realism-design.md`

**Conventions for every new `.py` file:** prepend the existing AGPL license header block (copy it verbatim from any current module, e.g. `marketforge/core/garch.py` lines 1–15). Test files do not need the header.

---

## File structure (created / modified)

| Path | Responsibility |
|---|---|
| `marketforge/core/innovations.py` | **new** — pluggable innovation generators (Gaussian, Student-t) |
| `marketforge/core/seasonality.py` | **new** — deterministic intraday/weekly volatility multiplier |
| `marketforge/utils/random.py` | add `chisquare` (needed by Student-t) |
| `marketforge/core/garch.py` | GJR-GARCH asymmetric variance update |
| `marketforge/config/settings.py` | extend `GARCHParams` (`gamma`), `GeneratorConfig` (`innovation_nu`, `volume_params`, `seasonality_enabled`); add `VolumeParams` |
| `marketforge/config/defaults.py` | model-parameter defaults per market (gamma, nu, volume AR); drop misleading `base_volatility`/`base_drift` |
| `marketforge/configs/loader.py` | wire new params into `GeneratorConfig` |
| `marketforge/core/returns.py` | use innovation generator + apply seasonality to volatility |
| `marketforge/generators/ohlcv.py` | vectorized Brownian-bridge High/Low |
| `marketforge/generators/volume.py` | log-AR(1) MDH volume model via `lfilter` |
| `marketforge/generators/anomalies.py` | vectorize spike/gap loops, recalibrate intensity |
| `marketforge/validation/__init__.py` | **new** package |
| `marketforge/validation/stylized_facts.py` | **new** — metric functions + target bands |
| `marketforge/validation/report.py` | **new** — `validate()` + `ValidationReport` |
| `marketforge/cli/parser.py` / `runner.py` | add `validate` subcommand |
| `tests/` | **new** — model unit tests, invariants, stylized-facts integration |
| `pyproject.toml`, `requirements.txt`, `setup.py` | deps + version bump to 2.0.0 |
| `README.md` | document v2 model + validation |

---

## Task 1: Dev/test environment + dependency + version bump

**Files:**
- Modify: `requirements.txt`, `pyproject.toml`, `setup.py`
- Create: `tests/__init__.py`, `tests/conftest.py`, `.gitignore` (append)

- [ ] **Step 1: Add validation/test deps to `requirements.txt`**

Append:

```
# Validation / diagnostics
arch>=6.3.0
statsmodels>=0.14.0
```

- [ ] **Step 2: Bump version + add dev/test extras in `pyproject.toml`**

In `pyproject.toml`, set the project version to `2.0.0` (find the `version = "1.0.0"` line and change it). Ensure an optional-dependencies dev group includes pytest and validation libs. Add/merge:

```toml
[project.optional-dependencies]
dev = ["mypy>=1.19.1", "pytest>=8.0.0", "arch>=6.3.0", "statsmodels>=0.14.0"]
```

Also bump `version` in `setup.py` if it hardcodes `1.0.0`.

- [ ] **Step 3: Ensure `.venv` is git-ignored**

Append to `.gitignore` if absent:

```
.venv/
.pytest_cache/
```

- [ ] **Step 4: Create the virtualenv and install editable with dev extras**

Run:
```bash
python3 -m venv .venv && . .venv/bin/activate && pip install -U pip && pip install -e ".[dev]"
```
Expected: installs numpy, scipy, pandas, click, tqdm, arch, statsmodels, pytest. **All subsequent `pytest`/`python` commands assume this venv is active.**

- [ ] **Step 5: Create test package + shared fixtures `tests/conftest.py`**

```python
"""Shared pytest fixtures for MarketForge tests."""
import numpy as np
import pytest

from marketforge.utils.random import RandomState


@pytest.fixture
def rng():
    return RandomState(42)


@pytest.fixture
def small_corr():
    """A simple 3-asset positive-definite correlation matrix."""
    return np.array([
        [1.0, 0.6, 0.3],
        [0.6, 1.0, 0.5],
        [0.3, 0.5, 1.0],
    ])
```

`tests/__init__.py` is empty.

- [ ] **Step 6: Verify pytest collects**

Run: `pytest -q`
Expected: `no tests ran` (exit 5) or `0 passed` — confirms collection works with no errors.

- [ ] **Step 7: Commit**

```bash
git add requirements.txt pyproject.toml setup.py .gitignore tests/__init__.py tests/conftest.py
git commit -m "build: add validation deps, pytest scaffold, bump to v2.0.0"
```

---

## Task 2: `RandomState.chisquare` (mixing variable for Student-t)

**Files:**
- Modify: `marketforge/utils/random.py`
- Test: `tests/test_random.py`

- [ ] **Step 1: Write the failing test**

```python
import numpy as np
from marketforge.utils.random import RandomState


def test_chisquare_mean_and_reproducibility():
    rng = RandomState(7)
    x = rng.chisquare(df=5, size=200_000)
    # E[chi2_k] = k
    assert abs(x.mean() - 5.0) < 0.1
    assert np.all(x > 0)

    rng.reset()
    y = rng.chisquare(df=5, size=10)
    rng2 = RandomState(7)
    z = rng2.chisquare(df=5, size=10)
    assert np.allclose(y, z)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_random.py -v`
Expected: FAIL — `AttributeError: 'RandomState' object has no attribute 'chisquare'`.

- [ ] **Step 3: Add the method**

In `marketforge/utils/random.py`, add to the `RandomState` class (after `integers`):

```python
    def chisquare(
        self,
        df: float,
        size: Optional[int | tuple[int, ...]] = None
    ) -> np.ndarray:
        """
        Generate samples from a chi-square distribution.

        Args:
            df: Degrees of freedom (> 0).
            size: Output shape.

        Returns:
            Array of random samples.
        """
        return self._generator.chisquare(df, size)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_random.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add marketforge/utils/random.py tests/test_random.py
git commit -m "feat(random): add chisquare for Student-t mixing variable"
```

---

## Task 3: Pluggable innovations — Gaussian + multivariate Student-t

**Files:**
- Create: `marketforge/core/innovations.py`
- Test: `tests/test_innovations.py`

- [ ] **Step 1: Write the failing test**

```python
import numpy as np
from scipy.linalg import cholesky

from marketforge.utils.random import RandomState
from marketforge.core.innovations import GaussianInnovations, StudentTInnovations


def _chol(corr):
    return cholesky(corr + np.eye(corr.shape[0]) * 1e-12, lower=True)


def test_gaussian_unit_variance_and_correlation(small_corr):
    L = _chol(small_corr)
    gen = GaussianInnovations()
    x = gen.generate(RandomState(1), n_steps=200_000, n_assets=3, cholesky_lower=L)
    assert x.shape == (200_000, 3)
    # marginal variance ~ 1
    assert np.allclose(x.var(axis=0), 1.0, atol=0.05)
    # recovers correlation
    assert np.allclose(np.corrcoef(x.T), small_corr, atol=0.02)


def test_student_t_unit_variance_fat_tails_and_correlation(small_corr):
    L = _chol(small_corr)
    gen = StudentTInnovations(nu=5.0)
    x = gen.generate(RandomState(2), n_steps=400_000, n_assets=3, cholesky_lower=L)
    # standardized to unit variance
    assert np.allclose(x.var(axis=0), 1.0, atol=0.06)
    # excess kurtosis of standardized t with nu=5 is 6/(nu-4) = 6 -> heavy tails (>> 0)
    from scipy.stats import kurtosis
    assert kurtosis(x[:, 0]) > 2.0
    # correlation preserved
    assert np.allclose(np.corrcoef(x.T), small_corr, atol=0.03)


def test_student_t_requires_nu_above_two():
    import pytest
    with pytest.raises(ValueError):
        StudentTInnovations(nu=2.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_innovations.py -v`
Expected: FAIL — `ModuleNotFoundError: marketforge.core.innovations`.

- [ ] **Step 3: Implement `marketforge/core/innovations.py`**

(Prepend the AGPL header.)

```python
"""
Pluggable innovation generators for correlated return shocks.

Provides the standardized (unit-variance) correlated innovations z_t that drive
the GARCH/return recursion. Two implementations:

- GaussianInnovations: classic multivariate normal (thin tails).
- StudentTInnovations: multivariate Student-t via a normal-variance mixture,
  giving heavy tails AND tail dependence (assets get extreme draws together).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import numpy as np

from marketforge.utils.random import RandomState


class InnovationGenerator(ABC):
    """Abstract base for correlated, unit-variance innovation generators."""

    @abstractmethod
    def generate(
        self,
        rng: RandomState,
        n_steps: int,
        n_assets: int,
        cholesky_lower: np.ndarray,
    ) -> np.ndarray:
        """
        Generate correlated innovations of shape (n_steps, n_assets).

        The result has (approximately) unit marginal variance per asset and a
        correlation matrix equal to ``cholesky_lower @ cholesky_lower.T``.
        """
        raise NotImplementedError


class GaussianInnovations(InnovationGenerator):
    """Multivariate standard-normal innovations (thin tails)."""

    def generate(
        self,
        rng: RandomState,
        n_steps: int,
        n_assets: int,
        cholesky_lower: np.ndarray,
    ) -> np.ndarray:
        z = rng.standard_normal((n_steps, n_assets))
        return z @ cholesky_lower.T


class StudentTInnovations(InnovationGenerator):
    """
    Multivariate Student-t innovations via normal-variance mixture.

    Construction:
        Y = Z @ Lᵀ              correlated normals
        W = chi2(nu) / nu       shared mixing variable per time step
        T = Y / sqrt(W)         multivariate-t (E[T Tᵀ] = nu/(nu-2) · Σ)
        z = T * sqrt((nu-2)/nu) standardized to unit variance

    A single shared W per row yields joint tail dependence (simultaneous
    extreme moves across assets), a documented feature of real markets.
    """

    def __init__(self, nu: float) -> None:
        if nu <= 2.0:
            raise ValueError(f"nu must be > 2 for finite variance, got {nu}")
        self._nu = float(nu)

    @property
    def nu(self) -> float:
        return self._nu

    def generate(
        self,
        rng: RandomState,
        n_steps: int,
        n_assets: int,
        cholesky_lower: np.ndarray,
    ) -> np.ndarray:
        z = rng.standard_normal((n_steps, n_assets))
        correlated = z @ cholesky_lower.T
        mixing = rng.chisquare(self._nu, size=n_steps) / self._nu  # (n_steps,)
        t = correlated / np.sqrt(mixing)[:, None]
        return t * np.sqrt((self._nu - 2.0) / self._nu)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_innovations.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add marketforge/core/innovations.py tests/test_innovations.py
git commit -m "feat(core): add Gaussian and multivariate Student-t innovations"
```

---

## Task 4: GJR-GARCH asymmetric volatility (leverage effect)

**Files:**
- Modify: `marketforge/config/settings.py` (`GARCHParams.gamma`)
- Modify: `marketforge/core/garch.py` (`GARCHModel` GJR update + omega scaling)
- Test: `tests/test_garch.py`

- [ ] **Step 1: Write the failing test**

```python
import numpy as np
from marketforge.config.settings import GARCHParams
from marketforge.core.garch import GARCHModel
from marketforge.utils.random import RandomState


def test_gamma_default_zero_is_symmetric():
    p = GARCHParams(alpha=0.05, beta=0.90)
    assert p.gamma == 0.0
    # persistence includes gamma/2
    assert abs(p.persistence - 0.95) < 1e-12


def test_stationarity_constraint_includes_gamma():
    import pytest
    # alpha + beta + gamma/2 must be < 1
    with pytest.raises(ValueError):
        GARCHParams(alpha=0.10, beta=0.90, gamma=0.10)  # 0.10+0.90+0.05 = 1.05


def test_long_run_variance_matches_base_volatility():
    base_vol = 0.30  # annualized
    p = GARCHParams(alpha=0.06, beta=0.88, gamma=0.04)
    model = GARCHModel(p, base_volatility=base_vol)
    per_minute_var = (base_vol ** 2) / (252 * 24 * 60)
    assert abs(model.unconditional_variance - per_minute_var) / per_minute_var < 1e-9


def test_negative_shocks_raise_volatility_more():
    """GJR: a negative innovation must produce higher next variance than a
    positive innovation of equal magnitude."""
    p = GARCHParams(alpha=0.05, beta=0.90, gamma=0.10)
    m_neg = GARCHModel(p, base_volatility=0.3)
    m_pos = GARCHModel(p, base_volatility=0.3)
    m_neg.initialize_state()
    m_pos.initialize_state()
    s_neg = m_neg.step(-2.0)  # large negative innovation
    s_pos = m_pos.step(+2.0)  # large positive innovation
    # after one identical-magnitude shock, the *next* variance differs:
    n_neg = m_neg.step(0.0).variance
    n_pos = m_pos.step(0.0).variance
    assert n_neg > n_pos
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_garch.py -v`
Expected: FAIL — `GARCHParams` has no `gamma`.

- [ ] **Step 3: Add `gamma` to `GARCHParams`**

In `marketforge/config/settings.py`, modify the `GARCHParams` dataclass: add the field and update validation/properties.

```python
@dataclass(frozen=True)
class GARCHParams:
    """
    GJR-GARCH(1,1) parameters for asymmetric conditional volatility.

    σ²_t = ω + (α + γ·1[ε_{t-1} < 0])·ε²_{t-1} + β·σ²_{t-1}

    Constraints: ω > 0, α ≥ 0, β ≥ 0, γ ≥ 0, and α + β + γ/2 < 1 (stationarity).
    γ > 0 introduces the leverage effect: negative shocks raise volatility more.
    """
    omega: float = 0.00001
    alpha: float = 0.05
    beta: float = 0.90
    gamma: float = 0.0

    def __post_init__(self) -> None:
        if self.omega <= 0:
            raise ValueError(f"omega must be positive, got {self.omega}")
        if self.alpha < 0:
            raise ValueError(f"alpha must be non-negative, got {self.alpha}")
        if self.beta < 0:
            raise ValueError(f"beta must be non-negative, got {self.beta}")
        if self.gamma < 0:
            raise ValueError(f"gamma must be non-negative, got {self.gamma}")
        if self.persistence >= 1:
            raise ValueError(
                f"alpha + beta + gamma/2 must be < 1 for stationarity, "
                f"got {self.persistence}"
            )

    @property
    def persistence(self) -> float:
        """Volatility persistence α + β + γ/2 (γ/2 = expected leverage contribution)."""
        return self.alpha + self.beta + self.gamma / 2.0

    @property
    def long_run_variance(self) -> float:
        return self.omega / (1 - self.persistence)
```

- [ ] **Step 4: Apply GJR update in `GARCHModel`**

In `marketforge/core/garch.py`:

(a) In `__init__`, the persistence used for omega scaling now comes from `params.persistence`. Replace the persistence computation:

```python
        # Scale omega so long-run variance == base_volatility (per-minute)
        target_variance = (base_volatility ** 2) / (252 * 24 * 60)  # Per-minute
        persistence = params.persistence  # alpha + beta + gamma/2
        self._scaled_omega = target_variance * (1 - persistence)
        self._initial_variance = self._scaled_omega / (1 - persistence)
        self._state: Optional[GARCHState] = None
```

(b) In `step`, use the asymmetric (GJR) update:

```python
    def step(self, innovation: float) -> GARCHState:
        if self._state is None:
            self.initialize_state()

        prev_shock = self._state.shock
        # Leverage indicator on the sign of the previous shock ε_{t-1}
        leverage = self._params.gamma if prev_shock < 0 else 0.0

        new_variance = (
            self._scaled_omega
            + (self._params.alpha + leverage) * (prev_shock ** 2)
            + self._params.beta * self._state.variance
        )

        new_volatility = np.sqrt(new_variance)
        new_shock = new_volatility * innovation

        self._state = GARCHState(variance=new_variance, shock=new_shock)
        return self._state
```

(c) The `half_life` property currently uses `self._params.persistence` — it still works (now includes γ/2). No change needed.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_garch.py -v`
Expected: PASS (4 tests).

- [ ] **Step 6: Run the full suite (no regressions)**

Run: `pytest -q`
Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add marketforge/config/settings.py marketforge/core/garch.py tests/test_garch.py
git commit -m "feat(core): GJR-GARCH asymmetric volatility (leverage effect)"
```

---

## Task 5: Intraday/weekly volatility seasonality

**Files:**
- Create: `marketforge/core/seasonality.py`
- Test: `tests/test_seasonality.py`

- [ ] **Step 1: Write the failing test**

```python
import numpy as np
from marketforge.config.settings import MarketType
from marketforge.core.seasonality import SeasonalityModel


def _one_day_minutely():
    # 1440 one-minute timestamps starting at a Monday 00:00 UTC (2024-01-01 is Monday)
    start = 1704067200
    return np.arange(start, start + 1440 * 60, 60, dtype=np.int64)


def test_multiplier_is_positive_and_variance_neutral():
    ts = _one_day_minutely()
    for mt in (MarketType.STOCKS, MarketType.FOREX, MarketType.CRYPTO):
        s = SeasonalityModel(mt).multiplier_series(ts)
        assert s.shape == ts.shape
        assert np.all(s > 0)
        # variance-neutral: mean of s^2 over the window ~ 1
        assert abs(np.mean(s ** 2) - 1.0) < 1e-6


def test_stocks_open_close_exceed_midday():
    ts = _one_day_minutely()
    s = SeasonalityModel(MarketType.STOCKS).multiplier_series(ts)
    minutes = (ts % 86400) // 60
    open_v = s[np.argmin(np.abs(minutes - 870))]    # ~14:30 UTC
    close_v = s[np.argmin(np.abs(minutes - 1260))]  # ~21:00 UTC
    midday = s[np.argmin(np.abs(minutes - 1065))]   # ~17:45 UTC (between)
    assert open_v > midday
    assert close_v > midday


def test_crypto_weekend_below_weekday():
    # Saturday vs Wednesday, same time of day
    sat = np.array([1704153600 + 12 * 3600], dtype=np.int64)   # 2024-01-06 is Saturday
    wed = np.array([1704456000 + 0], dtype=np.int64)           # 2024-01-10 is Wednesday-ish
    model = SeasonalityModel(MarketType.CRYPTO)
    # Use a shared normalization window so comparison is meaningful
    combo = np.concatenate([sat, wed])
    s = model.multiplier_series(combo)
    assert s[0] < s[1]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_seasonality.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement `marketforge/core/seasonality.py`**

(Prepend AGPL header.)

```python
"""
Deterministic intraday and weekly volatility seasonality.

Real markets concentrate volatility at specific times (equity open/close,
FX session overlaps) and quieter periods (lunch, weekends for crypto). This
module produces a strictly-positive multiplicative factor s(t) applied to the
per-minute conditional volatility (and reused by the volume model).

The factor is variance-neutralized over the generated window (mean(s²) == 1)
so it reshapes *when* volatility occurs without changing the asset's overall
configured volatility level.
"""

from __future__ import annotations

import numpy as np

from marketforge.config.settings import MarketType

SECONDS_PER_DAY = 86400

# US cash session in UTC minutes-of-day (EST baseline ~14:30–21:00).
_STOCK_OPEN_MIN = 870
_STOCK_CLOSE_MIN = 1260

# FX session windows (UTC minutes-of-day).
_FX_LONDON = (420, 960)        # 07:00–16:00
_FX_NY_OVERLAP = (780, 960)    # 13:00–16:00
_FX_ASIAN = (0, 420)           # 00:00–07:00


class SeasonalityModel:
    """Per-market deterministic volatility seasonality factor."""

    def __init__(self, market_type: MarketType) -> None:
        self._market_type = market_type

    def multiplier_series(self, timestamps: np.ndarray) -> np.ndarray:
        """
        Return a positive, variance-neutral seasonality factor per timestamp.

        Args:
            timestamps: int64 Unix seconds, shape (n,).

        Returns:
            float array shape (n,) with mean(s²) == 1 over the window.
        """
        minutes = (timestamps % SECONDS_PER_DAY) // 60  # minute-of-day [0,1440)
        # day-of-week with Monday=0 (1970-01-01 was a Thursday => +3)
        dow = ((timestamps // SECONDS_PER_DAY) + 3) % 7

        if self._market_type == MarketType.STOCKS:
            shape = self._stock_shape(minutes)
        elif self._market_type == MarketType.FOREX:
            shape = self._forex_shape(minutes, dow)
        else:
            shape = self._crypto_shape(minutes, dow)

        shape = np.maximum(shape, 1e-3)
        # variance-neutralize over the window
        norm = np.sqrt(np.mean(shape ** 2))
        return shape / norm

    @staticmethod
    def _stock_shape(minutes: np.ndarray) -> np.ndarray:
        in_session = (minutes >= _STOCK_OPEN_MIN) & (minutes <= _STOCK_CLOSE_MIN)
        base = np.where(in_session, 1.0, 0.45)
        # smooth U-shape: bumps at open and close
        open_bump = 0.9 * np.exp(-((minutes - _STOCK_OPEN_MIN) / 25.0) ** 2)
        close_bump = 0.7 * np.exp(-((minutes - _STOCK_CLOSE_MIN) / 25.0) ** 2)
        return base + open_bump + close_bump

    @staticmethod
    def _forex_shape(minutes: np.ndarray, dow: np.ndarray) -> np.ndarray:
        s = np.full(minutes.shape, 0.7)
        london = (minutes >= _FX_LONDON[0]) & (minutes < _FX_LONDON[1])
        overlap = (minutes >= _FX_NY_OVERLAP[0]) & (minutes < _FX_NY_OVERLAP[1])
        asian = (minutes >= _FX_ASIAN[0]) & (minutes < _FX_ASIAN[1])
        s[london] = 1.2
        s[overlap] = 1.5
        s[asian] = 0.8
        # FX effectively closed on weekends
        s = np.where(dow >= 5, s * 0.3, s)
        return s

    @staticmethod
    def _crypto_shape(minutes: np.ndarray, dow: np.ndarray) -> np.ndarray:
        # mild diurnal cycle (slightly higher around US/EU afternoon) + weekend dip
        diurnal = 1.0 + 0.12 * np.sin((minutes / 1440.0) * 2 * np.pi - 1.0)
        weekend = np.where(dow >= 5, 0.82, 1.0)
        return diurnal * weekend
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_seasonality.py -v`
Expected: PASS (3 tests).

> Note: if `test_crypto_weekend_below_weekday` is flaky due to chosen timestamps, fix the timestamps in the test to a known Saturday vs Wednesday at the same minute-of-day; do **not** weaken the model.

- [ ] **Step 5: Commit**

```bash
git add marketforge/core/seasonality.py tests/test_seasonality.py
git commit -m "feat(core): intraday/weekly volatility seasonality (variance-neutral)"
```

---

## Task 6: Config plumbing — innovation ν, volume params, seasonality flag

**Files:**
- Modify: `marketforge/config/settings.py` (`VolumeParams`, `GeneratorConfig` fields)
- Test: `tests/test_settings.py`

- [ ] **Step 1: Write the failing test**

```python
import numpy as np
from marketforge.config.settings import (
    GeneratorConfig, AssetConfig, MarketType, VolumeParams,
)


def _cfg(**kw):
    return GeneratorConfig(
        assets=[AssetConfig("X", start_price=100.0, volatility=0.3)],
        market_type=MarketType.CRYPTO,
        start_timestamp=1704067200,
        end_timestamp=1704067200 + 3600,
        **kw,
    )


def test_new_fields_have_defaults():
    cfg = _cfg()
    assert cfg.innovation_nu is None            # None => Gaussian
    assert cfg.seasonality_enabled is True
    assert isinstance(cfg.volume_params, VolumeParams)
    assert 0 < cfg.volume_params.phi < 1


def test_volume_params_validation():
    import pytest
    with pytest.raises(ValueError):
        VolumeParams(phi=1.0)   # must be < 1
    with pytest.raises(ValueError):
        VolumeParams(phi=-0.1)


def test_innovation_nu_must_exceed_two():
    import pytest
    with pytest.raises(ValueError):
        _cfg(innovation_nu=1.5)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_settings.py -v`
Expected: FAIL — `VolumeParams` / `innovation_nu` missing.

- [ ] **Step 3: Add `VolumeParams` and extend `GeneratorConfig`**

In `marketforge/config/settings.py`, add the dataclass (near `AnomalyConfig`):

```python
@dataclass(frozen=True)
class VolumeParams:
    """
    Parameters for the log-AR(1) volume model.

    log V_t = μ + φ·(log V_{t-1} − μ) + λ·|z_t| + log s(t) + η_t

    Attributes:
        phi: AR(1) persistence of log-volume (volume clustering), 0 ≤ φ < 1.
        lam: Sensitivity to absolute standardized returns (MDH coupling).
        noise_sigma: Std of the idiosyncratic log-volume noise η.
    """
    phi: float = 0.7
    lam: float = 0.3
    noise_sigma: float = 0.4

    def __post_init__(self) -> None:
        if not (0.0 <= self.phi < 1.0):
            raise ValueError(f"phi must be in [0, 1), got {self.phi}")
        if self.lam < 0:
            raise ValueError(f"lam must be non-negative, got {self.lam}")
        if self.noise_sigma < 0:
            raise ValueError(f"noise_sigma must be non-negative, got {self.noise_sigma}")
```

Then add three fields to `GeneratorConfig` (after `anomaly_config`):

```python
    innovation_nu: Optional[float] = None  # None => Gaussian; else Student-t df
    seasonality_enabled: bool = True
    volume_params: VolumeParams = field(default_factory=VolumeParams)
```

And in `GeneratorConfig.__post_init__`, after the existing checks, add:

```python
        if self.innovation_nu is not None and self.innovation_nu <= 2.0:
            raise ValueError(
                f"innovation_nu must be > 2 for finite variance, got {self.innovation_nu}"
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_settings.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add marketforge/config/settings.py tests/test_settings.py
git commit -m "feat(config): add innovation_nu, volume_params, seasonality flag"
```

---

## Task 7: Per-market model-parameter defaults + loader wiring

**Files:**
- Modify: `marketforge/config/defaults.py` (add gamma, nu, volume params; drop misleading base_volatility/base_drift)
- Modify: `marketforge/configs/loader.py` (`market_config_to_generator_config`)
- Test: `tests/test_defaults_wiring.py`

- [ ] **Step 1: Write the failing test**

```python
from marketforge.configs.loader import market_config_to_generator_config, load_market_config
from marketforge.config.settings import MarketType


def test_generator_config_gets_market_model_params():
    mc = load_market_config("crypto")
    gc = market_config_to_generator_config(
        mc, start_timestamp=1704067200, end_timestamp=1704067200 + 3600,
        seed=1, batch_symbols=mc.symbols[:3],
    )
    # crypto uses Student-t with low df and a leverage gamma > 0
    assert gc.innovation_nu is not None and gc.innovation_nu <= 4.0
    assert gc.garch_params.gamma > 0.0
    assert gc.volume_params.phi > 0.0


def test_forex_has_higher_nu_than_crypto():
    fx = market_config_to_generator_config(
        load_market_config("forex"), 1704067200, 1704067200 + 3600, batch_symbols=["EURUSD"],
    )
    cr = market_config_to_generator_config(
        load_market_config("crypto"), 1704067200, 1704067200 + 3600,
        batch_symbols=load_market_config("crypto").symbols[:1],
    )
    assert fx.innovation_nu > cr.innovation_nu
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_defaults_wiring.py -v`
Expected: FAIL — loader does not set `innovation_nu`/`volume_params`; defaults lack these.

- [ ] **Step 3: Extend `MarketDefaults` and the three market default objects**

In `marketforge/config/defaults.py`:

(a) Add fields to the `MarketDefaults` dataclass (remove the misleading `base_volatility`/`base_drift` — per-asset configs are authoritative; if other code references them, keep them but they are no longer used for generation). Add:

```python
    innovation_nu: float
    volume_params: "VolumeParams"
```

and import `VolumeParams`:

```python
from marketforge.config.settings import (
    MarketType, GARCHParams, RegimeParams, AnomalyConfig, AnomalyType, RegimeType,
    VolumeParams,
)
```

(b) Update each defaults object's `garch_params` to include `gamma`, and add `innovation_nu` + `volume_params`:

- `CRYPTO_DEFAULTS`: `garch_params=GARCHParams(omega=0.00002, alpha=0.08, beta=0.88, gamma=0.04)`, `innovation_nu=3.5`, `volume_params=VolumeParams(phi=0.72, lam=0.35, noise_sigma=0.5)`.
- `FOREX_DEFAULTS`: `garch_params=GARCHParams(omega=0.000005, alpha=0.04, beta=0.92, gamma=0.03)`, `innovation_nu=6.0`, `volume_params=VolumeParams(phi=0.6, lam=0.25, noise_sigma=0.35)`.
- `STOCKS_DEFAULTS`: `garch_params=GARCHParams(omega=0.00001, alpha=0.05, beta=0.90, gamma=0.06)`, `innovation_nu=4.5`, `volume_params=VolumeParams(phi=0.7, lam=0.3, noise_sigma=0.45)`.

(Each pre-existing `MarketDefaults(...)` call must now also pass `innovation_nu=` and `volume_params=`; add them.)

> Stationarity check: crypto 0.08+0.88+0.02=0.98 ✓; forex 0.04+0.92+0.015=0.975 ✓; stocks 0.05+0.90+0.03=0.98 ✓.

- [ ] **Step 4: Wire params through `market_config_to_generator_config`**

In `marketforge/configs/loader.py`, in `market_config_to_generator_config`, after `market_defaults = get_market_defaults(...)`, pass the new fields into the returned `GeneratorConfig`:

```python
    return GeneratorConfig(
        assets=asset_configs,
        market_type=settings_market_type,
        start_timestamp=start_timestamp,
        end_timestamp=end_timestamp,
        correlation_matrix=correlation_matrix,
        garch_params=market_defaults.garch_params,
        regime_params=market_defaults.regime_params,
        anomaly_config=anomaly_config,
        output_dir=output_dir,
        seed=seed,
        timeframes=timeframes,
        show_progress=show_progress,
        innovation_nu=market_defaults.innovation_nu,
        volume_params=market_defaults.volume_params,
    )
```

- [ ] **Step 5: Run tests + full suite**

Run: `pytest tests/test_defaults_wiring.py -v && pytest -q`
Expected: PASS, no regressions.

- [ ] **Step 6: Commit**

```bash
git add marketforge/config/defaults.py marketforge/configs/loader.py tests/test_defaults_wiring.py
git commit -m "feat(config): per-market gamma/nu/volume defaults wired into generator"
```

---

## Task 8: ReturnGenerator — Student-t innovations + seasonality overlay

**Files:**
- Modify: `marketforge/core/returns.py`
- Test: `tests/test_returns.py`

- [ ] **Step 1: Write the failing test**

```python
import numpy as np
from marketforge.config.settings import GeneratorConfig, AssetConfig, MarketType
from marketforge.core.returns import ReturnGenerator
from marketforge.utils.random import RandomState


def _cfg(nu=None, seasonal=True, n_assets=2):
    assets = [AssetConfig(f"A{i}", start_price=100.0, volatility=0.5) for i in range(n_assets)]
    corr = np.eye(n_assets)
    return GeneratorConfig(
        assets=assets, market_type=MarketType.CRYPTO,
        start_timestamp=1704067200, end_timestamp=1704067200 + 2 * 86400,  # 2 days
        correlation_matrix=corr, seed=11,
        innovation_nu=nu, seasonality_enabled=seasonal,
    )


def test_student_t_returns_have_fatter_tails_than_gaussian():
    from scipy.stats import kurtosis
    g = ReturnGenerator(_cfg(nu=None))
    t = ReturnGenerator(_cfg(nu=3.5))
    rg = g.generate(RandomState(1)).returns[:, 0]
    rt = t.generate(RandomState(1)).returns[:, 0]
    assert kurtosis(rt) > kurtosis(rg)


def test_seasonality_changes_conditional_volatility_shape():
    gen = ReturnGenerator(_cfg(nu=None, seasonal=True))
    res = gen.generate(RandomState(2))
    minutes = (res.timestamps % 86400) // 60
    vol = res.volatilities[:, 0]
    # crypto seasonality is mild but present: weekend/diurnal structure -> not constant
    assert vol.std() / vol.mean() > 1e-3


def test_reproducible():
    gen = ReturnGenerator(_cfg(nu=4.0))
    a = gen.generate(RandomState(5)).returns
    b = gen.generate(RandomState(5)).returns
    assert np.allclose(a, b)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_returns.py -v`
Expected: FAIL — generator still uses Gaussian-only path; `test_student_t...` fails (kurtosis equal).

- [ ] **Step 3: Modify `ReturnGenerator`**

In `marketforge/core/returns.py`:

(a) Add imports at top:

```python
from marketforge.core.innovations import (
    InnovationGenerator, GaussianInnovations, StudentTInnovations,
)
from marketforge.core.seasonality import SeasonalityModel
```

(b) In `__init__`, after building `self._correlation_engine`, build the innovation generator and seasonality model:

```python
        nu = getattr(config, "innovation_nu", None)
        self._innovation_gen: InnovationGenerator = (
            StudentTInnovations(nu) if nu is not None else GaussianInnovations()
        )
        self._seasonality = (
            SeasonalityModel(config.market_type)
            if getattr(config, "seasonality_enabled", True) else None
        )
```

(c) In `generate`, replace Step 1 (innovation generation):

```python
        # Step 1: Generate correlated, unit-variance innovations (Gaussian or Student-t)
        innovations = self._innovation_gen.generate(
            rng, n_steps, self._n_assets, self._correlation_engine.cholesky_matrix
        )
```

(d) After Step 2 (regime multipliers), compute the seasonality factor once:

```python
        # Seasonality overlay (variance-neutral); ones if disabled
        if self._seasonality is not None:
            seasonal = self._seasonality.multiplier_series(timestamps)
        else:
            seasonal = np.ones(n_steps)
```

(e) In Step 3, apply seasonality to each asset's volatility:

```python
            volatilities[:, i] = base_vols * vol_mults * seasonal
```

- [ ] **Step 4: Run tests + full suite**

Run: `pytest tests/test_returns.py -v && pytest -q`
Expected: PASS, no regressions.

- [ ] **Step 5: Commit**

```bash
git add marketforge/core/returns.py tests/test_returns.py
git commit -m "feat(core): Student-t innovations and seasonality in ReturnGenerator"
```

---

## Task 9: Vectorized Brownian-bridge intrabar OHLC

**Files:**
- Modify: `marketforge/generators/ohlcv.py` (replace `_generate_high_low` + the per-candle loop)
- Test: `tests/test_ohlcv_bridge.py`

- [ ] **Step 1: Write the failing test**

```python
import numpy as np
from marketforge.generators.ohlcv import intrabar_high_low
from marketforge.utils.random import RandomState


def test_high_low_bracket_open_close():
    rng = RandomState(3)
    n = 5000
    openp = np.full(n, 100.0)
    closep = 100.0 * np.exp(rng.normal(0, 0.001, n))
    sigma = np.full(n, 0.001)
    high, low = intrabar_high_low(rng, openp, closep, sigma, k=8)
    body_high = np.maximum(openp, closep)
    body_low = np.minimum(openp, closep)
    assert np.all(high >= body_high - 1e-9)
    assert np.all(low <= body_low + 1e-9)
    assert np.all(high >= low)
    assert np.all(low > 0)


def test_range_scales_with_volatility():
    rng = RandomState(4)
    n = 20000
    openp = np.full(n, 100.0)
    closep = np.full(n, 100.0)
    lo_sigma = np.full(n, 0.0005)
    hi_sigma = np.full(n, 0.005)
    h1, l1 = intrabar_high_low(RandomState(4), openp, closep, lo_sigma, k=8)
    h2, l2 = intrabar_high_low(RandomState(4), openp, closep, hi_sigma, k=8)
    assert np.mean(h2 - l2) > 3 * np.mean(h1 - l1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_ohlcv_bridge.py -v`
Expected: FAIL — `intrabar_high_low` not defined.

- [ ] **Step 3: Implement the vectorized bridge + rewire the builder**

In `marketforge/generators/ohlcv.py`, add a module-level function:

```python
def intrabar_high_low(
    rng: RandomState,
    open_prices: np.ndarray,
    close_prices: np.ndarray,
    bar_volatility: np.ndarray,
    k: int = 8,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Vectorized intrabar High/Low via a Brownian bridge from open to close.

    The within-bar log-price is modeled as a Brownian bridge pinned at
    log(open) and log(close) with per-bar diffusion ``bar_volatility`` (the
    per-minute conditional volatility). High/Low are the running max/min of the
    bridge over ``k`` interior sub-steps. Guarantees High ≥ max(O,C) and
    Low ≤ min(O,C) by construction, with range scaling correctly with vol.

    Args:
        rng: Random state.
        open_prices, close_prices: shape (n,) price arrays (> 0).
        bar_volatility: shape (n,) per-bar log-volatility (std over the bar).
        k: number of interior sub-steps.

    Returns:
        (high, low) arrays of shape (n,).
    """
    n = open_prices.shape[0]
    log_o = np.log(open_prices)
    log_c = np.log(close_prices)

    # Brownian bridge on grid t_j = j/(k+1), j=1..k (interior points).
    # Build a standard BM via cumulative normal increments, then subtract the
    # linear interpolation of its endpoints to pin it to zero at both ends.
    incs = rng.standard_normal((n, k + 1)) * np.sqrt(1.0 / (k + 1))
    bm = np.cumsum(incs, axis=1)                      # (n, k+1); bm[:, -1] = B(1)
    t = np.linspace(1.0 / (k + 1), 1.0, k + 1)        # times of bm columns
    bridge = bm - t[None, :] * bm[:, -1][:, None]     # pin endpoint to 0
    bridge = bridge[:, :-1]                           # drop endpoint (==0); (n, k)
    t_int = t[:-1]                                    # interior times; (k,)

    # Scale bridge by per-bar volatility -> intrabar log deviations.
    deviations = bridge * bar_volatility[:, None]     # (n, k)

    # Linear log-price interpolation between open and close at interior times.
    base = log_o[:, None] + np.outer(log_c - log_o, t_int)  # (n, k)
    log_path = base + deviations

    # Candidate extremes include the two endpoints (open, close) and interior path.
    path_high = np.maximum(np.exp(log_path).max(axis=1), np.maximum(open_prices, close_prices))
    path_low = np.minimum(np.exp(log_path).min(axis=1), np.minimum(open_prices, close_prices))
    return path_high, path_low
```

Then in `OHLCVBuilder._build_single_asset`, replace the per-candle high/low loop (the `for i in range(n): high_prices[i], low_prices[i] = self._generate_high_low(...)` block) with a single vectorized call:

```python
        # Vectorized intrabar high/low via Brownian bridge
        high_prices, low_prices = intrabar_high_low(
            rng,
            open_prices=open_prices,
            close_prices=close_prices,
            bar_volatility=volatilities,
            k=8,
        )
```

Delete the now-unused `_generate_high_low` method.

- [ ] **Step 4: Run tests + full suite**

Run: `pytest tests/test_ohlcv_bridge.py -v && pytest -q`
Expected: PASS, no regressions.

- [ ] **Step 5: Commit**

```bash
git add marketforge/generators/ohlcv.py tests/test_ohlcv_bridge.py
git commit -m "feat(generators): vectorized Brownian-bridge intrabar OHLC"
```

---

## Task 10: Coherent log-AR(1) volume model

**Files:**
- Modify: `marketforge/generators/volume.py`
- Modify: `marketforge/generators/ohlcv.py` (pass standardized returns + timestamps + volume_params to volume generator)
- Test: `tests/test_volume.py`

- [ ] **Step 1: Write the failing test**

```python
import numpy as np
from marketforge.config.settings import GeneratorConfig, AssetConfig, MarketType, VolumeParams
from marketforge.generators.volume import VolumeGenerator
from marketforge.utils.random import RandomState


def _cfg():
    return GeneratorConfig(
        assets=[AssetConfig("A", start_price=100.0, volatility=0.4, volume_base=5000.0)],
        market_type=MarketType.CRYPTO,
        start_timestamp=1704067200, end_timestamp=1704067200 + 86400,
        volume_params=VolumeParams(phi=0.8, lam=0.4, noise_sigma=0.3),
    )


def test_volume_positive_and_level_near_base():
    cfg = _cfg()
    gen = VolumeGenerator(cfg)
    n = cfg.duration_minutes
    rng = RandomState(9)
    std_abs_ret = np.abs(rng.standard_normal((n, 1)))
    vols = gen.generate(rng, n, abs_returns=std_abs_ret)
    assert np.all(vols > 0)
    # mean level within a factor of ~2 of base
    assert 2500.0 < vols[:, 0].mean() < 10000.0


def test_volume_has_autocorrelation():
    cfg = _cfg()
    gen = VolumeGenerator(cfg)
    n = cfg.duration_minutes
    rng = RandomState(10)
    std_abs_ret = np.abs(rng.standard_normal((n, 1)))
    v = gen.generate(rng, n, abs_returns=std_abs_ret)[:, 0]
    lv = np.log(v)
    ac1 = np.corrcoef(lv[:-1], lv[1:])[0, 1]
    assert ac1 > 0.3  # clustering present


def test_volume_correlates_with_abs_returns():
    cfg = _cfg()
    gen = VolumeGenerator(cfg)
    n = cfg.duration_minutes
    rng = RandomState(12)
    z = rng.standard_normal((n, 1))
    abs_z = np.abs(z)
    v = gen.generate(rng, n, abs_returns=abs_z)[:, 0]
    assert np.corrcoef(abs_z[:, 0], v)[0, 1] > 0.1  # MDH: positive coupling
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_volume.py -v`
Expected: FAIL — current `generate` signature/behavior differs (no `volume_params`, weak autocorrelation may fail `> 0.3`).

- [ ] **Step 3: Rewrite the volume model**

In `marketforge/generators/volume.py`:

(a) Add import:

```python
from scipy.signal import lfilter
```

(b) In `VolumeGenerator.__init__`, capture volume params and seasonality:

```python
        from marketforge.core.seasonality import SeasonalityModel
        self._volume_params = getattr(config, "volume_params", None)
        self._seasonality = SeasonalityModel(config.market_type)
        self._seasonality_enabled = getattr(config, "seasonality_enabled", True)
```

(c) Replace `_generate_single_asset` and the three `_apply_*` helpers with a single coherent model. New `_generate_single_asset`:

```python
    def _generate_single_asset(
        self,
        rng: RandomState,
        n_steps: int,
        base_volume: float,
        volume_volatility: float,
        abs_returns: Optional[np.ndarray] = None,
        volatilities: Optional[np.ndarray] = None,
        timestamps: Optional[np.ndarray] = None,
    ) -> np.ndarray:
        """log V_t = μ + φ·(log V_{t-1}−μ) + λ·|z_t| + log s(t) + η_t."""
        params = self._volume_params
        phi = params.phi if params is not None else 0.7
        lam = params.lam if params is not None else 0.3
        noise_sigma = params.noise_sigma if params is not None else volume_volatility

        # Standardized absolute returns (MDH driver); 0 if not provided
        if abs_returns is not None:
            z = abs_returns / (abs_returns.mean() + 1e-12)
        else:
            z = np.zeros(n_steps)

        # Seasonal log-multiplier (variance-neutral, positive)
        if self._seasonality_enabled and timestamps is not None:
            log_s = np.log(self._seasonality.multiplier_series(timestamps))
        else:
            log_s = np.zeros(n_steps)

        eta = rng.normal(0.0, noise_sigma, n_steps)
        # Driver u_t for the AR(1): everything except the autoregressive memory.
        u = lam * z + log_s + eta
        # Stationary AR(1): y_t = phi*y_{t-1} + u_t  (zero-mean fluctuation of log-vol)
        y = lfilter([1.0], [1.0, -phi], u)

        log_v = np.log(base_volume) + y
        volumes = np.exp(log_v)
        # Re-center the level to base_volume (AR + |z| inject a positive mean shift)
        volumes *= base_volume / (volumes.mean() + 1e-12)
        return np.maximum(volumes, 1.0)
```

(d) Update the public `generate` to thread `timestamps` through (it already accepts it) — no signature change needed; ensure it passes `timestamps` into `_generate_single_asset` (it already does).

Delete `_apply_volume_clustering`, `_apply_return_correlation`, `_apply_volatility_scaling`, `_apply_time_patterns` (now subsumed).

- [ ] **Step 4: Pass timestamps + standardized returns from the OHLCV builder**

In `marketforge/generators/ohlcv.py`, in `OHLCVBuilder.build`, update the volume call to pass timestamps and use standardized abs returns:

```python
        volumes = self._volume_generator.generate(
            rng,
            n_steps,
            np.abs(return_result.returns),
            return_result.volatilities,
            timestamps=return_result.timestamps,
        )
```

- [ ] **Step 5: Run tests + full suite**

Run: `pytest tests/test_volume.py -v && pytest -q`
Expected: PASS, no regressions.

- [ ] **Step 6: Commit**

```bash
git add marketforge/generators/volume.py marketforge/generators/ohlcv.py tests/test_volume.py
git commit -m "feat(generators): log-AR(1) MDH volume model with seasonality"
```

---

## Task 11: Vectorize + recalibrate anomalies

**Files:**
- Modify: `marketforge/generators/anomalies.py` (`_inject_spikes`, `_inject_gaps` vectorized)
- Test: `tests/test_anomalies.py`

- [ ] **Step 1: Write the failing test**

```python
import numpy as np
from marketforge.config.settings import AnomalyConfig, AnomalyType, MarketType
from marketforge.generators.anomalies import AnomalyInjector
from marketforge.generators.ohlcv import OHLCVData
from marketforge.utils.random import RandomState


def _ohlcv(n=10000):
    rng = RandomState(1)
    close = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.001, n)))
    openp = np.concatenate([[close[0]], close[:-1]])
    high = np.maximum(openp, close) * 1.0005
    low = np.minimum(openp, close) * 0.9995
    vol = np.full(n, 1000.0)
    ts = np.arange(n, dtype=np.int64) * 60
    return OHLCVData("X", ts, openp, high, low, close, vol)


def test_invariants_hold_after_spike_injection():
    cfg = AnomalyConfig(types=frozenset({AnomalyType.SPIKES}), spike_probability=0.01)
    inj = AnomalyInjector(cfg, market_type=MarketType.CRYPTO)
    out, report = inj.inject(RandomState(2), _ohlcv())
    out.validate()  # raises if invariants broken
    assert report.n_events > 0


def test_spike_injection_is_reproducible():
    cfg = AnomalyConfig(types=frozenset({AnomalyType.SPIKES}), spike_probability=0.01)
    inj = AnomalyInjector(cfg, market_type=MarketType.CRYPTO)
    a, _ = inj.inject(RandomState(5), _ohlcv())
    b, _ = inj.inject(RandomState(5), _ohlcv())
    assert np.allclose(a.high, b.high) and np.allclose(a.low, b.low)
```

- [ ] **Step 2: Run test to verify it fails (or is slow)**

Run: `pytest tests/test_anomalies.py -v`
Expected: the reproducibility/invariant tests should pass against the current loop, but Step 3 replaces the per-candle Python loops with vectorized draws. If they already pass, treat this task as a refactor guarded by these tests (keep them green).

- [ ] **Step 3: Vectorize spike and gap selection**

In `marketforge/generators/anomalies.py`, replace the body of `_inject_spikes` loop with vectorized masks (same RNG semantics: one uniform draw per candle):

```python
        spike_prob = self._config.spike_probability
        min_mag, max_mag = self._config.spike_magnitude_range

        draws = rng.uniform(size=n)
        idxs = np.where(draws < spike_prob)[0]
        if idxs.size == 0:
            return events

        directions = rng.choice(np.array([-1, 1]), size=idxs.size)
        magnitudes = rng.uniform(min_mag, max_mag, size=idxs.size)
        mids = (open_prices[idxs] + close_prices[idxs]) / 2.0
        amounts = mids * magnitudes

        up = directions > 0
        high_prices[idxs[up]] += amounts[up]
        new_low = low_prices[idxs[~up]] - amounts[~up]
        floor = mids[~up] * 0.5
        low_prices[idxs[~up]] = np.maximum(new_low, floor)
        volumes[idxs] *= 2.0

        for k, i in enumerate(idxs):
            events.append(AnomalyEvent(
                type=AnomalyType.SPIKES, index=int(i),
                magnitude=float(magnitudes[k]), direction=int(directions[k]),
            ))
        return events
```

Apply the same vectorization pattern to `_inject_gaps` (draw `rng.uniform(size=n)` once, compute masked gap application). Keep `_inject_flash_crashes` as-is (already event-sparse).

> RNG-order note: vectorizing changes the exact random draw sequence vs the old loop, which is acceptable under the v2.0.0 break. The reproducibility test only requires *same seed → same output*, which holds.

- [ ] **Step 4: Run tests + full suite**

Run: `pytest tests/test_anomalies.py -v && pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add marketforge/generators/anomalies.py tests/test_anomalies.py
git commit -m "perf(generators): vectorize spike/gap anomaly injection"
```

---

## Task 12: Validation metrics — stylized facts

**Files:**
- Create: `marketforge/validation/__init__.py`
- Create: `marketforge/validation/stylized_facts.py`
- Test: `tests/test_stylized_facts_unit.py`

- [ ] **Step 1: Write the failing test**

```python
import numpy as np
from marketforge.validation.stylized_facts import (
    excess_kurtosis, volatility_clustering_strength, leverage_correlation,
    range_efficiency, ljung_box_pvalue,
)


def test_excess_kurtosis_detects_fat_tails():
    rng = np.random.default_rng(0)
    normal = rng.standard_normal(100_000)
    t = rng.standard_t(4, size=100_000)
    assert abs(excess_kurtosis(normal)) < 0.2
    assert excess_kurtosis(t) > 1.0


def test_volatility_clustering_strength_positive_for_garch_like():
    rng = np.random.default_rng(1)
    # synthesize clustered series: vol follows AR(1)
    n = 50_000
    vol = np.empty(n); vol[0] = 1.0
    for i in range(1, n):
        vol[i] = 0.99 * vol[i-1] + 0.01 * abs(rng.standard_normal())
    r = vol * rng.standard_normal(n)
    assert volatility_clustering_strength(r) > volatility_clustering_strength(rng.standard_normal(n))


def test_leverage_correlation_negative_when_downmoves_raise_vol():
    rng = np.random.default_rng(2)
    n = 50_000
    r = np.empty(n); sig = np.ones(n)
    for i in range(1, n):
        sig[i] = 0.9 * sig[i-1] + (0.2 if r[i-1] < 0 else 0.05) * abs(r[i-1])
        r[i] = sig[i] * rng.standard_normal()
    assert leverage_correlation(r) < 0


def test_range_efficiency_in_unit_band():
    rng = np.random.default_rng(3)
    n = 10_000
    o = np.full(n, 100.0); c = 100.0 * np.exp(rng.normal(0, 0.001, n))
    h = np.maximum(o, c) + np.abs(rng.normal(0, 0.05, n))
    l = np.minimum(o, c) - np.abs(rng.normal(0, 0.05, n))
    val = range_efficiency(o, h, l, c)
    assert val > 1.0  # (H-L) exceeds |C-O| on average
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_stylized_facts_unit.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement `marketforge/validation/stylized_facts.py`**

(Prepend AGPL header. `__init__.py` is empty.)

```python
"""
Stylized-fact metrics for validating synthetic market data against the
documented statistical properties of real financial returns.
"""

from __future__ import annotations

import numpy as np
from scipy.stats import kurtosis


def log_returns(close: np.ndarray) -> np.ndarray:
    """Close-to-close log returns."""
    close = np.asarray(close, dtype=float)
    return np.diff(np.log(close))


def excess_kurtosis(returns: np.ndarray) -> float:
    """Excess kurtosis (0 for a normal distribution; > 0 = fat tails)."""
    return float(kurtosis(np.asarray(returns, dtype=float), fisher=True, bias=False))


def _acf(x: np.ndarray, lag: int) -> float:
    x = np.asarray(x, dtype=float)
    x = x - x.mean()
    denom = np.sum(x * x)
    if denom == 0:
        return 0.0
    return float(np.sum(x[:-lag] * x[lag:]) / denom)


def volatility_clustering_strength(returns: np.ndarray, max_lag: int = 20) -> float:
    """Mean autocorrelation of |returns| over the first ``max_lag`` lags.

    Positive and slowly decaying for real markets; ~0 for i.i.d. noise.
    """
    a = np.abs(np.asarray(returns, dtype=float))
    return float(np.mean([_acf(a, k) for k in range(1, max_lag + 1)]))


def leverage_correlation(returns: np.ndarray) -> float:
    """corr(r_t, |r_{t+1}|): negative indicates the leverage effect."""
    r = np.asarray(returns, dtype=float)
    if r.size < 3:
        return 0.0
    return float(np.corrcoef(r[:-1], np.abs(r[1:]))[0, 1])


def range_efficiency(open_, high, low, close) -> float:
    """Mean of (High-Low) / |Close-Open|, a measure of intrabar range richness."""
    o = np.asarray(open_, float); h = np.asarray(high, float)
    l = np.asarray(low, float); c = np.asarray(close, float)
    body = np.abs(c - o)
    rng_ = h - l
    mask = body > 1e-12
    if not np.any(mask):
        return float("inf")
    return float(np.mean(rng_[mask] / body[mask]))


def ljung_box_pvalue(x: np.ndarray, lags: int = 20) -> float:
    """Ljung-Box p-value (small => significant autocorrelation present)."""
    from statsmodels.stats.diagnostic import acorr_ljungbox
    res = acorr_ljungbox(np.asarray(x, dtype=float), lags=[lags], return_df=True)
    return float(res["lb_pvalue"].iloc[-1])


def arch_lm_pvalue(returns: np.ndarray, lags: int = 12) -> float:
    """ARCH-LM test p-value (small => volatility clustering / ARCH effects)."""
    from statsmodels.stats.diagnostic import het_arch
    r = np.asarray(returns, dtype=float)
    r = r - r.mean()
    return float(het_arch(r, nlags=lags)[1])
```

- [ ] **Step 4: Run tests + full suite**

Run: `pytest tests/test_stylized_facts_unit.py -v && pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add marketforge/validation/__init__.py marketforge/validation/stylized_facts.py tests/test_stylized_facts_unit.py
git commit -m "feat(validation): stylized-fact metric functions"
```

---

## Task 13: Validation report + target bands

**Files:**
- Create: `marketforge/validation/report.py`
- Test: `tests/test_validation_report.py`

- [ ] **Step 1: Write the failing test**

```python
import numpy as np
from marketforge.config.settings import MarketType
from marketforge.validation.report import validate_returns, ValidationReport


def test_report_flags_gaussian_as_too_thin_for_crypto():
    rng = np.random.default_rng(0)
    gaussian = rng.standard_normal(100_000) * 0.001
    report = validate_returns(gaussian, MarketType.CRYPTO)
    assert isinstance(report, ValidationReport)
    # crypto expects fat tails; pure gaussian should FAIL the kurtosis check
    k = report.get("excess_kurtosis")
    assert k is not None and not k.passed


def test_report_overall_pass_property_aggregates():
    rng = np.random.default_rng(1)
    r = rng.standard_t(3.5, size=200_000) * 0.001
    report = validate_returns(r, MarketType.CRYPTO)
    assert isinstance(report.passed, bool)
    assert "excess_kurtosis" in report.metrics
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_validation_report.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement `marketforge/validation/report.py`**

(Prepend AGPL header.)

```python
"""
Validation report: run stylized-fact metrics against per-market target bands.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
import numpy as np

from marketforge.config.settings import MarketType
from marketforge.validation import stylized_facts as sf


@dataclass
class MetricResult:
    name: str
    value: float
    low: Optional[float]
    high: Optional[float]
    passed: bool


@dataclass
class ValidationReport:
    market_type: MarketType
    metrics: dict[str, MetricResult] = field(default_factory=dict)

    def get(self, name: str) -> Optional[MetricResult]:
        return self.metrics.get(name)

    @property
    def passed(self) -> bool:
        return all(m.passed for m in self.metrics.values())

    def summary(self) -> str:
        lines = [f"Validation report ({self.market_type.value}): "
                 f"{'PASS' if self.passed else 'FAIL'}"]
        for m in self.metrics.values():
            band = f"[{m.low}, {m.high}]"
            flag = "ok " if m.passed else "FAIL"
            lines.append(f"  {flag} {m.name}={m.value:.4f} target {band}")
        return "\n".join(lines)


# Per-market target bands for m1 log-returns.
# (low, high); None = unbounded on that side.
_KURTOSIS_BANDS = {
    MarketType.CRYPTO: (2.0, 60.0),
    MarketType.STOCKS: (1.5, 40.0),
    MarketType.FOREX: (1.0, 30.0),
}


def _check(name, value, low, high) -> MetricResult:
    ok = True
    if low is not None and value < low:
        ok = False
    if high is not None and value > high:
        ok = False
    return MetricResult(name=name, value=value, low=low, high=high, passed=ok)


def validate_returns(returns: np.ndarray, market_type: MarketType) -> ValidationReport:
    """Validate a 1-D return series against the market's target bands."""
    report = ValidationReport(market_type=market_type)
    r = np.asarray(returns, dtype=float)

    k_low, k_high = _KURTOSIS_BANDS[market_type]
    report.metrics["excess_kurtosis"] = _check(
        "excess_kurtosis", sf.excess_kurtosis(r), k_low, k_high)

    # Volatility clustering must be present and positive.
    report.metrics["vol_clustering"] = _check(
        "vol_clustering", sf.volatility_clustering_strength(r), 0.02, None)

    # Leverage effect: correlation of r_t with |r_{t+1}| should be <= 0.
    report.metrics["leverage"] = _check(
        "leverage", sf.leverage_correlation(r), None, 0.02)

    return report


def validate_ohlcv(open_, high, low, close, market_type: MarketType) -> ValidationReport:
    """Validate an OHLC series: return-based facts plus range efficiency."""
    report = validate_returns(sf.log_returns(close), market_type)
    report.metrics["range_efficiency"] = _check(
        "range_efficiency", sf.range_efficiency(open_, high, low, close), 1.0, 6.0)
    return report
```

- [ ] **Step 4: Run tests + full suite**

Run: `pytest tests/test_validation_report.py -v && pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add marketforge/validation/report.py tests/test_validation_report.py
git commit -m "feat(validation): report with per-market stylized-fact bands"
```

---

## Task 14: `marketforge validate` CLI subcommand

**Files:**
- Modify: `marketforge/cli/parser.py`, `marketforge/cli/runner.py` (or wherever the click group lives)
- Test: `tests/test_cli_validate.py`

> First read `marketforge/cli/parser.py` and `marketforge/cli/runner.py` to find the existing click group/command structure, then attach a sibling `validate` command. The code below assumes a `click.Group` named `cli`; adapt names to the actual file.

- [ ] **Step 1: Write the failing test**

```python
import numpy as np
import pandas as pd
from click.testing import CliRunner

from marketforge.cli.parser import cli  # adapt import to actual group location


def test_validate_command_on_a_csv(tmp_path):
    # Write a fat-tailed synthetic CSV
    rng = np.random.default_rng(0)
    n = 50_000
    r = rng.standard_t(3.5, size=n) * 0.001
    close = 100.0 * np.exp(np.cumsum(r))
    openp = np.concatenate([[close[0]], close[:-1]])
    high = np.maximum(openp, close) * 1.0008
    low = np.minimum(openp, close) * 0.9992
    df = pd.DataFrame({
        "timestamp": np.arange(n) * 60, "open": openp, "high": high,
        "low": low, "close": close, "volume": np.full(n, 1000.0),
    })
    p = tmp_path / "BTCUSD_m1.csv"
    df.to_csv(p, index=False)

    res = CliRunner().invoke(cli, ["validate", "--input", str(p), "--market", "crypto"])
    assert res.exit_code in (0, 1)  # 0 pass / 1 soft-fail, but must run cleanly
    assert "Validation report" in res.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli_validate.py -v`
Expected: FAIL — no `validate` command.

- [ ] **Step 3: Add the `validate` command**

Attach to the existing click group (adapt to actual structure):

```python
import click
import pandas as pd

from marketforge.configs.base import MarketType
from marketforge.validation.report import validate_ohlcv


@cli.command(name="validate")
@click.option("--input", "input_path", required=True, type=click.Path(exists=True),
              help="CSV file (with open/high/low/close columns) to validate.")
@click.option("--market", "market", required=True,
              type=click.Choice([m.value for m in MarketType]),
              help="Market type whose target bands to apply.")
def validate_cmd(input_path: str, market: str) -> None:
    """Validate generated OHLCV data against real-market stylized facts."""
    df = pd.read_csv(input_path)
    report = validate_ohlcv(
        df["open"].to_numpy(), df["high"].to_numpy(),
        df["low"].to_numpy(), df["close"].to_numpy(),
        MarketType(market),
    )
    click.echo(report.summary())
    raise SystemExit(0 if report.passed else 1)
```

- [ ] **Step 4: Run tests + full suite**

Run: `pytest tests/test_cli_validate.py -v && pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add marketforge/cli/ tests/test_cli_validate.py
git commit -m "feat(cli): add 'validate' subcommand for stylized-fact checks"
```

---

## Task 15: End-to-end stylized-facts integration + OHLC invariants

**Files:**
- Create: `tests/test_stylized_facts_integration.py`
- Create: `tests/test_invariants.py`

- [ ] **Step 1: Write the integration test (the realism proof)**

```python
import numpy as np
import pytest

from marketforge.configs.loader import load_market_config, market_config_to_generator_config
from marketforge.generators.ohlcv import OHLCVBuilder
from marketforge.utils.random import RandomState
from marketforge.validation.report import validate_ohlcv
from marketforge.config.settings import MarketType

# 10 days of m1 for a few assets per market => enough samples for the metrics.
_TEN_DAYS = 10 * 86400


@pytest.mark.parametrize("market", ["crypto", "stocks", "forex"])
def test_generated_data_matches_stylized_facts(market):
    mc = load_market_config(market)
    syms = mc.symbols[:3]
    cfg = market_config_to_generator_config(
        mc, start_timestamp=1704067200, end_timestamp=1704067200 + _TEN_DAYS,
        seed=123, batch_symbols=syms,
    )
    builder = OHLCVBuilder(cfg)
    data = builder.build(RandomState(123))

    d = data[syms[0]]
    report = validate_ohlcv(d.open, d.high, d.low, d.close, MarketType(market))
    assert report.get("excess_kurtosis").passed, report.summary()
    assert report.get("vol_clustering").passed, report.summary()
    assert report.get("leverage").passed, report.summary()
    assert report.get("range_efficiency").passed, report.summary()
```

- [ ] **Step 2: Write the invariants test**

```python
import numpy as np
import pytest

from marketforge.configs.loader import load_market_config, market_config_to_generator_config
from marketforge.generators.ohlcv import OHLCVBuilder
from marketforge.generators.anomalies import AnomalyInjector
from marketforge.config.settings import AnomalyConfig, AnomalyType
from marketforge.utils.random import RandomState


@pytest.mark.parametrize("market", ["crypto", "stocks", "forex"])
def test_ohlc_invariants_with_anomalies(market):
    mc = load_market_config(market)
    syms = mc.symbols[:2]
    cfg = market_config_to_generator_config(
        mc, 1704067200, 1704067200 + 3 * 86400, seed=7, batch_symbols=syms,
    )
    data = OHLCVBuilder(cfg).build(RandomState(7))
    inj = AnomalyInjector(
        AnomalyConfig(types=frozenset({AnomalyType.SPIKES, AnomalyType.GAPS})),
        market_type=cfg.market_type,
    )
    for sym in syms:
        out, _ = inj.inject(RandomState(7), data[sym])
        out.validate()  # raises on any invariant violation
        assert np.all(out.volume >= 0)
        assert np.all(out.low > 0)
```

- [ ] **Step 3: Run the integration tests**

Run: `pytest tests/test_stylized_facts_integration.py tests/test_invariants.py -v`
Expected: PASS. **If a band fails**, tune the responsible default in `marketforge/config/defaults.py` (e.g. raise `gamma` if leverage is too weak, lower `innovation_nu` if kurtosis is below band, adjust `volume_params`) and re-run. Do **not** widen a band to force a pass unless the band itself is demonstrably unrealistic; record the rationale in the commit message.

- [ ] **Step 4: Run the entire suite**

Run: `pytest -q`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add tests/test_stylized_facts_integration.py tests/test_invariants.py
git commit -m "test: end-to-end stylized-facts and OHLC invariant suite"
```

---

## Task 16: Before/after benchmark + README/docs update

**Files:**
- Create: `scripts/benchmark_realism.py`
- Modify: `README.md`

- [ ] **Step 1: Write the benchmark script**

`scripts/benchmark_realism.py` (prepend AGPL header):

```python
"""
Print stylized-fact metrics for generated data, per market — the v2 realism proof.

Usage: python scripts/benchmark_realism.py
"""
from __future__ import annotations

from marketforge.configs.loader import load_market_config, market_config_to_generator_config
from marketforge.generators.ohlcv import OHLCVBuilder
from marketforge.utils.random import RandomState
from marketforge.validation.report import validate_ohlcv
from marketforge.config.settings import MarketType

TEN_DAYS = 10 * 86400


def main() -> None:
    for market in ("crypto", "stocks", "forex"):
        mc = load_market_config(market)
        syms = mc.symbols[:1]
        cfg = market_config_to_generator_config(
            mc, 1704067200, 1704067200 + TEN_DAYS, seed=2024, batch_symbols=syms,
        )
        data = OHLCVBuilder(cfg).build(RandomState(2024))
        d = data[syms[0]]
        report = validate_ohlcv(d.open, d.high, d.low, d.close, MarketType(market))
        print(report.summary())
        print()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the benchmark**

Run: `python scripts/benchmark_realism.py`
Expected: three PASS reports printed (crypto/stocks/forex) with fat-tailed kurtosis, positive clustering, non-positive leverage, realistic range efficiency.

- [ ] **Step 3: Update `README.md`**

- Bump the version footer to **2.0.0**.
- Replace the "Realistic Price Dynamics" bullets to reflect: multivariate Student-t innovations (fat tails + tail dependence), GJR-GARCH leverage effect, intraday/weekly volatility seasonality, Brownian-bridge intrabar OHLC, log-AR(1) MDH volume.
- Add a **Validation** section documenting `marketforge validate --input <csv> --market <m>` and the stylized facts checked.
- Add a short **"Statistical realism (v2.0.0)"** subsection summarizing the stylized facts the generator now reproduces and how to verify them.

- [ ] **Step 4: Commit**

```bash
git add scripts/benchmark_realism.py README.md
git commit -m "docs: v2.0.0 realism model, validation usage, benchmark script"
```

---

## Final verification

- [ ] **Run the whole suite + type check**

Run: `pytest -q && mypy marketforge`
Expected: all tests pass; mypy clean (or no new errors vs baseline).

- [ ] **Run the benchmark one more time and eyeball the numbers**

Run: `python scripts/benchmark_realism.py`
Confirm: excess kurtosis in realistic fat-tailed range per market, leverage correlation ≤ 0, volatility clustering > 0, range efficiency in band.

---

## Spec coverage check

- Fat tails + tail dependence → Tasks 2, 3, 8 ✅
- GJR-GARCH leverage → Task 4 ✅
- Intraday/weekly seasonality → Tasks 5, 8 ✅
- Brownian-bridge intrabar OHLC → Task 9 ✅
- Coherent log-AR volume (MDH) → Task 10 ✅
- Anomaly recalibration/vectorization → Task 11 ✅
- Config unification (model params single-sourced, drop misleading base_volatility) → Tasks 6, 7 ✅
- Validation harness (metrics, report, CLI, tests) → Tasks 12–15 ✅
- v2.0.0 bump, deps, README → Tasks 1, 16 ✅
- 24/7 emission retained, no trading calendar → honored (no calendar task) ✅
