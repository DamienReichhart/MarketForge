"""Tests for the third-party licence report and policy (.github/scripts/licenses.py)."""

from __future__ import annotations

import importlib.metadata
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".github" / "scripts" / "licenses.py"
if not SCRIPT.is_file():  # running from the sdist, which ships tests/ but not .github/
    pytest.skip("release tooling is not part of the sdist", allow_module_level=True)

_spec = importlib.util.spec_from_file_location("licenses", SCRIPT)
assert _spec is not None and _spec.loader is not None
licenses = importlib.util.module_from_spec(_spec)
sys.modules["licenses"] = licenses
_spec.loader.exec_module(licenses)

PERMISSIVE = ["MIT", "BSD-3-Clause", "Apache-2.0"]


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("MIT", True),
        ("mit", True),
        ("GPL-3.0-only", False),
        ("MIT OR GPL-3.0-only", True),
        ("(GPL-3.0-only or MIT)", True),
        ("MIT AND GPL-3.0-only", False),
        ("MIT AND (BSD-3-Clause OR GPL-2.0-only)", True),
        ("(MIT AND GPL-2.0-only) OR Apache-2.0", True),
        ("Apache-2.0 WITH LLVM-exception", False),
    ],
)
def test_spdx_allowed(expression, expected):
    assert licenses.spdx_allowed(expression, PERMISSIVE) is expected


def test_spdx_allowed_with_an_allowed_exception():
    assert licenses.spdx_allowed("Apache-2.0 WITH LLVM-exception", PERMISSIVE, ["LLVM-exception"])


@pytest.mark.parametrize(
    "expression", ["", "MIT OR", "(MIT", "MIT)", "AND MIT", "MIT WITH", "MIT/X11", "BSD, MIT"]
)
def test_spdx_allowed_rejects_what_is_not_spdx(expression):
    with pytest.raises(licenses.LicenseError, match="SPDX"):
        licenses.spdx_allowed(expression, PERMISSIVE)


def _meta(**fields: str | list[str]) -> importlib.metadata.PackageMetadata:
    from email.message import Message

    message = Message()
    for key, value in fields.items():
        for item in value if isinstance(value, list) else [value]:
            message[key.replace("_", "-")] = item
    return message  # type: ignore[return-value]


def test_declared_license_prefers_the_pep_639_expression():
    assert licenses.declared_license(_meta(License_Expression="MIT", License="BSD")) == "MIT"
    assert licenses.declared_license(_meta(License="MPL-2.0 AND MIT")) == "MPL-2.0 AND MIT"
    classifiers = ["License :: OSI Approved :: BSD License", "Programming Language :: Python"]
    assert licenses.declared_license(_meta(Classifier=classifiers)) == "BSD License"
    # A whole licence text in the License field is not a licence name.
    full_text = "Copyright (c) 2010\nAll rights reserved."
    assert licenses.declared_license(_meta(License=full_text, Classifier=classifiers)) == (
        "BSD License"
    )


def _policy(**packages: dict[str, object]) -> object:
    return licenses.Policy(
        allowed=frozenset(PERMISSIVE),
        exceptions=frozenset(),
        packages={licenses.normalize(k): v for k, v in packages.items()},
    )


def _package(declared: str = "MIT", texts=(("LICENSE", "Copyright"),)) -> object:
    return licenses.Package("Some_Pkg", "1.0", declared, "", tuple(texts))


def test_resolve_accepts_an_allowed_licence():
    assert licenses.resolve(_package(), _policy()) == "MIT"


def test_resolve_blocks_copyleft_unless_allowed_for_the_package():
    with pytest.raises(licenses.LicenseError, match="does not allow"):
        licenses.resolve(_package("GPL-3.0-only"), _policy())
    allowed = _policy(**{"some-pkg": {"declared": "GPL-3.0-only", "allow": ["GPL-3.0-only"]}})
    assert licenses.resolve(_package("GPL-3.0-only"), allowed) == "GPL-3.0-only"


def test_resolve_maps_a_licence_that_is_not_spdx():
    with pytest.raises(licenses.LicenseError, match="not an SPDX expression"):
        licenses.resolve(_package("BSD, see LICENSE"), _policy())
    with pytest.raises(licenses.LicenseError, match="license = '<SPDX expression>'"):
        licenses.resolve(_package("BSD"), _policy())
    mapped = _policy(some_pkg={"declared": "BSD", "license": "BSD-3-Clause"})
    assert licenses.resolve(_package("BSD"), mapped) == "BSD-3-Clause"


