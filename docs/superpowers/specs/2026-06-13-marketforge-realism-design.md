# MarketForge v2.0.0 — Statistical Realism Upgrade

**Date:** 2026-06-13
**Status:** Design — pending review
**Goal:** Make MarketForge's generated OHLCV data statistically indistinguishable from real markets, and prove it with a measurement harness.

## 1. Motivation

MarketForge generates synthetic OHLCV data via GBM + GARCH(1,1) + regime switching.
The current output misses several well-documented "stylized facts" of real financial
returns, which limits its usefulness for backtesting and research:

| Stylized fact | Current | Problem |
|---|---|---|
| Heavy tails (excess kurtosis) | Gaussian innovations | Tails far too thin at m1 |
| Volatility clustering | GARCH(1,1) | OK — keep |
| Leverage effect (asymmetric vol) | symmetric GARCH | Absent |
| Intraday volatility seasonality | only volume | Returns have flat intraday vol |
| Intrabar High/Low realism | `volatility × mid × 10` exponential wicks | Arbitrary; not a real price path |
| Volume clustering / MDH coupling | 3 stacked ad-hoc multipliers | Weak, no proper ACF |
| Tail co-movement | independent Gaussian → Cholesky | Assets never crash together |

Structural debt that the realism work touches:
- **Two parallel config systems**: `marketforge/config/` (`GeneratorConfig`, `defaults.py`
  with an unrealistic `base_volatility=0.008`) and `marketforge/configs/` (real per-asset
  `AssetParams` with realistic vols). They must be unified.
- **Per-candle Python loops** in High/Low, gaps, and GARCH limit throughput.

## 2. Scope decisions (locked with stakeholder)

- **Primary objective:** statistical realism (not speed, not new formats).
- **Validation harness:** YES — build a diagnostics module + pytest suite with target bands.
- **Dependencies:** specialized libs allowed (`arch`, `statsmodels`) for validation;
  core simulation stays vectorized numpy/scipy for speed.
- **Trading calendar:** NOT included. Keep 24/7 candle emission for all markets; apply
  intraday volatility seasonality to returns + keep existing session-gap injection.
- **Backward compatibility:** none required. This is a major version bump to **v2.0.0**;
  seeds will produce different (better) data than v1.0.0. No legacy mode.

## 3. Design — the statistical core

All models below are vectorized across `(n_steps, n_assets)` unless inherently recursive.

### 3.1 Fat tails + tail dependence — Multivariate Student-t innovations

Replace Gaussian innovations in `CorrelationEngine.generate_correlated_normals` with a
**multivariate Student-t** built as a normal-variance mixture:

```
Z ~ N(0, I)                      # (n_steps, n_assets) independent normals
Y = Z @ Lᵀ                       # correlated normals (existing Cholesky L)
W ~ ChiSquared(ν) / ν            # (n_steps, 1) shared mixing variable per time step
T = Y / sqrt(W)                  # multivariate-t, then rescaled to unit variance
T_std = T * sqrt((ν - 2) / ν)    # standardized so Var = 1 (requires ν > 2)
```

- A **shared** `W` per time step gives joint tail dependence: when the mixing variable is
  large, *all* assets get an extreme draw together → realistic simultaneous crashes.
- `ν` (degrees of freedom) configurable per market: crypto ≈ 3.5, stocks ≈ 4.5, forex ≈ 6.
- New module: `marketforge/core/innovations.py` with an `InnovationGenerator` abstraction
  (`GaussianInnovations`, `StudentTInnovations`) so the model is pluggable and testable.
- `CorrelationEngine` keeps Cholesky; it gains an injected innovation generator.

### 3.2 Asymmetric volatility — GJR-GARCH(1,1,1)

Replace symmetric GARCH update in `GARCHModel.step` /
`generate_volatility_series` with the Glosten-Jagannathan-Runkle form:

```
σ²_t = ω + (α + γ·1[ε_{t-1} < 0])·ε²_{t-1} + β·σ²_{t-1}
```

- `γ > 0` makes negative shocks raise volatility more → leverage effect.
- Stationarity / unconditional-variance constraint becomes `α + β + γ/2 < 1`;
  `_scaled_omega` and `_initial_variance` recomputed accordingly so the long-run vol
  still matches the asset's configured `volatility`.
- `GARCHParams` gains `gamma: float = 0.0` (frozen dataclass; validated in `__post_init__`).
  `gamma=0` recovers classic GARCH, so existing call sites stay valid.
- Default `gamma` per market set in unified defaults (crypto/stocks higher, forex lower).
- The recursive loop stays (GARCH is inherently sequential) but is tightened; optionally
  Numba-jitted if available, with a pure-numpy fallback (decided at implementation —
  not required for correctness).

### 3.3 Intraday & weekly volatility seasonality

New module: `marketforge/core/seasonality.py` producing a deterministic, strictly-positive
multiplicative factor `s(t) ≥ 0` applied to per-minute volatility (and reused by volume):

