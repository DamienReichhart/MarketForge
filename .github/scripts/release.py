"""Release helpers for the CD pipeline (.github/workflows/cd.yml).

Subcommands:

    guard        Resolve the version from pyproject.toml and refuse to release
                 it if it is invalid, already tagged, not newer than the latest
                 tag, already on PyPI, missing from CHANGELOG.md, or not a
                 major bump although a commit since the latest tag is marked
                 breaking. Writes `release`, `name`, `version`, `tag` and
                 `prerelease` to $GITHUB_OUTPUT. With --if-unreleased, an
                 already tagged version is not an error: `release=false`.
    check-dist   Check that dist/ holds exactly the sdist and wheel of a version.
    check-sbom   Check that a CycloneDX SBOM describes this release, lists every
                 runtime dependency, and will be accepted by actions/attest.
    notes        Print the CHANGELOG.md section of a version (release notes).

Every failure is reported as a GitHub `::error::` annotation and exits 1.
Only `guard` needs a third-party package (`packaging`); the rest is stdlib.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import tomllib
import urllib.error
import urllib.request
from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from packaging.version import Version

ROOT = Path(__file__).resolve().parents[2]
TAG_PREFIX = "v"


class ReleaseError(Exception):
    """A check failed; the message says why and how to fix it."""


# --------------------------------------------------------------------------- #
# Pure checks (unit-tested in tests/test_release_script.py)
# --------------------------------------------------------------------------- #


def read_project(pyproject: Path) -> tuple[str, str]:
    """Return (distribution name, version) from a pyproject.toml."""
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    project = data.get("project", {})
    if "version" in project.get("dynamic", []):
        raise ReleaseError(f"{pyproject}: the version must be static, not dynamic")
    try:
        return project["name"], str(project["version"])
    except KeyError as e:
        raise ReleaseError(f"{pyproject}: missing [project].{e.args[0]}") from None


def parse_version(raw: str) -> Version:
    """Parse a PEP 440 version and insist it is written in canonical form."""
    from packaging.version import InvalidVersion, Version

    try:
        version = Version(raw)
    except InvalidVersion:
        raise ReleaseError(f"'{raw}' is not a valid PEP 440 version") from None
    if str(version) != raw:
        raise ReleaseError(
            f"version '{raw}' is not in canonical form; write it as '{version}' "
            "so the tag, the PyPI release and the file names all agree"
        )
    if version.local is not None:
        raise ReleaseError(f"version '{raw}' has a local segment; PyPI rejects those")
    return version


def tag_versions(tags: Iterable[str]) -> dict[Version, str]:
    """Map each version-like tag (v1.2.3, V2.0, 3.0.0rc1, ...) to its version."""
    from packaging.version import InvalidVersion, Version

    out: dict[Version, str] = {}
    for tag in tags:
        match = re.fullmatch(r"[vV]?(\d.*)", tag.strip())
        if not match:
            continue
        try:
            out[Version(match.group(1))] = tag
        except InvalidVersion:
            continue
    return out


def check_not_tagged(version: Version, tags: Iterable[str]) -> None:
    """Fail if any existing tag denotes the same version (V3.0 == v3.0.0)."""
    existing = tag_versions(tags)
    if version in existing:
        raise ReleaseError(
            f"version {version} is already released: tag '{existing[version]}' exists. "
            "Bump [project].version in pyproject.toml (and add a CHANGELOG.md entry) "
            "to cut a new release"
        )


def check_newer_than_tags(version: Version, tags: Iterable[str]) -> None:
    """Fail if the version is not greater than every released version."""
    existing = tag_versions(tags)
    if existing:
        latest = max(existing)
        if version <= latest:
            raise ReleaseError(
                f"version {version} is not newer than the latest release "
                f"{latest} (tag '{existing[latest]}'); versions released from main "
                "must increase"
            )


# Conventional Commits: `feat!: ...`, `refactor(api)!: ...`, or a footer.
_BREAKING_SUBJECT = re.compile(r"^([A-Za-z]+)(?:\([^)]*\))?!:")
_BREAKING_FOOTER = re.compile(r"^BREAKING[ -]CHANGE:", re.MULTILINE)
_TYPE = re.compile(r"^([A-Za-z]+)(?:\([^)]*\))?!?:")
# The major version is for breaks of the public API (ADR 0011). Commits of
# these types cannot change it, whatever their marker says; `build` can (a
# dropped Python version or dependency breaks users), so it counts.
_NON_API_TYPES = frozenset({"docs", "ci", "test", "style", "chore"})


def breaking_commits(messages: Iterable[str]) -> list[str]:
    """Subjects of the commit messages that mark a break of the public API."""
    out = []
    for message in messages:
        subject = message.strip().splitlines()[0] if message.strip() else ""
        marked = _BREAKING_SUBJECT.match(subject) or _BREAKING_FOOTER.search(message)
        kind = _TYPE.match(subject)
        if marked and not (kind and kind.group(1).lower() in _NON_API_TYPES):
            out.append(subject)
    return out


def check_breaking_bump(version: Version, latest: Version | None, breaking: list[str]) -> None:
    """Fail if breaking commits are released without a major bump (minor below 1.0)."""
    if not breaking or latest is None:
        return
    if latest.major == 0:
        bumped = version.major > 0 or version.minor > latest.minor
    else:
        bumped = version.major > latest.major
    if not bumped:
        listed = "; ".join(breaking[:5]) + (
            f" (+{len(breaking) - 5} more)" if len(breaking) > 5 else ""
        )
        raise ReleaseError(
            f"{len(breaking)} commit(s) since {latest} are marked breaking ({listed}), "
            f"but {version} is not a major release. Bump the major version, or reword "
            "the commits if they do not break users"
        )


def changelog_section(text: str, version: str) -> str:
    """Return the body of the `## <version>` section of a changelog.

    Accepts `## 3.0.0`, `## v3.0.0`, `## [3.0.0]` and a trailing date
    (`## [3.0.0] - 2026-11-16`). The section ends at the next `## ` heading.
    """
    heading = re.compile(
        rf"^##[ \t]+\[?v?{re.escape(version)}\]?(?:[ \t]+.*)?$", re.IGNORECASE | re.MULTILINE
    )
    match = heading.search(text)
    if not match:
        raise ReleaseError(
            f"CHANGELOG.md has no '## {version}' section; document the release before tagging it"
        )
    rest = text[match.end() :]
    end = re.search(r"^##[ \t]", rest, re.MULTILINE)
    body = (rest[: end.start()] if end else rest).strip()
    if not body:
        raise ReleaseError(f"the '## {version}' section of CHANGELOG.md is empty")
    return body


def expected_dist_files(name: str, version: str) -> set[str]:
    """File names of the sdist and pure-Python wheel for name==version."""
    normalized = re.sub(r"[-_.]+", "_", name).lower()
    return {f"{normalized}-{version}.tar.gz", f"{normalized}-{version}-py3-none-any.whl"}


def check_dist(dist: Path, name: str, version: str) -> list[str]:
    # Dotfiles (uv build writes dist/.gitignore) are never uploaded.
    found = sorted(p.name for p in dist.iterdir() if p.is_file() and not p.name.startswith("."))
    expected = expected_dist_files(name, version)
    if set(found) != expected:
        raise ReleaseError(
            f"{dist} holds {found or 'nothing'}, expected exactly {sorted(expected)}"
        )
    return found


def _normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def runtime_dependencies(pyproject: Path) -> set[str]:
    """Normalized names of the [project].dependencies of a pyproject.toml."""
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    return {
        _normalize(re.match(r"[A-Za-z0-9._-]+", req.strip()).group())  # type: ignore[union-attr]
        for req in data.get("project", {}).get("dependencies", [])
    }


_SERIAL_NUMBER = re.compile(
    r"urn:uuid:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE
)


def check_sbom(bom: dict[str, object], name: str, version: str, dependencies: set[str]) -> int:
    """Validate a CycloneDX SBOM for name==version; return its component count.

    The format checks mirror what actions/attest requires before it will
    attest an SBOM (bomFormat, specVersion and serialNumber all present), so
    a bad SBOM fails CI on the pull request instead of the release.
    """
    if bom.get("bomFormat") != "CycloneDX" or not bom.get("specVersion"):
        raise ReleaseError("the SBOM is not CycloneDX JSON (bomFormat/specVersion missing)")
    if not _SERIAL_NUMBER.fullmatch(str(bom.get("serialNumber", ""))):
        raise ReleaseError(
            "the SBOM has no 'urn:uuid:' serialNumber, so actions/attest rejects it "
            "('Unsupported SBOM format'). Do not generate it with --output-reproducible"
        )
    metadata = bom.get("metadata")
    root = metadata.get("component", {}) if isinstance(metadata, dict) else {}
    if (_normalize(str(root.get("name", ""))), root.get("version")) != (_normalize(name), version):
        raise ReleaseError(
            f"the SBOM describes {root.get('name')} {root.get('version')}, not {name} {version}"
        )
    components = bom.get("components")
    listed = {
        _normalize(str(c.get("name", "")))
        for c in (components if isinstance(components, list) else [])
        if isinstance(c, dict)
    }
    if missing := sorted(dependencies - listed):
        raise ReleaseError(f"the SBOM does not list the runtime dependencies {missing}")
    return len(listed)


# --------------------------------------------------------------------------- #
# Side effects: git, PyPI, GitHub Actions I/O
# --------------------------------------------------------------------------- #


def git_tags() -> list[str]:
    """Tags on the remote, falling back to local ones (both are checked)."""
    tags: set[str] = set()
    remote = subprocess.run(
        ["git", "ls-remote", "--tags", "--refs", "origin"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if remote.returncode == 0:
        tags.update(line.split("refs/tags/", 1)[1] for line in remote.stdout.splitlines() if line)
    else:
        warn(f"could not list remote tags ({remote.stderr.strip()}); using local tags only")
    local = subprocess.run(
        ["git", "tag", "--list"], cwd=ROOT, capture_output=True, text=True, check=True
    )
    tags.update(t for t in local.stdout.splitlines() if t)
    return sorted(tags)


def commit_messages_since(tag: str) -> list[str]:
    """Full messages of the commits reachable from HEAD but not from `tag`."""
    result = subprocess.run(
        ["git", "log", "--format=%B%x1e", f"refs/tags/{tag}..HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise ReleaseError(
            f"cannot list the commits since tag '{tag}' ({result.stderr.strip()}); "
            "check out the full history (fetch-depth: 0)"
        )
    return [m for m in result.stdout.split("\x1e") if m.strip()]


def pypi_has_version(name: str, version: str, attempts: int = 4) -> bool:
    """True if PyPI already serves name==version. Retries transient errors."""
    url = f"https://pypi.org/pypi/{name}/{version}/json"
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                json.load(response)
                return True
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return False
            error = f"HTTP {e.code}"
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            error = str(e)
        if attempt < attempts:
            time.sleep(2**attempt)
    raise ReleaseError(f"could not query {url} after {attempts} attempts ({error})")


def warn(message: str) -> None:
    print(f"::warning title=release::{message}")


def set_outputs(**values: str) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    lines = [f"{key}={value}" for key, value in values.items()]
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
    for line in lines:
        print(line)


def summary(markdown: str) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(markdown + "\n")


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #


def cmd_guard(args: argparse.Namespace) -> None:
    name, raw = read_project(ROOT / "pyproject.toml")
    version = parse_version(raw)
    tag = f"{TAG_PREFIX}{version}"
    print(f"Candidate release: {name} {version} (tag {tag})")

    tags = git_tags()
    existing = tag_versions(tags)
    if args.if_unreleased and version in existing:
        print(
            f"::notice title=Nothing to release::{name} {version} is already released "
            f"(tag '{existing[version]}'). Bump [project].version to cut a new release"
        )
        set_outputs(release="false", name=name, version=str(version), tag=tag, prerelease="false")
        summary(
            f"### Nothing to release\n\n`{name}` {version} is already tagged "
            f"`{existing[version]}`; CI ran, nothing was published.\n"
        )
        return
    check_not_tagged(version, tags)
    check_newer_than_tags(version, tags)
    latest = max(existing, default=None)
    if latest is not None:
        check_breaking_bump(
            version, latest, breaking_commits(commit_messages_since(existing[latest]))
        )
    changelog_section((ROOT / "CHANGELOG.md").read_text(encoding="utf-8"), str(version))
    if not args.skip_pypi and pypi_has_version(name, str(version)):
        raise ReleaseError(
            f"{name} {version} is already on PyPI (but has no '{tag}' tag). PyPI never "
            "accepts the same version twice: bump [project].version in pyproject.toml"
        )

    set_outputs(
        release="true",
        name=name,
        version=str(version),
        tag=tag,
        prerelease=str(version.is_prerelease).lower(),
    )
    summary(
        f"### Release guard passed\n\n"
        f"| | |\n|---|---|\n| Package | `{name}` |\n| Version | `{version}` |\n"
        f"| Tag | `{tag}` (not taken) |\n| Pre-release | {version.is_prerelease} |\n"
        f"| Latest existing tag | `{max(tag_versions(tags), default='none')}` |\n"
    )


def cmd_check_dist(args: argparse.Namespace) -> None:
    name, raw = read_project(ROOT / "pyproject.toml")
    version = args.version or raw
    for file_name in check_dist(Path(args.dist), name, version):
        print(f"ok  {file_name}")


def cmd_check_sbom(args: argparse.Namespace) -> None:
    name, version = read_project(ROOT / "pyproject.toml")
    path = Path(args.sbom)
    bom = json.loads(path.read_text(encoding="utf-8"))
    count = check_sbom(bom, name, version, runtime_dependencies(ROOT / "pyproject.toml"))
    print(f"ok  {path.name}: CycloneDX {bom['specVersion']}, {name} {version}, {count} components")


def cmd_notes(args: argparse.Namespace) -> None:
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    print(changelog_section(text, args.version))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    guard = sub.add_parser("guard", help="validate that pyproject's version can be released")
    guard.add_argument("--skip-pypi", action="store_true", help="do not query PyPI")
    guard.add_argument(
        "--if-unreleased",
        action="store_true",
        help="an already tagged version means nothing to release (exit 0, release=false)",
    )
    guard.set_defaults(func=cmd_guard)

    dist = sub.add_parser("check-dist", help="validate the built distributions")
    dist.add_argument("dist", nargs="?", default="dist")
    dist.add_argument("--version", help="expected version (default: pyproject's)")
    dist.set_defaults(func=cmd_check_dist)

    sbom = sub.add_parser("check-sbom", help="validate a release's CycloneDX SBOM")
    sbom.add_argument("sbom")
    sbom.set_defaults(func=cmd_check_sbom)

    notes = sub.add_parser("notes", help="print a version's CHANGELOG section")
    notes.add_argument("version")
    notes.set_defaults(func=cmd_notes)

    args = parser.parse_args(argv)
    try:
        args.func(args)
    except ReleaseError as e:
        print(f"::error title=Release blocked::{e}")
        summary(f"### :x: Release blocked\n\n{e}\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
