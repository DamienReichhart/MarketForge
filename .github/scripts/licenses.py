"""Third-party licences of marketforge's runtime dependencies (CI, .github/workflows/ci.yml).

    python .github/scripts/licenses.py --path SITE_PACKAGES [--path ...] --out FILE

Reads the distributions installed in each --path (environments that hold the
built wheel and nothing but its dependencies, one per platform), checks every
dependency's licence against the policy (.github/python-license-policy.toml),
and writes their licence and NOTICE texts to FILE, which CD attaches to the
GitHub release.

The wheel and the sdist contain only MarketForge's own code: pip installs the
dependencies from their own distributions, each with its own licence files.
This file is for whoever redistributes an environment with MarketForge in it
(a container image, a frozen application), and the policy keeps a dependency
under a licence MarketForge cannot be used with from reaching a release.

It fails (a GitHub `::error::` annotation, exit 1) when a dependency's licence
is not allowed, is not an SPDX expression and has no policy entry, has changed
since its policy entry was reviewed, or when a dependency ships no licence text.
Standard library only.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import re
import sys
import tomllib
from collections.abc import Iterable
from dataclasses import dataclass
from email.message import Message
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / ".github" / "python-license-policy.toml"
PROJECT = "marketforge"

# Licence files of a distribution that declares none (older metadata than PEP 639).
_LICENSE_FILE = re.compile(r"(licen[cs]e|copying|notice|copyright)([-._ ].*)?", re.IGNORECASE)


class LicenseError(Exception):
    """A check failed; the message says why and how to fix it."""


# --------------------------------------------------------------------------- #
# SPDX licence expressions
# --------------------------------------------------------------------------- #

_TOKEN = re.compile(r"\s*(\(|\)|[A-Za-z0-9.+:-]+)")


def spdx_tokens(expression: str) -> list[str]:
    tokens, pos = [], 0
    expression = expression.strip()
    while pos < len(expression):
        match = _TOKEN.match(expression, pos)
        if not match:
            raise LicenseError(f"'{expression}' is not an SPDX licence expression")
        tokens.append(match.group(1))
        pos = match.end()
        while pos < len(expression) and expression[pos].isspace():
            pos += 1
    if not tokens:
        raise LicenseError("an empty licence is not an SPDX licence expression")
    return tokens


def spdx_allowed(expression: str, allowed: Iterable[str], exceptions: Iterable[str] = ()) -> bool:
    """Whether an SPDX expression can be satisfied with the allowed licences.

    `A OR B` needs one side, `A AND B` both, `A WITH E` needs A and the
    exception E. IDs and operators are matched without regard to case, as
    SPDX specifies. Raises LicenseError if the expression does not parse.
    """
    ids = {i.lower() for i in allowed}
    excs = {e.lower() for e in exceptions}
    tokens = spdx_tokens(expression)
    operators = {"and", "or", "with"}
    pos = 0

    def peek() -> str | None:
        return tokens[pos].lower() if pos < len(tokens) else None

    def take() -> str:
        nonlocal pos
        if pos >= len(tokens):
            raise LicenseError(f"'{expression}' ends too early for an SPDX expression")
        pos += 1
        return tokens[pos - 1]

    def atom() -> bool:
        token = take()
        if token == "(":
            value = either()
            if take() != ")":
                raise LicenseError(f"'{expression}' has an unclosed parenthesis")
            return value
        if token == ")" or token.lower() in operators:
            raise LicenseError(f"'{expression}' is not an SPDX licence expression")
        value = token.lower() in ids
        if peek() == "with":
            take()
            exception = take()
            if exception in "()" or exception.lower() in operators:
                raise LicenseError(f"'{expression}' has no exception after WITH")
            value = value and exception.lower() in excs
        return value

    def both() -> bool:
        value = atom()
        while peek() == "and":
            take()
            value = atom() and value
        return value

    def either() -> bool:
        value = both()
        while peek() == "or":
            take()
            value = both() or value
        return value

    result = either()
    if pos != len(tokens):
        raise LicenseError(f"'{expression}' is not an SPDX licence expression")
    return result


# --------------------------------------------------------------------------- #
# Distributions and policy
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Package:
    name: str
    version: str
    declared: str  # the licence as the distribution states it
    url: str
    texts: tuple[tuple[str, str], ...]  # (file name, contents)


@dataclass(frozen=True)
class Policy:
    allowed: frozenset[str]
    exceptions: frozenset[str]
    packages: dict[str, dict[str, object]]


def normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def declared_license(meta: Message) -> str:
    """The licence a distribution states: its PEP 639 expression, else the
    one-line `License` field, else its licence classifiers."""
    if expression := (meta.get("License-Expression") or "").strip():
        return expression
    field = (meta.get("License") or "").strip()
    if field and "\n" not in field:
        return field
    classifiers = [
        c.split("::")[-1].strip()
        for c in meta.get_all("Classifier") or []
        if c.startswith("License ::")
    ]
    if classifiers:
        return " AND ".join(classifiers)
    return field.splitlines()[0] if field else ""


def _url(meta: Message) -> str:
    urls = {}
    for entry in meta.get_all("Project-URL") or []:
        label, _, url = entry.partition(",")
        urls[label.strip().lower()] = url.strip()
    for label in ("source", "source code", "repository", "github", "homepage", "home"):
        if label in urls:
            return urls[label]
    return (meta.get("Home-page") or "").strip() or next(iter(urls.values()), "")


def clean_text(text: str) -> str:
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    return "\n".join(lines).strip("\n")


def license_texts(dist: importlib.metadata.Distribution) -> tuple[tuple[str, str], ...]:
    """The licence and NOTICE files of a distribution, as it declares them
    (PEP 639 `License-File`), else the licence-like files of its .dist-info."""
    texts = []
    for name in dist.metadata.get_all("License-File") or []:
        text = dist.read_text(f"licenses/{name}") or dist.read_text(name)
        if text and text.strip():
            texts.append((name, clean_text(text)))
    if not texts:
        for file in dist.files or []:
            if (
                len(file.parts) >= 2
                and file.parts[0].endswith(".dist-info")
                and _LICENSE_FILE.fullmatch(file.name)
            ):
                text = Path(file.locate()).read_text(encoding="utf-8", errors="replace")
                if text.strip():
                    texts.append(("/".join(file.parts[1:]), clean_text(text)))
    return tuple(texts)


def installed(paths: Iterable[Path]) -> tuple[str, list[Package]]:
    """(marketforge's version, its dependencies) installed under `paths`."""
    project_version = None
    packages: dict[tuple[str, str], Package] = {}
    for path in paths:
        if not path.is_dir():
            raise LicenseError(f"{path} is not a directory")
        for dist in importlib.metadata.distributions(path=[str(path)]):
            meta = dist.metadata
            name = meta["Name"]
            if normalize(name) == PROJECT:
                project_version = dist.version
                continue
            packages.setdefault(
                (normalize(name), dist.version),
                Package(
                    name, dist.version, declared_license(meta), _url(meta), license_texts(dist)
                ),
            )
    if project_version is None:
        raise LicenseError(
            f"no {PROJECT} distribution under {', '.join(map(str, paths))}: pass the "
            "site-packages of environments the wheel was installed into"
        )
    return project_version, sorted(packages.values(), key=lambda p: (normalize(p.name), p.version))


def load_policy(path: Path = POLICY) -> Policy:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return Policy(
        allowed=frozenset(data.get("allowed", [])),
        exceptions=frozenset(data.get("exceptions", [])),
        packages={normalize(k): v for k, v in data.get("packages", {}).items()},
    )


def resolve(package: Package, policy: Policy) -> str:
    """The SPDX licence the policy accepts for a package, or LicenseError."""
    entry = policy.packages.get(normalize(package.name), {})
    where = f"[packages.{normalize(package.name)}] in {POLICY.relative_to(ROOT)}"
    allowed = policy.allowed | set(entry.get("allow", []))  # type: ignore[arg-type]
    license = package.declared
    if entry:
        if entry.get("declared") != package.declared:
            raise LicenseError(
                f"{package.name} {package.version} declares the licence '{package.declared}', "
                f"but {where} was reviewed for '{entry.get('declared')}'. Read its licence "
                "files, then update or remove the entry"
            )
        license = str(entry.get("license", license))
    try:
        ok = spdx_allowed(license, allowed, policy.exceptions)
    except LicenseError:
        raise LicenseError(
            f"{package.name} {package.version} declares the licence '{package.declared}', "
            f"which is not an SPDX expression. Read its licence files and add {where} "
            f"with declared = '{package.declared}' and license = '<SPDX expression>'"
        ) from None
    if not ok:
        raise LicenseError(
            f"{package.name} {package.version} is under '{license}', which the policy does "
            f"not allow (allowed: {', '.join(sorted(allowed))}). If that is not the SPDX "
            f"identifier of its licence, read its licence files and give the right one with "
            f"declared = '{package.declared}' and license = '<SPDX expression>' in {where}. "
            "Otherwise it needs a decision: replace it, or allow it for this package only "
            "with allow = [...]"
        )
    if not package.texts:
        raise LicenseError(
            f"{package.name} {package.version} ships no licence text in its distribution, "
            "so the release cannot reproduce it"
        )
    return license


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #

RULE = "=" * 79


def render(version: str, packages: list[tuple[Package, str]], platforms: str) -> str:
    width = max((len(p.name) for p, _ in packages), default=4)
    out = [
        f"MarketForge {version}: third-party licences",
        RULE,
        "",
        "MarketForge's wheel and sdist contain only its own code, under the Apache",
        "License 2.0 (LICENSE and NOTICE in the distribution). They contain none of",
        "the packages below: pip installs those from their own distributions, each",
        "with its own licence files.",
        "",
        "This file reproduces the licence and NOTICE texts of MarketForge's runtime",
        f"dependencies as they were resolved when {version} was built ({platforms}),",
        "for whoever redistributes an environment with MarketForge in it. The",
        "versions you install may be newer; their own distributions are authoritative.",
        "",
        "Generated by .github/scripts/licenses.py; do not edit.",
        "",
        "",
        f"{'Package'.ljust(width)}  {'Version'.ljust(12)}  Licence",
        f"{'-' * width}  {'-' * 12}  {'-' * 7}",
    ]
    out += [f"{p.name.ljust(width)}  {p.version.ljust(12)}  {lic}" for p, lic in packages]
    for package, lic in packages:
        out += ["", "", RULE, f"{package.name} {package.version}", f"Licence: {lic}"]
        if lic != package.declared:
            out.append(f"Declared as: {package.declared}")
        if package.url:
            out.append(f"Source: {package.url}")
        out.append(RULE)
        for name, text in package.texts:
            out += ["", f"----- {name} -----", "", text]
    return "\n".join(out) + "\n"


def run(paths: list[Path], out: Path, platforms: str, policy: Policy) -> list[str]:
    """Check every dependency and write the report; return the errors."""
    version, packages = installed(paths)
    resolved, errors = [], []
    for package in packages:
        try:
            resolved.append((package, resolve(package, policy)))
        except LicenseError as e:
            errors.append(str(e))
    present = {normalize(p.name) for p in packages}
    for name in sorted(set(policy.packages) - present):
        print(
            f"::warning title=licences::{name} is not a dependency any more: remove "
            f"[packages.{name}] from {POLICY.relative_to(ROOT)}"
        )
    if not errors:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(render(version, resolved, platforms), encoding="utf-8")
        for package, lic in resolved:
            print(f"ok  {package.name} {package.version}  {lic}")
        print(f"Wrote {out} ({len(resolved)} packages)")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--path",
        type=Path,
        action="append",
        required=True,
        help="site-packages holding the wheel and its dependencies; repeat per platform",
    )
    parser.add_argument("--out", type=Path, required=True, help="the report to write")
    parser.add_argument(
        "--platforms",
        default="Linux, macOS and Windows",
        help="the platforms the paths were resolved for, as the report states them",
    )
    args = parser.parse_args(argv)
    try:
        errors = run(args.path, args.out, args.platforms, load_policy())
    except LicenseError as e:
        errors = [str(e)]
    for error in errors:
        print(f"::error title=Third-party licences::{error}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
