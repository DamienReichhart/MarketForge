# MarketForge

Synthetic OHLCV market-data generator (Python). See `README.md` for features, architecture and usage.

## Agent skills

### Issue tracker

Issues live in GitHub Issues on `DamienReichhart/MarketForge` (`gh` locally; GitHub MCP tools in cloud sessions). See `docs/agents/issue-tracker.md`.

### Triage labels

Default five-role vocabulary: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `GLOSSARY.md` and `docs/adr/` at the repo root, created lazily. See `docs/agents/domain.md`.

## Brand

The identity is **Regimes**; the guidelines, tokens and every logo are in `docs/brand/` (`README.md`). Colours come from `docs/brand/tokens.json`, mirrored in `website/src/styles/theme.css` (a test fails if they drift); never hard-code a colour or recolour the mark. Regime colours mean a market regime and nothing else, and the up/down green and red mean candle direction and nothing else. Rebuild the assets with `python scripts/build_brand_assets.py` after changing the tokens. The site's Brand page is generated from `docs/brand/README.md`; edit that file.

## CI/CD

CI runs `ruff check`, `ruff format --check`, `lint-imports` (package layering, see the README's project layout), `mypy marketforge` and `pytest` (install the tools with `pip install -e . --group dev`); run them before pushing. CI also fails if any seed's output differs from the latest release unless `MODEL_REVISION` (`marketforge/_version.py`) is incremented and `CHANGELOG.md` lists the change under `### Output changes` (realism comes before seed stability, ADR 0011), and a release is blocked if a commit marked breaking (`type!:` or `BREAKING CHANGE:`) ships without a major bump. A push to `main` releases the version in `pyproject.toml` when it is not yet tagged, and PRs into `main` must bump it and add a `CHANGELOG.md` section, so merge to `main` only to release. CI also fails when the code is more than 15% slower than the latest release (an intended slowdown takes an `Accept-Slowdown: N%` commit trailer), and when a code block of `README.md` or of the website's pages no longer works: they are run against the built wheel (`python -I .github/scripts/doc_examples.py`), and a block too long to run is marked `check=static` after its language. See `docs/ci-cd.md`.

Third-party licence and NOTICE texts are generated, never committed: the release's by `.github/scripts/licenses.py` (CI's build job), the website's `/third-party-licenses.txt` by `website/scripts/third-party-licenses.mjs` on every build. Both fail on a licence their policy (`.github/python-license-policy.toml`, `website/license-policy.json`) does not allow or a package without licence text; resolve a failure by reading the package's licence and recording the decision and its reason there, never by widening the global allowlist for one package. Upstream texts a served package lacks are saved in `website/licenses/` for one version; after a version bump, `cd website && npm run vendor-licenses` refetches them, then review the diff. See `docs/ci-cd.md#third-party-licences`.

The website (`website/`, Astro + Starlight) is type-checked, built and link-checked in CI (`cd website && npm ci && npm run check && npm run build && npm run check-links`); links to other sites are checked weekly (`npm run check-external-links`) and deployed to GitHub Pages from `main` by CD. Its changelog, glossary and ADR pages are generated from `CHANGELOG.md`, `GLOSSARY.md` and `docs/adr/`; edit those, never the generated copies.
