# CI/CD

These workflows live in `.github/workflows/`:

| Workflow | Runs on | Purpose |
| --- | --- | --- |
| `ci.yml` (**CI**) | every PR, push to `dev`, merge queue, weekly schedule, manual; on `main` it runs inside CD | Quality gate |
| `cd.yml` (**CD**) | push to `main`, manual dry run | `main`'s CI, release to PyPI and GitHub when the version is new, and deployment of the website to GitHub Pages |
| `codeql.yml` (**CodeQL**) | PR, push to `dev`/`main`, weekly | Static security analysis of the Python code and the workflows |
| `scorecard.yml` (**Scorecard**) | push to `main`, weekly, branch-protection changes | OpenSSF Scorecard: grades supply-chain practices; findings go to code scanning, results feed the public badge |
| `links.yml` (**External links**) | weekly, manual | Builds the website and checks every link to another site: fails on a page that is gone (404, 410) or a host that no longer resolves, and lists sites that refuse robots, err or time out as warnings. Not run on pull requests: a remote site's state says nothing about a change, and an outage elsewhere must never block a merge |
| `scheduled-alerts.yml` | a scheduled CI, CodeQL, Scorecard or External links run completes | Opens an issue (label `scheduled-failure`) when a scheduled run fails, comments while it keeps failing, closes it when one passes. GitHub alone notifies only whoever last edited the cron line. Runs from `main` only |

