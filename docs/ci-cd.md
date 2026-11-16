# CI/CD

These workflows live in `.github/workflows/`:

| Workflow | Runs on | Purpose |
| --- | --- | --- |
| `ci.yml` (**CI**) | every PR, push to `dev`, merge queue, weekly schedule, manual; on `main` it runs inside CD | Quality gate |
| `cd.yml` (**CD**) | push to `main`, manual dry run | `main`'s CI, and release to PyPI and GitHub when the version is new |
| `codeql.yml` (**CodeQL**) | PR, push to `dev`/`main`, weekly | Static security analysis of the Python code and the workflows |
| `scorecard.yml` (**Scorecard**) | push to `main`, weekly, branch-protection changes | OpenSSF Scorecard: grades supply-chain practices; findings go to code scanning, results feed the public badge |
| `scheduled-alerts.yml` | a scheduled CI, CodeQL or Scorecard run completes | Opens an issue (label `scheduled-failure`) when a scheduled run fails, comments while it keeps failing, closes it when one passes. GitHub alone notifies only whoever last edited the cron line. Runs from `main` only |

All third-party actions are pinned to a commit SHA, and runner images to a
version (`ubuntu-24.04`, `macos-15`, `windows-2025`), not `-latest`: the
distributions are built on these images, so moving to a new OS is a
deliberate PR with a green CI run, never GitHub's migration schedule.
Dependabot does not bump runner labels; review them yearly. Dependabot
(`.github/dependabot.yml`) opens one grouped PR a week against `dev` to bump
them. Every job starts with a read-only token; jobs that need more ask for it
explicitly.

## CI

| Job | What it checks |
| --- | --- |
| Lint & format | `ruff check`, `ruff format --check`, and `lint-imports`, which fails when a package imports from a layer above it (the contract is in `pyproject.toml`) |
| Type-check | `mypy marketforge` on Python 3.12 with numpy pinned to the declared floor (2.2) and on Python 3.14 with the newest numpy (numpy's type stubs differ between releases) |
| Test | `pytest` on Linux for Python 3.12 to 3.14, and on macOS and Windows for 3.12 and 3.14. The Linux 3.13 leg measures branch coverage (90% minimum) and uploads `coverage.xml` |
| Test (py3.15 preview, non-blocking) | `pytest` on the next CPython (3.15, in beta) with binary wheels only. **Not** part of CI OK: an early warning, never a merge blocker. Promote it into the test matrix once 3.15 is final |
| Test (lowest supported dependencies) | `pytest` with every dependency at the floor declared in `pyproject.toml` (`uv --resolution lowest-direct`). A floor that does not really work fails here |
| Seed reproducibility | On Linux, macOS and Windows: fingerprints (SHA-256) 786 outputs of fixed-seed scenarios (every instrument, CSV bytes and in-memory frames, all timeframes, anomalies, regime labels, both DST transitions, a leap day) with the code under test and with the latest PyPI release, **in the same environment**, and fails on any difference unless the major version was bumped (ADR 0006). Same dependencies and CPU on both sides, so a difference is the code's. `BASELINE_VERSION` overrides the release compared against |
| Build & verify distributions | Validates `pyproject.toml`, builds the sdist and then the wheel *from the sdist* with reproducible timestamps, runs `twine check --strict` and `check-wheel-contents`, installs the wheel in a clean environment and runs the CLI and a small generation, then writes a CycloneDX SBOM of that environment and checks it (`release.py check-sbom`: the format `actions/attest` requires, this release as the root component, every runtime dependency listed). Uploads the `dist` and `sbom` artifacts |
| Dependency vulnerability audit | `pip-audit` on the runtime dependency tree as resolved for Python 3.12 and 3.14 |
| Lint GitHub workflows | `actionlint` (with shellcheck) and `zizmor` (Actions security audit) |
| Dependency review | PRs only: fails if the PR adds a dependency with a known moderate-or-worse vulnerability |
| Release readiness | PRs (and merge-queue runs) into `main` only: runs the CD release guard below, so a PR that would fail to release (version not bumped, no CHANGELOG section, breaking commits without a major bump) is blocked before the merge |
| **CI OK** | Fails if any job above failed or was cancelled. **Make this the only required status check** |

The weekly scheduled run tests against the newest releases of every
dependency, so an upstream break or a new advisory shows up without waiting
for a commit.

### Running the checks locally

```bash
pip install -e . --group dev          # or: uv pip install -e . --group dev
ruff check . && ruff format --check . && lint-imports
mypy marketforge
pytest --cov
uv pip install -e . --group test --resolution lowest-direct && pytest   # floors, in a fresh venv
```

## CD: how a release happens

**To release: bump `[project].version` in `pyproject.toml`, add a
`## <version>` section to `CHANGELOG.md`, and merge to `main`.** That is all.
`pyproject.toml` is the only place the version is written;
`marketforge.__version__` reads it back from the installed metadata.

```
guard ─┐
ci ────┴─► publish (PyPI) ──► github-release (tag + release)
                         └──► verify (pip install from PyPI on Linux, macOS, Windows)
```

1. **guard** reads the version. If a tag for it already exists, in any
   spelling (`v3.0.0`, `V3.0`, `3.0.0`), there is **nothing to release**: CI
   still runs, nothing is published, and the run is green. Otherwise it
   **blocks the release** (the run fails, nothing is published) if:
   - it is not a canonical PEP 440 version (`3.1.0`, `3.1.0rc1`; not `3.1.0-rc1`);
   - it is not newer than every existing version tag;
   - PyPI already has it (PyPI never accepts the same version twice);
   - `CHANGELOG.md` has no non-empty `## <version>` section;
   - a commit since the latest tag is marked breaking (`feat!:`,
     `refactor(api)!:`, or a `BREAKING CHANGE:` footer) and the version is not
     a major bump (a minor bump below 1.0). The `!` is a promise to users:
     either bump the major version or reword the commit.
2. **ci** runs the full CI workflow on the commit, in parallel with the
   guard. This is `main`'s only CI run (`ci.yml` has no push trigger for
   `main`). Nothing is published unless all of it passes.