def test_resolve_rejects_an_entry_reviewed_for_another_licence():
    reviewed = _policy(some_pkg={"declared": "MIT", "allow": ["GPL-3.0-only"]})
    with pytest.raises(licenses.LicenseError, match="was reviewed for 'MIT'"):
        licenses.resolve(_package("GPL-3.0-only"), reviewed)


def test_resolve_requires_a_licence_text():
    with pytest.raises(licenses.LicenseError, match="ships no licence text"):
        licenses.resolve(_package(texts=()), _policy())


def _install(site: Path, name: str, version: str, metadata: str, files: dict[str, str]) -> None:
    info = site / f"{name}-{version}.dist-info"
    info.mkdir(parents=True)
    (info / "METADATA").write_text(
        f"Metadata-Version: 2.4\nName: {name}\nVersion: {version}\n{metadata}", encoding="utf-8"
    )
    for path, text in files.items():
        (info / path).parent.mkdir(parents=True, exist_ok=True)
        (info / path).write_text(text, encoding="utf-8")
    record = [f"{info.name}/{p},," for p in ["METADATA", *files]]
    (info / "RECORD").write_text("\n".join(record) + "\n", encoding="utf-8")


def test_run_writes_the_texts_of_every_platform(tmp_path):
    linux, windows = tmp_path / "linux", tmp_path / "windows"
    for site in (linux, windows):
        _install(site, "marketforge", "9.9.9", "License-Expression: Apache-2.0\n", {})
        _install(
            site,
            "dep",
            "1.0",
            "License-Expression: Apache-2.0\nLicense-File: LICENSE\nLicense-File: NOTICE\n",
            {"licenses/LICENSE": "Copyright Dep\r\n", "licenses/NOTICE": "Dep NOTICE"},
        )
    # A Windows-only dependency with pre-PEP 639 metadata: its licence file is found anyway.
    _install(
        windows,
        "winonly",
        "2.0",
        "Classifier: License :: OSI Approved :: BSD License\n",
        {"LICENSE.txt": "Copyright Win"},
    )
    out = tmp_path / "out" / "report.txt"
    policy = _policy(winonly={"declared": "BSD License", "license": "BSD-3-Clause"})
    assert licenses.run([linux, windows], out, "Linux and Windows", policy) == []
    report = out.read_text(encoding="utf-8")
    assert report.startswith("MarketForge 9.9.9: third-party licences\n")
    assert "resolved when 9.9.9 was built (Linux and Windows)" in report
    assert report.count("\ndep 1.0\n") == 1  # listed once, though installed on both platforms
    assert "----- NOTICE -----\n\nDep NOTICE" in report
    assert "Copyright Dep\n" in report and "\r" not in report
    assert "winonly 2.0\nLicence: BSD-3-Clause\nDeclared as: BSD License" in report
    assert "marketforge 9.9.9" not in report


def test_run_reports_every_failure_and_writes_nothing(tmp_path):
    _install(tmp_path, "marketforge", "1.0", "", {})
    _install(tmp_path, "gpl", "1.0", "License-Expression: GPL-3.0-only\n", {"LICENSE": "GPL"})
    _install(tmp_path, "bare", "1.0", "License-Expression: MIT\n", {})
    out = tmp_path / "report.txt"
    errors = licenses.run([tmp_path], out, "Linux", _policy())
    assert len(errors) == 2 and "bare 1.0" in errors[0] and "gpl 1.0" in errors[1]
    assert not out.exists()


def test_run_needs_the_wheel_in_the_paths(tmp_path):
    with pytest.raises(licenses.LicenseError, match="no marketforge distribution"):
        licenses.run([tmp_path], tmp_path / "report.txt", "Linux", _policy())


def test_the_policy_entries_name_their_reason():
    policy = licenses.load_policy()
    assert {"MIT", "Apache-2.0", "BSD-3-Clause"} <= policy.allowed
    assert not {"GPL-3.0-only", "AGPL-3.0-only", "LGPL-3.0-only"} & policy.allowed
    for name, entry in policy.packages.items():
        assert entry.get("declared"), name
        assert entry.get("reason"), name
