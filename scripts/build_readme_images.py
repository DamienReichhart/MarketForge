# MarketForge
# Copyright (c) 2026 REICHHART Damien
#
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file in the project root for full license information.

"""
Build the README's images from real MarketForge output and the brand tokens.

Every chart is drawn from the samples the website is built from
(website/src/samples/, written by website/scripts/hero_sample.py and
landing_samples.py), every colour comes from docs/brand/tokens.json, and every
label is outlined in DM Sans or DM Mono, so the SVGs look the same on GitHub
and PyPI with no fonts installed. Run it after regenerating the samples or
changing the tokens:

    pip install fonttools brotli uharfbuzz
    (cd website && npm ci)
    python scripts/build_readme_images.py

Writes docs/readme/{hero,regimes,seeds}-{dark,light}.svg.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_brand_assets import TOKENS, svg, text_path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "readme"
SAMPLES = ROOT / "website" / "src" / "samples"

REGIMES = ("trend_up", "trend_down", "range", "high_volatility", "crash")
LABELS = {
    "trend_up": "Trend up",
    "trend_down": "Trend down",
    "range": "Range",
    "high_volatility": "High volatility",
    "crash": "Crash",
}
# Regime bands behind candles: the regime fills, faint enough for the candles
# to stay readable (docs/brand/README.md, Charts: 10 to 24 percent).
BAND_OPACITY = {
    "trend_up": 0.14,
    "trend_down": 0.22,
    "range": 0.10,
    "high_volatility": 0.14,
    "crash": 0.24,
}

W = 1200


def r(v: float) -> str:
    return f"{v:.1f}".rstrip("0").rstrip(".")


def ui(mode: str) -> dict[str, str]:
    return TOKENS[mode]


def fills(mode: str) -> dict[str, dict[str, str]]:
    return TOKENS["regimes"][mode]


def label(
    text: str,
    x: float,
    y: float,
    fill: str,
    *,
    size: float,
    weight: int = 500,
    kind: str = "sans",
    anchor: str = "start",
) -> str:
    """Outlined text with its baseline at y; anchor 'end' right-aligns it on x."""
    d, width = text_path(text, kind=kind, size=size, weight=weight)
    if anchor == "end":
        x -= width
    elif anchor == "middle":
        x -= width / 2
    return f'<path transform="translate({r(x)} {r(y)})" d="{d}" fill="{fill}"/>'


def panel(mode: str, width: float, height: float, x: float = 0, y: float = 0) -> str:
    c = ui(mode)
    return (
        f'<rect x="{r(x + 0.5)}" y="{r(y + 0.5)}" width="{r(width - 1)}" height="{r(height - 1)}" rx="10" '
        f'fill="{c["panel"]}" stroke="{c["line_strong"]}"/>'
    )


def candles(
    rows: list[list],
    x0: float,
    y0: float,
    width: float,
    height: float,
    mode: str,
    *,
    volume: float = 0,
) -> str:
    """Candles, with volume bars under them when `volume` (their band's height) is set."""
    c = ui(mode)
    price_h = height - volume - (16 if volume else 0)
    hi = max(row[2] for row in rows)
    lo = min(row[3] for row in rows)
    pad = (hi - lo) * 0.06 or 1
    y = lambda p: y0 + price_h - (p - lo + pad) / (hi - lo + 2 * pad) * price_h  # noqa: E731
    step = width / len(rows)
    body = max(1.0, step * 0.6)
    vmax = max(row[5] for row in rows) or 1
    out = []
    for i, row in enumerate(rows):
        colour = c["up"] if row[4] >= row[1] else c["down"]
        cx = x0 + i * step + step / 2
        top, bottom = sorted((y(row[1]), y(row[4])))
        out.append(
            f'<line x1="{r(cx)}" x2="{r(cx)}" y1="{r(y(row[2]))}" y2="{r(y(row[3]))}" stroke="{colour}" stroke-width="1"/>'
        )
        out.append(
            f'<rect x="{r(cx - body / 2)}" y="{r(top)}" width="{r(body)}" height="{r(max(1, bottom - top))}" fill="{colour}"/>'
        )
        if volume:
            vh = row[5] / vmax * volume
            out.append(
                f'<rect x="{r(cx - body / 2)}" y="{r(y0 + height - vh)}" width="{r(body)}" height="{r(vh)}" '
                f'fill="{colour}" fill-opacity="0.32"/>'
            )
    return "".join(out)


def legend(x: float, y: float, mode: str) -> str:
    c = ui(mode)
    out = []
    for key in REGIMES:
        out.append(
            f'<rect x="{r(x)}" y="{r(y - 11)}" width="12" height="12" rx="2" fill="{fills(mode)[key]["fill"]}"/>'
        )
        d, width = text_path(LABELS[key], size=15, weight=450)
        out.append(f'<path transform="translate({r(x + 20)} {r(y)})" d="{d}" fill="{c["muted"]}"/>')
        x += 20 + width + 28
    return "".join(out)


def hero(mode: str) -> str:
    """The landing page's hero chart: ten days of BTCUSD, shaded by regime."""
    sample = json.loads((SAMPLES / "hero-sample.json").read_text())
    rows = sample["candles"]
    c = ui(mode)
    H = 560
    px, py, pw, ph = 32, 92, W - 64 - 96, 380
    step = pw / len(rows)
    out = [panel(mode, W, H)]
    out.append(label(sample["instrument"], 32, 50, c["text"], size=22, weight=650))
    symbol_w = text_path(sample["instrument"], size=22, weight=650)[1]
    meta = f"{sample['timeframe']} candles, {sample['market']}, seed {sample['seed']}"
    out.append(label(meta, 32 + symbol_w + 16, 50, c["muted"], size=17, kind="mono"))
    out.append(
        label(
            f"marketforge {sample['version']}",
            W - 32,
            50,
            c["muted"],
            size=17,
            kind="mono",
            anchor="end",
        )
    )
    out.append(f'<line x1="0" x2="{W}" y1="72.5" y2="72.5" stroke="{c["line"]}"/>')
    # Regime bands.
    start = 0
    for i in range(1, len(rows) + 1):
        if i == len(rows) or rows[i][7] != rows[start][7]:
            key = rows[start][7]
            out.append(
                f'<rect x="{r(px + start * step)}" y="{py}" width="{r((i - start) * step)}" height="{ph}" '
                f'fill="{fills(mode)[key]["fill"]}" fill-opacity="{BAND_OPACITY[key]}"/>'
            )
            start = i
    # Price gridlines and their labels on the right.
    hi = max(row[2] for row in rows)
    lo = min(row[3] for row in rows)
    price_h = ph - 70 - 16
    pad = (hi - lo) * 0.06
    stepp = 2000
    for level in range(math.ceil(lo / stepp) * stepp, int(hi) + 1, stepp):
        gy = py + price_h - (level - lo + pad) / (hi - lo + 2 * pad) * price_h
        out.append(
            f'<line x1="{px}" x2="{px + pw}" y1="{r(gy)}" y2="{r(gy)}" stroke="{c["line"]}"/>'
        )
        out.append(label(f"{level:,}", px + pw + 14, gy + 6, c["muted"], size=15, kind="mono"))
    out.append(candles(rows, px, py, pw, ph, mode, volume=70))
    out.append(legend(32, H - 30, mode))
    title = f"{sample['instrument']} {sample['timeframe']} candles generated by MarketForge with seed {sample['seed']}, shaded by market regime"
    return svg(W, H, "".join(out), title=title)


def regimes(mode: str) -> str:
    """The five regimes, in the order of the mark's bands, each with its longest run of BTCUSD."""
    runs = json.loads((SAMPLES / "landing-samples.json").read_text())["regimes"]["runs"]
    c = ui(mode)
    H = 400
    gap = 16
    cw = (W - 4 * gap) / 5
    out = []
    for n, key in enumerate(REGIMES):
        x = n * (cw + gap)
        fill = fills(mode)[key]
        out.append(
            f'<rect x="{r(x)}" y="0" width="{r(cw)}" height="{H}" rx="8" fill="{c["panel"]}"/>'
        )
        out.append(
            f'<rect x="{r(x)}" y="0" width="{r(cw)}" height="{H}" rx="8" fill="{fill["fill"]}" fill-opacity="0.14"/>'
        )
        out.append(f'<rect x="{r(x)}" y="0" width="{r(cw)}" height="6" fill="{fill["fill"]}"/>')
        out.append(label(LABELS[key], x + 20, 48, fill["text"], size=22, weight=650))
        out.append(label(key, x + 20, 76, c["muted"], size=15, kind="mono"))
        out.append(candles(runs[key], x + 14, 110, cw - 28, H - 140, mode))
    return svg(
        W,
        H,
        "".join(out),
        title="The five regimes MarketForge labels, each with a run of BTCUSD candles generated in it",
    )


def seeds(mode: str) -> str:
    """One path of BTCUSD against the same six months under 32 seeds."""
    paths = json.loads((SAMPLES / "landing-samples.json").read_text())["paths"]
    lines, drawdowns = paths["paths"], paths["max_drawdown_pct"]
    c = ui(mode)
    H = 470
    gap = 24
    pw = (W - gap) / 2
    lo = math.log(min(min(p) for p in lines))
    hi = math.log(max(max(p) for p in lines))
    ch = 270

    def chart(x0: float, which: list[int]) -> str:
        cw = pw - 48 - 56
        y = lambda v: 96 + ch - (math.log(v) - lo) / (hi - lo) * ch  # noqa: E731
        out = []
        for level in (12.5, 25, 50, 100, 200, 400, 800):
            if lo < math.log(level) < hi:
                dash = ' stroke-dasharray="5 5"' if level == 100 else ""
                colour = c["line_strong"] if level == 100 else c["line"]
                out.append(
                    f'<line x1="{r(x0 + 24)}" x2="{r(x0 + 24 + cw)}" y1="{r(y(level))}" y2="{r(y(level))}" stroke="{colour}"{dash}/>'
                )
                out.append(
                    label(
                        f"{level:g}",
                        x0 + 24 + cw + 12,
                        y(level) + 5,
                        c["muted"],
                        size=14,
                        kind="mono",
                    )
                )
        n = len(lines[0]) - 1
        for i in which:
            d = " ".join(
                f"{'M' if k == 0 else 'L'}{r(x0 + 24 + k / n * cw)} {r(y(v))}"
                for k, v in enumerate(lines[i])
            )
            if i == 0:
                out.append(
                    f'<path d="{d}" stroke="{c["text"]}" stroke-width="2.5" stroke-linejoin="round"/>'
                )
            else:
                out.append(
                    f'<path d="{d}" stroke="{c["muted"]}" stroke-opacity="0.45" stroke-width="1.2" stroke-linejoin="round"/>'
                )
        return "".join(out)

    out = [panel(mode, pw, H), panel(mode, pw, H, x=pw + gap)]
    out.append(label("One path", 24, 52, c["text"], size=22, weight=650))
    out.append(chart(0, [0]))
    out.append(
        f'<line x1="24" x2="{r(pw - 24)}" y1="{H - 72}.5" y2="{H - 72}.5" stroke="{c["line"]}"/>'
    )
    out.append(label("Worst drawdown", 24, H - 32, c["muted"], size=17))
    out.append(
        label(
            f"{round(drawdowns[0])}%", pw - 24, H - 30, c["text"], size=28, weight=650, anchor="end"
        )
    )
    x1 = pw + gap
    out.append(label(f"{len(lines)} seeds", x1 + 24, 52, c["text"], size=22, weight=650))
    out.append(chart(x1, [*range(1, len(lines)), 0]))
    out.append(
        f'<line x1="{r(x1 + 24)}" x2="{r(x1 + pw - 24)}" y1="{H - 72}.5" y2="{H - 72}.5" stroke="{c["line"]}"/>'
    )
    out.append(label("Worst drawdown", x1 + 24, H - 32, c["muted"], size=17))
    spread = f"{round(min(drawdowns))}% to {round(max(drawdowns))}%"
    out.append(label(spread, x1 + pw - 24, H - 30, c["text"], size=28, weight=650, anchor="end"))
    title = f"Buy-and-hold BTCUSD over six months: one seed, then {len(lines)} seeds, worst drawdown from {spread}"
    return svg(W, H, "".join(out), title=title)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, build in (("hero", hero), ("regimes", regimes), ("seeds", seeds)):
        for mode in ("dark", "light"):
            path = OUT / f"{name}-{mode}.svg"
            path.write_text(build(mode))
            print(f"wrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
