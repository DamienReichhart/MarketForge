# Security policy

## Supported versions

Only the latest release on [PyPI](https://pypi.org/project/marketforge/)
receives security fixes. Upgrade before reporting.

## Reporting a vulnerability

**Do not open a public issue.** Report it privately through GitHub:
*Security → Report a vulnerability* on
[DamienReichhart/MarketForge](https://github.com/DamienReichhart/MarketForge/security/advisories/new).

Include the affected version, how to reproduce it, and its impact. You will
get an acknowledgement within 7 days. Once a fix is released, the advisory
is published and you are credited unless you ask otherwise.

## Verifying a release

Every release is built and published by GitHub Actions through PyPI trusted
publishing, with signed build-provenance and SBOM attestations. Check a
downloaded distribution with:

```bash
gh attestation verify marketforge-<version>-py3-none-any.whl --repo DamienReichhart/MarketForge
```

The CycloneDX SBOM of each release is attached to its
[GitHub release](https://github.com/DamienReichhart/MarketForge/releases).