All third-party actions are pinned to a commit SHA, and runner images to a
version (`ubuntu-24.04`, `ubuntu-24.04-arm`, `macos-15`, `windows-2025`), not `-latest`: the
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
| Test | `pytest` against **the wheel the build job made** (the file CD publishes), not an editable install: the source package is deleted from the checkout first, so nothing can import it instead. On Linux (x86-64) for Python 3.12 to 3.14, and on Linux arm64, macOS (arm64) and Windows for 3.12 and 3.14. A file missing from the wheel or a platform where it does not work fails here, before PyPI, not in CD's **verify** after the upload |
| Test coverage | `pytest --cov` on an editable install (coverage maps lines to the source tree), Linux, Python 3.13: 90% branch coverage minimum; uploads `coverage.xml` |
| Test (py3.15 preview, non-blocking) | `pytest` on the next CPython (3.15, in beta) with binary wheels only. **Not** part of CI OK: an early warning, never a merge blocker. Promote it into the test matrix once 3.15 is final |
| Test (lowest supported dependencies) | `pytest` with every dependency at the floor declared in `pyproject.toml` (`uv --resolution lowest-direct`). A floor that does not really work fails here |
| Seed reproducibility | On Linux (x86-64 and arm64), macOS and Windows: fingerprints (SHA-256) 786 outputs of fixed-seed scenarios (every instrument, CSV bytes and in-memory frames, all timeframes, anomalies, regime labels, both DST transitions, a leap day) with the code under test (the wheel CI built) and with the latest PyPI release, **in the same environment**, and fails on any difference unless the major version was bumped (ADR 0006). Same dependencies and CPU on both sides, so a difference is the code's. `BASELINE_VERSION` overrides the release compared against |
| Performance | Times fixed workloads (each market, forex crosses, anomalies, every timeframe, the CSV writer, and a cold start: a fresh interpreter's import and first generation) with the code under test and with the latest PyPI release, on **one runner with the same dependencies**, interleaving the two versions' runs and keeping each one's fastest time, so the runner's speed cancels out. Fails if any workload is more than **15% slower** than the release (ADRs 0003, 0007). For an intended slowdown, see [Performance gate](#performance-gate). The timings are uploaded as the `performance` artifact |
| Documentation examples | Checks every `python`, `bash` and `toml` block of `README.md` and the website's pages against the wheel CI built, and runs them; see [Documentation examples](#documentation-examples) |
| Build & verify distributions | Validates `pyproject.toml`, builds the sdist and then the wheel *from the sdist* with reproducible timestamps, runs `twine check --strict` and `check-wheel-contents`, installs the wheel in a clean environment and runs the CLI and a small generation, then writes a CycloneDX SBOM of that environment and checks it (`release.py check-sbom`: the format `actions/attest` requires, this release as the root component, every runtime dependency listed). Uploads the `dist` and `sbom` artifacts |
| Dependency vulnerability audit | `pip-audit` on the runtime dependency tree as resolved for Python 3.12 and 3.14 |
| Secret scan | `gitleaks` over **every commit** of the history, with values redacted in the log. The project has no secrets by design (trusted publishing, no tokens) and GitHub push protection already blocks known token formats; this adds the history and generic patterns. gitleaks is built from source at the version in `GITLEAKS_VERSION` through the Go module proxy, whose checksum database verifies it; Dependabot does not bump that version, so review it with the runner images. A false positive is silenced with a `gitleaks:allow` comment on its line, or a `.gitleaks.toml` allowlist |
| Lint GitHub workflows | `actionlint` (with shellcheck) and `zizmor` (Actions security audit) |
| Dependency review | PRs only: fails if the PR adds a dependency with a known moderate-or-worse vulnerability |
| Website | Type-checks the Astro/Starlight site in `website/` (`npm run check`: `astro check`, strict TypeScript) and builds it from its lockfile (`npm ci`; the changelog, glossary and ADRs are copied in from the repository at build time), fails on any broken internal link (`npm run check-links`), and uploads the built site as the `github-pages` artifact that CD deploys |
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
pip install . --group docs && python -I .github/scripts/doc_examples.py   # in a fresh venv
```

### Performance gate

`.github/scripts/perf.py` compares the code under test with the latest
release (`perf.py run` times both, `perf.py compare` judges). Workloads are
warmed up first, so Numba compilation is not timed, except by the cold-start
workload, which is meant to catch a slow import or a lost `cache=True`.

A slowdown can be the price of a fix. Then say so in a commit message, with
a trailer, and the gate allows up to that much on every workload until the
next release becomes the baseline:

```
fix(simulation): sum returns exactly

Accept-Slowdown: 25%
```

To measure locally, make two virtual environments with the same dependencies
(one with the wheel, one with the release) as the CI job does, then run
`perf.py run perf.json --head HEAD_VENV/bin/python --base BASE_VENV/bin/python`
and `perf.py compare perf.json`.

### Documentation examples

`.github/scripts/doc_examples.py` reads the fenced code blocks of `README.md`
and of the website's pages (`website/src/content/docs/`) and, page by page in
an empty directory, so an example can write `./data` and a later one read it:

- **python**: every `mf.NAME(...)` must be in the public API and bind to its
  real signature; then the block runs. The blocks of a page share one
  namespace where `import marketforge as mf` is done.
- **bash**: only `marketforge` commands count (`pip`, `git`, `npm` are not
  run). `generate` is planned with `--dry-run`, which checks instruments,
  dates and override files without simulating; the other commands go through
  the real command-line parser. Then the commands run.
- **toml**: loaded as an override file. A block whose first line is
  `# NAME.toml` is also saved as `NAME.toml` for the page's next examples.

A flag after the language opts a block out of running:

| Fence | Use it for |
| --- | --- |
| ` ```python check=static ` | Too long to run in CI (years of data, dozens of seeds), or it uses data or functions the reader provides. Still checked against the API and the command-line parser |
| ` ```python check=signature ` | A displayed signature, `mf.NAME(...) -> TYPE`: it must match the real one exactly |
| ` ```bash check=none ` | Not checked at all. Prefer `text` as the language for something that is not a command, such as a usage synopsis |

Errors are annotated on the page's line in the pull request.

## CD: how a release happens

**To release: bump `[project].version` in `pyproject.toml`, add a
`## <version>` section to `CHANGELOG.md`, and merge to `main`.** That is all.
`pyproject.toml` is the only place the version is written;
`marketforge.__version__` reads it back from the installed metadata.

```
guard ─┐
ci ────┴─► publish (PyPI) ──► github-release (tag + release)
   │                     └──► verify (pip install from PyPI on Linux, macOS, Windows)
   └─────► pages (website on GitHub Pages)
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
   (Python 3.12 and 3.14), Linux arm64, macOS and Windows (3.14), retrying while the CDN
   catches up, and runs the CLI and a generation across all three markets.
6. **pages** deploys the website CI built and link-checked in this run (the
   `github-pages` artifact) to GitHub Pages, at
   <https://damienreichhart.github.io/MarketForge/>. It needs only **ci**, so
   it runs on every push to `main`, whether or not there is a version to
   release, and a failed PyPI release does not hold the site back.

A push to `main` that does not bump the version (a docs fix, say) is a green
no-op release that still redeploys the website. PRs into `main` are stricter: their **Release readiness** job
runs the guard without the "nothing to release" escape, so a PR that forgets
the bump cannot merge. Merge to `main` to release; integrate on `dev`.

Releases never run concurrently, and a running release is never cancelled.

### Dry run

*Actions → CD → Run workflow* with **dry run** checked (the default) runs the
guard, the full CI and the build (the website included) on any branch, and
publishes and deploys nothing. Use it
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
7. **GitHub Pages.** In *Settings → Pages*, set *Source* to **GitHub
   Actions**. In *Settings → Environments → github-pages* (created by that
   switch), limit deployment branches to `main`. To serve the site from a
   custom domain, set `site` in `website/astro.config.mjs` to it, remove
   `base`, add `website/public/CNAME`, and configure the domain in the Pages
   settings.
8. **Blame.** Run `git config blame.ignoreRevsFile .git-blame-ignore-revs`
   locally to hide the bulk reformat commit from `git blame`.
