"""Versions stated in more than one place agree."""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if not (ROOT / "website" / "package.json").is_file():  # the sdist ships tests/ only
    pytest.skip("the website is not part of the sdist", allow_module_level=True)


def test_citation_names_the_release():
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    cited = re.search(r'^version: "([^"]+)"$', (ROOT / "CITATION.cff").read_text(), re.MULTILINE)
    assert cited and cited.group(1) == version["version"]


def test_the_websites_node_floor_is_the_node_ci_builds_it_with():
    nvmrc = (ROOT / "website" / ".nvmrc").read_text().strip()
    for name in ("package.json", "package-lock.json"):
        doc = json.loads((ROOT / "website" / name).read_text(encoding="utf-8"))
        engines = doc["engines"] if name == "package.json" else doc["packages"][""]["engines"]
        assert engines["node"] == f">={nvmrc}", name
