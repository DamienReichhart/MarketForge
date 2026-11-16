"""Tests for the CD release guard (.github/scripts/release.py)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from packaging.version import Version

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".github" / "scripts" / "release.py"
if not SCRIPT.is_file():  # running from the sdist, which ships tests/ but not .github/
    pytest.skip("release tooling is not part of the sdist", allow_module_level=True)

_spec = importlib.util.spec_from_file_location("release", SCRIPT)
assert _spec is not None and _spec.loader is not None
release = importlib.util.module_from_spec(_spec)
sys.modules["release"] = release
_spec.loader.exec_module(release)


def test_repository_version_is_releasable_and_documented():
    name, raw = release.read_project(ROOT / "pyproject.toml")
    assert name == "marketforge"
    version = release.parse_version(raw)
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert release.changelog_section(changelog, str(version))


def test_installed_version_matches_pyproject():
    import marketforge

    _, raw = release.read_project(ROOT / "pyproject.toml")
    assert marketforge.__version__ == raw


@pytest.mark.parametrize("raw", ["3.0.0", "3.1.0rc1", "4.0.0.dev2", "3.0.0.post1"])
def test_parse_version_accepts_canonical_versions(raw):
    assert str(release.parse_version(raw)) == raw


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ("3.0.0-rc1", "canonical"),
        ("v3.0.0", "canonical"),
        ("03.0.0", "canonical"),
        ("3.0.0+local", "local segment"),
        ("three", "not a valid PEP 440"),
    ],
)
def test_parse_version_rejects_bad_versions(raw, message):
    with pytest.raises(release.ReleaseError, match=message):
        release.parse_version(raw)


def test_tag_versions_understands_legacy_and_prefixed_tags():
    tags = ["V1.0", "V2.0", "v3.0.0rc1", "3.1.0", "nightly", "v-broken"]
    assert release.tag_versions(tags) == {
        Version("1.0"): "V1.0",
        Version("2.0"): "V2.0",
        Version("3.0.0rc1"): "v3.0.0rc1",
        Version("3.1.0"): "3.1.0",
    }


@pytest.mark.parametrize("existing", ["v3.0.0", "V3.0", "3.0.0", "V3.0.0"])
def test_existing_tag_blocks_the_release_whatever_its_spelling(existing):
    with pytest.raises(release.ReleaseError, match="already released"):
        release.check_not_tagged(Version("3.0.0"), ["V2.0", existing])


def test_untagged_version_passes():
    release.check_not_tagged(Version("3.0.0"), ["V1.0", "V2.0", "v3.0.0rc1"])
    release.check_newer_than_tags(Version("3.0.0"), ["V1.0", "V2.0", "v3.0.0rc1"])
    release.check_newer_than_tags(Version("1.0.0"), [])


@pytest.mark.parametrize("candidate", ["1.5.0", "2.0.0", "3.0.0rc1"])
def test_version_must_be_newer_than_every_tag(candidate):
    with pytest.raises(release.ReleaseError, match="not newer"):
        release.check_newer_than_tags(Version(candidate), ["V1.0", "V2.0", "v3.0.0rc2"])


CHANGELOG = """# Changelog

## [3.1.0] - 2026-12-01

### Fixed
- Something.

## 3.0.0

Big rewrite.

## 2.0.0
"""


@pytest.mark.parametrize(
    ("version", "expected"),
    [("3.1.0", "### Fixed\n- Something."), ("3.0.0", "Big rewrite.")],
)
def test_changelog_section_extracts_the_right_body(version, expected):
    assert release.changelog_section(CHANGELOG, version) == expected


def test_changelog_section_does_not_match_a_prefix_version():
    with pytest.raises(release.ReleaseError, match=r"no '## 3\.0' section"):
        release.changelog_section(CHANGELOG, "3.0")


def test_changelog_section_must_exist_and_not_be_empty():
    with pytest.raises(release.ReleaseError, match=r"no '## 4\.0\.0' section"):
        release.changelog_section(CHANGELOG, "4.0.0")
    with pytest.raises(release.ReleaseError, match="is empty"):
        release.changelog_section(CHANGELOG, "2.0.0")


def test_check_dist_wants_exactly_the_sdist_and_wheel(tmp_path):
    (tmp_path / "marketforge-3.0.0.tar.gz").touch()
    (tmp_path / "marketforge-3.0.0-py3-none-any.whl").touch()
    (tmp_path / ".gitignore").touch()
    assert len(release.check_dist(tmp_path, "marketforge", "3.0.0")) == 2

    (tmp_path / "marketforge-2.9.0-py3-none-any.whl").touch()
    with pytest.raises(release.ReleaseError, match="expected exactly"):
        release.check_dist(tmp_path, "marketforge", "3.0.0")


def test_read_project_rejects_dynamic_versions(tmp_path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "x"\ndynamic = ["version"]\n')
    with pytest.raises(release.ReleaseError, match="must be static"):
        release.read_project(pyproject)


def test_main_reports_failures_as_annotations(capsys, monkeypatch, tmp_path):
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    assert release.main(["notes", "9.9.9"]) == 1
    assert "::error title=Release blocked::" in capsys.readouterr().out
    assert "Release blocked" in summary.read_text()
