# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the GNU Affero General Public License v3.0 or later.
# See the LICENSE file in the project root for full license information.

"""
Build every brand asset (logos, favicon, social images) from the tokens in
docs/brand/tokens.json.

The wordmark is converted to outlines, so the SVGs render the same everywhere
without the fonts installed. Run it after changing the tokens or the geometry:

    pip install fonttools brotli uharfbuzz
    (cd website && npm ci)
    python scripts/build_brand_assets.py

Writes docs/brand/assets/ (the source of truth) and the files the website
serves directly: website/public/ and website/src/assets/logo.svg.
"""

from __future__ import annotations

import io
import json
import shutil
import subprocess
from pathlib import Path

import uharfbuzz as hb
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[1]
BRAND = ROOT / "docs" / "brand"
ASSETS = BRAND / "assets"
SITE_PUBLIC = ROOT / "website" / "public"
SITE_LOGO = ROOT / "website" / "src" / "assets" / "logo.svg"
FONTS = ROOT / "website" / "node_modules"

TOKENS = json.loads((BRAND / "tokens.json").read_text())
REGIMES = ["trend_up", "trend_down", "range", "high_volatility", "crash"]

# ---------------------------------------------------------------- geometry
# The mark lives in a 48 x 48 box: five regime bands, and one price path that
# starts in the crash band and climbs to a trend. A mask cuts a gap around the
# path, so the mark stays correct on any background, including transparent.
BAND_X, BAND_W, BAND_H, BAND_GAP, BAND_Y0 = 4, 40, 7, 2.5, 1.5
PATH = "M4 41 L12 33 L19 37 L27 21 L33 25 L44 6"
PATH_W, GAP_W = 3.2, 7.2

# The small mark (favicon, 16 to 24 px): three bands and a heavier path.
SMALL_BANDS = [("trend_up", 2), ("high_volatility", 18), ("crash", 34)]
SMALL_H = 12
SMALL_PATH = "M5 41 L18 31 L26 35 L43 8"
SMALL_PATH_W, SMALL_GAP_W = 4.6, 9.4

_uid = iter(range(1, 10_000))


def _palette(mode: str) -> dict[str, str]:
    return TOKENS["marks"][mode]


def mark_body(mode: str, *, small: bool = False, mono: str | None = None) -> str:
    """SVG elements of the mark in a 48 x 48 box. `mono` is a single fill colour."""
    pal = _palette(mode)
    mid = f"k{next(_uid)}"
    line = mono or pal["line"]
    path, gap, width = (SMALL_PATH, SMALL_GAP_W, SMALL_PATH_W) if small else (PATH, GAP_W, PATH_W)
    if small:
        bands = [
            (name, BAND_X - 2, y, BAND_W + 4, SMALL_H, mono or pal[name]) for name, y in SMALL_BANDS
        ]
    elif mono:
        # One colour cannot tell five bands apart, so each band becomes a rule.
        bands = [
            (name, BAND_X, BAND_Y0 + i * (BAND_H + BAND_GAP) + 2.3, BAND_W, 2.4, mono)
            for i, name in enumerate(REGIMES)
        ]
    else:
        bands = [
            (name, BAND_X, BAND_Y0 + i * (BAND_H + BAND_GAP), BAND_W, BAND_H, pal[name])
            for i, name in enumerate(REGIMES)
        ]
    rects = "".join(
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{1 if not small else 1.6}" fill="{c}"/>'
        for _, x, y, w, h, c in bands
    )
    return (
        f'<mask id="{mid}" maskUnits="userSpaceOnUse" x="0" y="0" width="48" height="48">'
        f'<rect width="48" height="48" fill="#fff"/>'
        f'<path d="{path}" fill="none" stroke="#000" stroke-width="{gap}" '
        f'stroke-linecap="round" stroke-linejoin="round"/></mask>'
        f'<g mask="url(#{mid})">{rects}</g>'
        f'<path d="{path}" fill="none" stroke="{line}" stroke-width="{width}" '
        f'stroke-linecap="round" stroke-linejoin="round"/>'
    )


def svg(width: float, height: float, body: str, view: str | None = None, title: str = "") -> str:
    view = view or f"0 0 {width:g} {height:g}"
    label = f' role="img" aria-label="{title}"' if title else ' aria-hidden="true"'
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:g}" height="{height:g}" '
        f'viewBox="{view}" fill="none"{label}>{body}</svg>\n'
    )


# -------------------------------------------------------------------- type
def _load(path: Path) -> bytes:
    buf = io.BytesIO()
    font = TTFont(path)
    font.flavor = None
    font.save(buf)
    return buf.getvalue()


_FONT_CACHE: dict[str, tuple[hb.Font, int]] = {}


