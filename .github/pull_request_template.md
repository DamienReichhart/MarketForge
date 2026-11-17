## What and why

<!-- What changes, and why. Link the issue: Closes #123 -->

## Checklist

- [ ] Commits follow [Conventional Commits](https://www.conventionalcommits.org/); a change that breaks users is marked `type!:` or has a `BREAKING CHANGE:` footer
- [ ] Tests cover the change
- [ ] Seeds still produce the same candles, or `MODEL_REVISION` is incremented and `CHANGELOG.md` lists the change under *Output changes* (CI: *Seed reproducibility*)
- [ ] Docs (`README.md`, `docs/`, ADRs) updated where behaviour changed

**Into `main` only (a merge releases):**

- [ ] `[project].version` in `pyproject.toml` is bumped (major if any commit breaks the public API)
- [ ] `CHANGELOG.md` has a `## <version>` section
