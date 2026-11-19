"""The documentation's examples run on one Python, the same in CI and nox,
on which every package they import installs."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest
from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parents[2]
CI = ROOT / ".github" / "workflows" / "ci.yml"
if not CI.is_file():  # running from the sdist, which ships tests/ but not .github/
    pytest.skip("CI configuration is not part of the sdist", allow_module_level=True)


def _setting(path: Path, pattern: str) -> str:
    match = re.search(pattern, path.read_text(encoding="utf-8"), re.MULTILINE)
    assert match, f"{pattern!r} not found in {path.name}"
    return match.group(1)


def test_ci_and_nox_run_the_documentation_on_the_same_python():
    ci = _setting(CI, r'^\s+DOCS_PYTHON: "([\d.]+)"$')
    nox = _setting(ROOT / "noxfile.py", r'^DOCS_PYTHON = "([\d.]+)"$')
    assert ci == nox


def test_every_documentation_dependency_installs_on_that_python():
    python = _setting(CI, r'^\s+DOCS_PYTHON: "([\d.]+)"$')
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    skipped = [
        str(req)
        for req in map(Requirement, project["dependency-groups"]["docs"])
        if req.marker is not None and not req.marker.evaluate({"python_version": python})
    ]
    assert not skipped, f"the documentation would run without {skipped} on Python {python}"