def _font(kind: str) -> tuple[hb.Font, int]:
    if kind not in _FONT_CACHE:
        if kind == "sans":
            path = FONTS / "@fontsource-variable/dm-sans/files/dm-sans-latin-wght-normal.woff2"
        else:
            path = FONTS / "@fontsource/dm-mono/files/dm-mono-latin-400-normal.woff2"
        face = hb.Face(hb.Blob(_load(path)))
        _FONT_CACHE[kind] = (hb.Font(face), face.upem)
    return _FONT_CACHE[kind]


def text_path(
    text: str, *, kind: str = "sans", size: float, weight: int = 500, tracking: float = 0.0
) -> tuple[str, float]:
    """Outline `text` as one SVG path with its baseline at y=0. Returns (d, advance width)."""
    font, upem = _font(kind)
    if kind == "sans":
        font.set_variations({"wght": weight})
    buf = hb.Buffer()
    buf.add_str(text)
    buf.guess_segment_properties()
    hb.shape(font, buf, {"kern": True, "liga": False})
    scale = size / upem
    x = 0.0
    parts: list[str] = []
    for info, pos in zip(buf.glyph_infos, buf.glyph_positions, strict=True):
        pen = SVGPathPen(None, ntos=lambda v: f"{v:.2f}".rstrip("0").rstrip("."))
        # Font units are y-up: flip y, scale to the requested size and place the glyph.
        font.draw_glyph_with_pen(info.codepoint, TransformPen(pen, (scale, 0, 0, -scale, x, 0)))
        if d := pen.getCommands():
            parts.append(d)
        x += pos.x_advance * scale + tracking * size
    return " ".join(parts), x - tracking * size


def wordmark(mode: str, size: float) -> tuple[str, float]:
    """'market' in medium weight and 'forge' in bold, as outlines. Returns (svg body, width)."""
    ink = _palette(mode)["line"]
    d1, w1 = text_path("market", size=size, weight=500, tracking=-0.02)
    d2, w2 = text_path("forge", size=size, weight=700, tracking=-0.02)
    gap = size * -0.02
    body = (
        f'<path d="{d1}" fill="{ink}"/>'
        f'<path transform="translate({w1 + gap:.2f} 0)" d="{d2}" fill="{ink}"/>'
    )
    return body, w1 + gap + w2


def lockup(mode: str) -> str:
    """Horizontal lockup: mark, then wordmark, vertically centred on the mark."""
    size = 34.0
    body, width = wordmark(mode, size)
    # DM Sans x-height centre sits about 0.26 em above the baseline.
    baseline = 24 + size * 0.255
    gap = 12
    total = 48 + gap + width
    inner = mark_body(mode) + f'<g transform="translate({48 + gap} {baseline:.2f})">{body}</g>'
    return svg(round(total, 1), 48, inner, title="MarketForge")


def stacked(mode: str) -> str:
    """Mark above wordmark, centred. For square and narrow placements."""
    size = 30.0
    body, width = wordmark(mode, size)
    w = max(width, 96)
    inner = (
        f'<g transform="translate({(w - 72) / 2:.2f} 0) scale(1.5)">{mark_body(mode)}</g>'
        f'<g transform="translate({(w - width) / 2:.2f} {72 + 14 + size * 0.74:.2f})">{body}</g>'
    )
    return svg(round(w, 1), round(72 + 14 + size, 1), inner, title="MarketForge")


def tile(*, small: bool, radius: float = 11) -> str:
    """The app icon: the mark on an ink tile. Used for the favicon and the docs header."""
    ink = TOKENS["dark"]["ground"]
    if small:
        # Fills the tile: at 16 px every pixel counts.
        inner = f'<g transform="translate(5.5 5.5) scale(0.77)">{mark_body("dark", small=True)}</g>'
    else:
        inner = f'<g transform="translate(7 7) scale(0.708)">{mark_body("dark")}</g>'
    body = f'<rect width="48" height="48" rx="{radius}" fill="{ink}"/>{inner}'
    return svg(48, 48, body, title="MarketForge")


def regime_strip(width: float, height: float, y: float = 0, x: float = 0) -> str:
    """The brand's timeline motif: contiguous regime runs. Widths are fixed for stability."""
    pal = _palette("dark")
    runs = [
        ("trend_up", 17),
        ("range", 11),
        ("high_volatility", 7),
        ("crash", 4),
        ("trend_down", 14),
        ("range", 13),
        ("trend_up", 24),
        ("high_volatility", 5),
        ("range", 5),
    ]
    total = sum(w for _, w in runs)
    out, cx = [], x
    for name, w in runs:
        rw = width * w / total
        out.append(
            f'<rect x="{cx:.2f}" y="{y}" width="{rw + 0.5:.2f}" height="{height}" fill="{pal[name]}"/>'
        )
        cx += rw
    return "".join(out)


