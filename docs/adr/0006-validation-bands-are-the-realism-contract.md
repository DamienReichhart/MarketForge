# The validation harness defines "realistic", and output changes need a major version

> Amended by [ADR 0011](0011-realism-over-seed-stability.md): output changes no longer need a major version. They need a `MODEL_REVISION` increment and an *Output changes* changelog entry.

"Statistically realistic" is defined operationally: generated m1 data must pass the stylized-fact bands in `marketforge/validation/report.py` (heavy tails, volatility clustering, leverage effect, range efficiency), checked for every instrument across seeds by `scripts/benchmark_realism.py`. Any change to the model or calibration is judged against that harness, not against intuition, and the bands themselves are anchored to statistics measured on real market data (see `marketforge/validation/reference.py`). Because users rely on seeds for reproducible backtests, any change that alters the candles produced by an existing seed ships only in a new major version, with no legacy mode kept alongside.

## Consequences

- The heavy validation libraries (`arch`, `statsmodels`) stay in the `dev` extra, out of the generation path.
- Loosening a band is a deliberate, recorded decision tied to real-data evidence, never a way to make a failing calibration pass.
