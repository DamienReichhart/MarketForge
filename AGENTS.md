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

CI runs `ruff check`, `ruff format --check`, `mypy marketforge` and `pytest` (install the tools with `pip install -e . --group dev`); run them before pushing. A push to `main` releases the version in `pyproject.toml` and fails if that version is already tagged, so merge to `main` only to release. See `docs/ci-cd.md`.