- **Stocks:** U-shape across the US cash session (~14:30–21:00 UTC; high at open & close,
  midday lull), reduced amplitude overnight. Implemented as a smooth function of
  minute-of-day, not hard buckets. (Session-hour constants centralized so they can be
  tuned without touching logic.)
- **Forex:** session-overlap profile (Asian < London < London/NY overlap peak).
- **Crypto:** mild — slightly lower on weekends / Asian early hours; near-flat otherwise.

The factor is **variance-neutralized** over a full day (mean ≈ 1 across a 24h cycle) so it
reshapes *when* volatility occurs without inflating overall daily volatility away from the
asset's configured level. Applied in `ReturnGenerator.generate` after GARCH, before returns.

### 3.4 Brownian-bridge intrabar OHLC

Replace `OHLCVBuilder._generate_high_low` (the `× 10` exponential-wick heuristic) with a
**vectorized Brownian-bridge** intrabar simulation:

For each bar, the intrabar log-price path is a Brownian bridge from `log(open)` to
`log(close)` with the bar's own volatility `σ_bar` (the per-minute conditional vol):

```
For k sub-steps (default k = 8):
  build a standard Brownian bridge B on a (n, k) grid pinned at 0 → 0
  scale by σ_bar (per-bar) to get intrabar log deviations d
  logpath = linspace(log O, log C, k) + d
  high = exp(max over k of logpath);  low = exp(min over k of logpath)
```

- Guarantees `high ≥ max(O,C)` and `low ≤ min(O,C)` by construction.
- Range scales correctly with volatility (no magic constant); the high/low–to–|O−C| ratio
  lands in the empirically realistic band automatically.
- t-distributed sub-step innovations give occasional long natural wicks (replacing some of
  the need for synthetic "spike" anomalies).
- Fully vectorized across all bars × assets → also removes the dominant Python-loop hotspot.
- Replaces `_generate_high_low`, `_get_gap_probabilities` retained (still 24/7) but
  vectorized; `_generate_gaps` already mostly vectorized.

### 3.5 Coherent volume model

Replace the three stacked heuristics (`_apply_volume_clustering`,
`_apply_return_correlation`, `_apply_volatility_scaling`) with a single log-AR(1) model in
`VolumeGenerator`:

```
log V_t = μ_v + φ·(log V_{t-1} − μ_v) + λ·|z_t| + log s(t) + η_t,   η_t ~ N(0, σ_η²)
V_t = exp(log V_t)
```

- `z_t` = standardized return at t → Mixture-of-Distributions-Hypothesis coupling
  (volume rises with |return|).
- `φ` gives genuine volume autocorrelation (clustering) with a correct ACF.
- `s(t)` is the same seasonality factor from §3.3 (shared, consistent).
- `μ_v` derived from the asset's `volume_base`; `φ, λ, σ_η` market-tunable defaults.
- Recursive in `t` (cheap), vectorized across assets.

### 3.6 Anomalies — keep, lightly recalibrate

Anomaly injection (gaps, spikes, flash crashes) is retained. Because §3.1 (fat tails) and
§3.4 (bridge wicks) now produce natural extremes, default spike intensity is reduced so
anomalies model *structural* events (flash crashes, news gaps) rather than compensating for
missing tail risk. Flash-crash and gap logic unchanged in shape; the per-candle loops in
`_inject_gaps`/`_inject_spikes` are vectorized.

## 4. Design — configuration unification

Collapse the two config packages into one coherent source of truth:

- Keep `marketforge/configs/` (the real per-asset `AssetParams` + correlation matrices) as
  the **authoritative market data**.
- Fold the *model-parameter* defaults (GARCH/GJR, regime, seasonality, innovation ν,
  volume AR params, anomaly config) into per-market default objects that live alongside it,
  replacing the disconnected `marketforge/config/defaults.py` values.
- `GeneratorConfig`/`AssetConfig`/`GARCHParams`/`RegimeParams`/`AnomalyConfig` dataclasses
  remain the runtime contract but are extended (new fields: `gamma`, `nu`, seasonality
  params, volume AR params) and are populated *only* from the authoritative configs.
- Delete the stale `base_volatility=0.008`-style market defaults; per-asset realistic vols
  already exist in `configs/`.
- Net: one place defines a market, no contradictory volatility numbers.

## 5. Design — validation harness (the proof)

New package `marketforge/validation/` + `tests/`:

### 5.1 Metrics (`marketforge/validation/stylized_facts.py`)

Given a generated OHLCV series (and/or returns), compute:

1. **Excess kurtosis** of m1 log-returns (per market target band, e.g. crypto 5–40).
2. **No linear autocorrelation in returns** — Ljung-Box on `r_t` (p large) via statsmodels.
3. **Volatility clustering** — Ljung-Box on `r_t²`/`|r_t|` (strong, significant) +
   **ARCH-LM** test (`statsmodels.stats.diagnostic.het_arch`).