def social(width: int, height: int, *, big: bool) -> str:
    """Open Graph (1200x630) and GitHub social preview (1280x640) cards."""
    d = TOKENS["dark"]
    pad = 80
    inner = [f'<rect width="{width}" height="{height}" fill="{d["ground"]}"/>']
    mark_size = 120
    inner.append(
        f'<g transform="translate({pad} {pad}) scale({mark_size / 48})">{mark_body("dark")}</g>'
    )
    wm_size = 76 if big else 70
    body, _ = wordmark("dark", wm_size)
    inner.append(
        f'<g transform="translate({pad + mark_size + 28} {pad + mark_size / 2 + wm_size * 0.255:.1f})">{body}</g>'
    )
    lines = ["Synthetic market data for training", "AI trading models and testing", "backtesters."]
    ty = 330
    for line in lines:
        dpath, _ = text_path(line, size=46, weight=500, tracking=-0.015)
        inner.append(
            f'<g transform="translate({pad} {ty})"><path d="{dpath}" fill="{d["text"]}"/></g>'
        )
        ty += 58
    cmd, _ = text_path(
        "$ marketforge generate --with-regime --seed 42", kind="mono", size=24, tracking=0
    )
    inner.append(
        f'<g transform="translate({pad} {height - 112})"><path d="{cmd}" fill="{d["muted"]}"/></g>'
    )
    inner.append(regime_strip(width - 2 * pad, 14, y=height - 80, x=pad))
    return svg(width, height, "".join(inner), title="MarketForge")


# ------------------------------------------------------------------ output
def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def rasterize(jobs: list[tuple[Path, Path, int]]) -> None:
    """SVG -> PNG with sharp (already a dependency of the website)."""
    payload = json.dumps([[str(s), str(t), w] for s, t, w in jobs])
    script = (
        "const sharp=require('sharp');const jobs=JSON.parse(process.argv[1]);"
        "Promise.all(jobs.map(([s,t,w])=>sharp(s,{density:384}).resize(w).png().toFile(t)))"
        ".catch(e=>{console.error(e);process.exit(1)});"
    )
    subprocess.run(
        ["node", "-e", script, payload],
        cwd=ROOT / "website",
        check=True,
    )


def main() -> None:
    a = ASSETS
    write(a / "mark-dark.svg", svg(48, 48, mark_body("dark"), title="MarketForge"))
    write(a / "mark-light.svg", svg(48, 48, mark_body("light"), title="MarketForge"))
    write(
        a / "mark-small-dark.svg", svg(48, 48, mark_body("dark", small=True), title="MarketForge")
    )
    write(
        a / "mark-small-light.svg", svg(48, 48, mark_body("light", small=True), title="MarketForge")
    )
    write(
        a / "mark-mono-black.svg",
        svg(48, 48, mark_body("light", mono="#000000"), title="MarketForge"),
    )
    write(
        a / "mark-mono-white.svg",
        svg(48, 48, mark_body("dark", mono="#FFFFFF"), title="MarketForge"),
    )
    write(a / "lockup-dark.svg", lockup("dark"))
    write(a / "lockup-light.svg", lockup("light"))
    write(a / "stacked-dark.svg", stacked("dark"))
    write(a / "stacked-light.svg", stacked("light"))
    write(a / "icon.svg", tile(small=False))
    write(a / "favicon.svg", tile(small=True, radius=10))
    write(a / "og-image.svg", social(1200, 630, big=False))
    write(a / "github-social.svg", social(1280, 640, big=True))

    rasterize(
        [
            (a / "icon.svg", a / "icon-512.png", 512),
            (a / "icon.svg", a / "icon-192.png", 192),
            (a / "icon.svg", a / "apple-touch-icon.png", 180),
            (a / "favicon.svg", a / "favicon-32.png", 32),
            (a / "og-image.svg", a / "og-image.png", 1200),
            (a / "github-social.svg", a / "github-social.png", 1280),
        ]
    )

    # Files the website serves or imports directly.
    SITE_PUBLIC.mkdir(parents=True, exist_ok=True)
    shutil.copy(a / "favicon.svg", SITE_PUBLIC / "favicon.svg")
    shutil.copy(a / "apple-touch-icon.png", SITE_PUBLIC / "apple-touch-icon.png")
    shutil.copy(a / "og-image.png", SITE_PUBLIC / "og-image.png")
    shutil.copy(a / "icon.svg", SITE_LOGO)
    print(f"wrote {len(list(a.iterdir()))} assets to {a.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
