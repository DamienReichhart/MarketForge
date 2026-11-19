"""Tests that the brand tokens, the website theme and the shipped assets agree."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BRAND = ROOT / "docs" / "brand"
THEME = ROOT / "website" / "src" / "styles" / "theme.css"
if not THEME.is_file():  # running from the sdist, which ships tests/ but not the website
    pytest.skip("website is not part of the sdist", allow_module_level=True)

TOKENS = json.loads((BRAND / "tokens.json").read_text())
CSS = THEME.read_text()

# Token name in tokens.json -> CSS custom properties it must set to the same value.
INTERFACE = {
    "ground": ["--mf-bg", "--sl-color-black"],
    "panel": ["--mf-panel"],
    "raised": ["--mf-raised"],
    "line": ["--mf-line"],
    "line_strong": ["--mf-line-strong"],
    "text": ["--mf-text", "--sl-color-white"],
    "muted": ["--mf-muted"],
    "accent": ["--sl-color-accent"],
    "accent_low": ["--sl-color-accent-low"],
    "accent_high": ["--sl-color-accent-high"],
    "up": ["--mf-up"],
    "down": ["--mf-down"],
}
REGIME_CSS = {
    "trend_up": "trend-up",
    "trend_down": "trend-down",
    "range": "range",
    "high_volatility": "high-vol",
    "crash": "crash",
}


def _block(selector: str) -> dict[str, str]:
    """Custom properties declared by the rule with exactly this selector."""
    match = re.search(re.escape(selector) + r"\s*\{(.*?)\n\}", CSS, re.S)
    assert match, f"no {selector} rule in theme.css"
    return {
        name: value.strip().lower()
        for name, value in re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", match.group(1))
    }


THEMES = {"dark": _block(":root"), "light": _block(":root[data-theme='light']")}


@pytest.mark.parametrize("mode", ["dark", "light"])
def test_interface_tokens_match_theme(mode):
    css = THEMES[mode]
    for token, names in INTERFACE.items():
        expected = TOKENS[mode][token].lower()
        for name in names:
            assert css[name] == expected, (
                f"{mode} {name}: theme.css has {css[name]}, tokens.json {expected}"
            )


@pytest.mark.parametrize("mode", ["dark", "light"])
def test_regime_tokens_match_theme(mode):
    css = THEMES[mode]
    for regime, slug in REGIME_CSS.items():
        for kind, suffix in (("fill", ""), ("text", "-text")):
            name = f"--mf-regime-{slug}{suffix}"
            expected = TOKENS["regimes"][mode][regime][kind].lower()
            assert css[name] == expected, f"{mode} {name}: {css[name]} != {expected}"


@pytest.mark.parametrize("mode", ["dark", "light"])
def test_mark_colours_are_the_regime_fills(mode):
    """The logo and the chart legend must use the same colours."""
    for regime in REGIME_CSS:
        assert TOKENS["marks"][mode][regime] == TOKENS["regimes"][mode][regime]["fill"]


def test_brand_never_uses_candle_direction_colours_for_regimes():
    directions = {TOKENS[m][k].lower() for m in ("dark", "light") for k in ("up", "down")}
    for mode in ("dark", "light"):
        for values in TOKENS["regimes"][mode].values():
            assert values["fill"].lower() not in directions
            assert values["text"].lower() not in directions


def test_website_serves_the_canonical_favicon_and_logo():
    assets = BRAND / "assets"
    site = ROOT / "website"
    assert (site / "public" / "favicon.svg").read_bytes() == (assets / "favicon.svg").read_bytes()
    assert (site / "src" / "assets" / "logo.svg").read_bytes() == (assets / "icon.svg").read_bytes()
    for name in ("apple-touch-icon.png", "og-image.png"):
        assert (site / "public" / name).read_bytes() == (assets / name).read_bytes()


def test_every_asset_the_guidelines_link_exists():
    guidelines = (BRAND / "README.md").read_text()
    linked = set(re.findall(r"""(?:\]\(|src(?:set)?=")assets/([\w.-]+\.(?:svg|png))""", guidelines))
    assert linked, "the guidelines link no assets"
    for name in linked:
        assert (BRAND / "assets" / name).is_file(), (
            f"docs/brand/README.md links missing assets/{name}"
        )


def test_every_asset_is_documented():
    guidelines = (BRAND / "README.md").read_text()
    for path in (BRAND / "assets").iterdir():
        assert path.name in guidelines, f"{path.name} is not described in docs/brand/README.md"


def _token_colours() -> set[str]:
    colours: set[str] = set()

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for value in node.values():
                walk(value)
        elif isinstance(node, str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", node):
            colours.add(node.upper())

    walk(TOKENS)
    return colours


README_IMAGES = ROOT / "docs" / "readme"


def test_readme_images_use_only_brand_colours():
    colours = _token_colours()
    images = sorted(README_IMAGES.glob("*.svg"))
    assert images, "docs/readme/ holds no images"
    for path in images:
        used = {c.upper() for c in re.findall(r"#[0-9A-Fa-f]{6}\b", path.read_text())}
        stray = used - colours
        assert not stray, f"{path.name} uses colours that are not brand tokens: {sorted(stray)}"


def test_every_readme_image_is_shown_in_both_themes():
    readme = (ROOT / "README.md").read_text()
    for path in README_IMAGES.glob("*.svg"):
        assert f"docs/readme/{path.name}" in readme, (
            f"README.md does not show docs/readme/{path.name}"
        )