4. **Slow decay** of `|r_t|` autocorrelation (ACF positive and decaying over many lags).
5. **Leverage effect** — `corr(r_t, σ_{t+1}) < 0` (and sign of `corr(r_t, |r_{t+1}|)`).
6. **Range efficiency** — distribution of `(High−Low)` vs `|Close−Open|`, and
   Garman-Klass vs close-to-close volatility consistency ratio in a realistic band.
7. **Intraday seasonality** — recovered U-shape / session profile matches the configured one.
8. **Aggregational Gaussianity** — excess kurtosis decreases monotonically m1 → H1 → D1.
9. **OHLC validity** — `high ≥ max(O,C)`, `low ≤ min(O,C)`, `high ≥ low`, `volume ≥ 0`
   (hard invariants, must be exact).

Optionally fit a GJR-GARCH with `arch` to the generated returns and check the recovered
parameters are near the configured ones (round-trip sanity).

### 5.2 Report (`marketforge/validation/report.py`)

A `validate(ohlcv | returns, market_type) -> ValidationReport` API returning each metric,
its target band, and pass/fail. Human-readable summary printer.

### 5.3 CLI

`marketforge validate --input <dir|csv> [--market crypto]` runs the harness on generated
data and prints the report (exit non-zero if hard invariants fail).

### 5.4 Tests (`tests/`)

The repo currently has **no tests**. Add:
- `tests/test_stylized_facts.py` — generate a fixed-seed sample per market, assert each
  metric falls in its target band. This is both the realism proof and a regression guard.
- `tests/test_invariants.py` — OHLC hard invariants across markets/timeframes/anomalies.
- `tests/test_models.py` — unit tests for GJR-GARCH stationarity/long-run variance,
  t-innovation variance ≈ 1 and kurtosis, seasonality day-mean ≈ 1, bridge high/low bounds.
- Wire `pytest` into `pyproject.toml` `[dev]` extras.

## 6. What is explicitly NOT changing

- Batch processing / threading (`processing/batch.py`) — keep.
- CSV writer and output format — keep (still `timestamp,open,high,low,close,volume`).
- Timeframe aggregation (`aggregation/timeframes.py`) — keep.
- CLI parser structure (`cli/`) — keep, extend with `validate` subcommand and new flags
  (`--nu`, `--leverage`/`gamma` overrides are optional; defaults come from configs).
- Markets, asset lists, correlation matrices — keep (authoritative data).

## 7. Module change map

| Module | Change |
|---|---|
| `core/innovations.py` | **new** — Gaussian / Student-t pluggable innovations |
| `core/correlation.py` | inject innovation generator; keep Cholesky |
| `core/garch.py` | GJR-GARCH; recompute omega/uncond. variance with `γ` |
| `core/seasonality.py` | **new** — intraday/weekly vol multiplier |
| `core/returns.py` | apply seasonality; use t-innovations; vectorize |
| `generators/ohlcv.py` | **rewrite** High/Low via Brownian bridge; vectorize |
| `generators/volume.py` | **rewrite** as log-AR(1) MDH model |
| `generators/anomalies.py` | recalibrate intensity; vectorize loops |
| `config/settings.py` | extend dataclasses (`gamma`, `nu`, seasonality, volume AR) |
| `config/defaults.py` | **delete/replace** — fold into unified per-market defaults |
| `configs/*` | authoritative source; add model-param defaults per market |
| `validation/` | **new** package — metrics, report, CLI |
| `tests/` | **new** — stylized-facts, invariants, model unit tests |
| `requirements.txt` / `pyproject.toml` | add `arch`, `statsmodels`; bump to 2.0.0 |
| `README.md` | document realism model, validation, v2.0.0 |

## 8. Success criteria

1. `tests/test_stylized_facts.py` passes: every metric in §5.1 within its market target band.
2. OHLC hard invariants hold for all markets × timeframes × anomaly settings.
3. A before/after report shows: excess kurtosis ↑ into realistic range, leverage
   correlation now negative, intraday vol U-shape present, High/Low–to–body ratio realistic,
   volume autocorrelation present — relative to v1.0.0.
4. No regression in generation throughput attributable to the new models (vectorization
   should net-improve it despite richer dynamics).
5. Single source of truth for market configuration (no contradictory volatility numbers).

## 9. Risks & mitigations

- **Seasonality double-counting volatility** → variance-neutralize `s(t)` over a day (mean 1).
- **GJR omega mis-scaling** breaking long-run vol → unit test long-run variance vs target.
- **t-innovation infinite variance** for ν ≤ 2 → validate `ν > 2`; standardize by
  `sqrt((ν−2)/ν)`.
- **Brownian-bridge cost** (k× memory) → modest `k=8`, chunked across batches; still net
  faster than the per-candle Python loop it replaces.
- **arch/statsmodels install weight** → confined to validation extra + dev/test, not the
  hot generation path.