3. **publish** downloads the exact `dist` artifact CI built and tested, checks
   it holds only this version's sdist and wheel, records signed build
   provenance and SBOM attestations, and uploads to PyPI through trusted
   publishing (OIDC, no stored token). Check a download with
   `gh attestation verify <file> --repo DamienReichhart/MarketForge`.
4. **github-release** creates the tag `v<version>` on the released commit and a
   GitHub release with the CHANGELOG section as notes and the distributions
   and the SBOM (`marketforge-<version>.cdx.json`) attached. Versions with a pre-release segment (`rc`, `b`, `a`, `dev`) are
   marked as pre-releases.
5. **verify** installs the version from PyPI in clean environments on Linux
   (Python 3.12 and 3.14), macOS and Windows (3.14), retrying while the CDN
   catches up, and runs the CLI and a generation across all three markets.

A push to `main` that does not bump the version (a docs fix, say) is a green
no-op release. PRs into `main` are stricter: their **Release readiness** job
runs the guard without the "nothing to release" escape, so a PR that forgets
the bump cannot merge. Merge to `main` to release; integrate on `dev`.

Releases never run concurrently, and a running release is never cancelled.

### Dry run

*Actions → CD → Run workflow* with **dry run** checked (the default) runs the
guard, the full CI and the build on any branch, and publishes nothing. Use it
to check a release before merging. A non-dry run is refused outside `main`.

### When a release fails half-way

- Failed in **guard** or **ci**: nothing was published. Fix and push again.
- Failed in **publish** (for example `invalid-publisher`: the trusted
  publisher on PyPI does not match the repository, `cd.yml` or `Deploy`):
  nothing was published. Fix the configuration, then *Re-run failed jobs*.
- Failed in **github-release** or **verify** after PyPI accepted the upload:
  use *Re-run failed jobs*. The release job is idempotent: it reuses the tag
  if it already points at this commit. Do **not** push a new commit to retry:
  the guard would see the version on PyPI and block it.

## One-time repository setup

These are GitHub and PyPI settings; the workflows cannot apply them.

1. **Required check.** In *Settings → Rules → Rulesets*, protect `main` and
   `dev`: require a pull request and the status check **CI OK**.
2. **Trusted publishing (configured).** PyPI accepts uploads only from the
   publisher registered under *marketforge → Manage → Publishing*: owner
   `DamienReichhart`, repository `MarketForge`, workflow `cd.yml`,
   environment `Deploy`. There is no PyPI API token, in GitHub or anywhere
   else. Renaming `cd.yml` or the `Deploy` environment breaks publishing until
   the publisher on PyPI is updated to match.
3. **`Deploy` environment.** In *Settings → Environments → Deploy*, limit
   deployment branches to `main`. Add required reviewers if you want to
   approve each upload by hand.
4. **Tag protection.** Add a tag ruleset for `v*` that blocks deletion and
   updates, so a released tag can never be moved.
5. **Code scanning.** If CodeQL *default setup* is enabled, switch it off: it
   conflicts with `codeql.yml`.
6. **Private vulnerability reporting.** Enable it in *Settings → Code
   security*; `SECURITY.md` sends reporters there.
7. **Blame.** Run `git config blame.ignoreRevsFile .git-blame-ignore-revs`
   locally to hide the bulk reformat commit from `git blame`.
