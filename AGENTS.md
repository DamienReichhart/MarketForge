# MarketForge

Synthetic OHLCV market-data generator (Python). See `README.md` for features, architecture and usage.

## Agent skills

### Issue tracker

Issues live in GitHub Issues on `DamienReichhart/MarketForge` (`gh` locally; GitHub MCP tools in cloud sessions). See `docs/agents/issue-tracker.md`.

### Triage labels

Default five-role vocabulary: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `GLOSSARY.md` and `docs/adr/` at the repo root, created lazily. See `docs/agents/domain.md`.

## CI/CD

CI runs `ruff check`, `ruff format --check`, `lint-imports` (package layering, see the README's project layout), `mypy marketforge` and `pytest` (install the tools with `pip install -e . --group dev`); run them before pushing. CI also fails if any seed's output differs from the latest release without a major version bump, and a release is blocked if a commit marked breaking (`type!:` or `BREAKING CHANGE:`) ships without a major bump. A push to `main` releases the version in `pyproject.toml` when it is not yet tagged, and PRs into `main` must bump it and add a `CHANGELOG.md` section, so merge to `main` only to release. See `docs/ci-cd.md`.

The website (`website/`, Astro + Starlight) is built and link-checked in CI (`cd website && npm ci && npm run build && npm run check-links`) and deployed to GitHub Pages from `main` by CD. Its changelog, glossary and ADR pages are generated from `CHANGELOG.md`, `GLOSSARY.md` and `docs/adr/`; edit those, never the generated copies.
