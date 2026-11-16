"""Shared pytest configuration for MarketForge tests."""

from __future__ import annotations

import pytest

# Files GitHub Actions reads back after a step. The release tooling under test
# writes to them, so under CI every test run would publish fixture data (fake
# tags, fake "Release blocked" errors) as the job's summary and outputs.
_ACTIONS_FILES = ("GITHUB_STEP_SUMMARY", "GITHUB_OUTPUT", "GITHUB_ENV", "GITHUB_PATH")


@pytest.fixture(autouse=True)
def _isolate_from_github_actions(monkeypatch):
    for name in _ACTIONS_FILES:
        monkeypatch.delenv(name, raising=False)
