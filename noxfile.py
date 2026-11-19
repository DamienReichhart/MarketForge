# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

"""
The checks CI runs, locally: ``nox`` runs them all, ``nox -s lint`` one.

Each session installs what it needs into its own virtual environment (uv is
used when it is installed: ``nox -db uv``). ``tests`` takes pytest arguments
after ``--``: ``nox -s tests -- tests/api -x``.
"""

from __future__ import annotations

from pathlib import Path

import nox

nox.options.default_venv_backend = "uv|virtualenv"
nox.options.sessions = ["lint", "typecheck", "tests"]
nox.options.error_on_missing_interpreters = False  # run the Pythons you have

PYTHONS = ["3.12", "3.13", "3.14", "3.15"]


@nox.session
def lint(session: nox.Session) -> None:
    """ruff (lint and format) and the package's layering contract."""
    session.install("-e", ".", "--group", "lint")
    session.run("ruff", "check", ".")
    session.run("ruff", "format", "--check", ".")
    session.run("lint-imports")


@nox.session
def typecheck(session: nox.Session) -> None:
    """mypy over the package."""
    session.install("-e", ".", "--group", "typecheck")
    session.run("mypy", "marketforge")


@nox.session(python=PYTHONS)
def tests(session: nox.Session) -> None:
    """The test suite, on every supported Python (``nox -s tests-3.13`` for one)."""
    session.install("-e", ".", "--group", "test", "--group", "fit")
    session.run("pytest", *session.posargs)


@nox.session
def docs(session: nox.Session) -> None:
    """Run every code block of the README and the website against a built wheel."""
    session.install("build")
    session.run("python", "-m", "build", "--wheel", "--outdir", session.create_tmp())
    wheel = next(Path(session.create_tmp()).glob("marketforge-*.whl"))
    session.install(str(wheel), "--group", "docs")
    session.run("python", "-I", ".github/scripts/doc_examples.py", *session.posargs)


@nox.session
def examples(session: nox.Session) -> None:
    """Run every script of examples/."""
    session.install(".", "--group", "docs")
    for script in sorted(Path("examples").glob("*.py")):
        session.run("python", "-I", str(script))
