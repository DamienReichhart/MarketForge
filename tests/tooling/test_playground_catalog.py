"""Tests that the website playground's instrument catalog matches the package."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "website" / "scripts" / "playground_catalog.py"
if not SCRIPT.is_file():  # running from the sdist, which ships tests/ but not the website
    pytest.skip("website is not part of the sdist", allow_module_level=True)


def test_the_committed_playground_catalog_is_up_to_date():
    spec = importlib.util.spec_from_file_location("playground_catalog", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    committed = json.loads(module.OUT.read_text())
    assert committed == module.catalog(), (
        "website/src/samples/playground-catalog.json is stale: "
        "run `python website/scripts/playground_catalog.py`"
    )
