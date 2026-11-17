# Realism comes before seed stability: output is reproducible per exact version

ADR 0006 froze every seed's candles within a major version, and ADR 0007 spent a release optimising under that rule. The cost was a model we could not improve: wrong correlations, regimes without a trend, candles without wicks were all kept for the sake of seeds that nobody could have relied on beyond a pinned version anyway. Users who need identical candles pin the version; users who need realistic ones should not wait for a major release.

**Decision.** The same seed, the same exact MarketForge version and the same platform give the same candles, bit for bit. Any release, minor or patch included, may change what a seed produces when the change makes the data more realistic. Such a change is listed in the changelog under **Output changes**, and it increments `MODEL_REVISION`, an integer that names the model's output generation. Major versions are reserved for breaks of the public API (renamed options, removed functions).

- **The manifest records the revision** next to the version. `extend` continues a dataset only when its `model_revision` equals the running one, since a checkpoint from another model cannot be continued exactly. Any other combination is refused with a message that names both revisions.
- **The CI gate changes.** CI still fingerprints 786 outputs with the code under test and with the latest release, in the same environment. A difference is now allowed only when `MODEL_REVISION` was incremented and the changelog has an *Output changes* section for the version. A difference without both fails, and so does an increment without a difference.
- **What stays exact.** Within one version and platform, output is still independent of the instrument selection, timeframes, format, `--jobs`, the spread and regime columns, how far `--to` extends and whether a range was extended in steps. ADR 0007's rules for exact kernels still apply: they are what makes those independences hold.
- **Validation still decides.** Changes are judged against the validation bands (ADR 0006's first half is unchanged), and a change that cannot be validated against real data is labelled as such in the changelog.

## Consequences

- ADR 0006's rule that output changes need a major version, ADR 0007's "ships as a minor version" argument, ADR 0001's note on draw order and ADR 0009's "within a major version" are superseded by this one.
- Anyone who needs identical candles across time pins the version (and the dataset's manifest says which one).
