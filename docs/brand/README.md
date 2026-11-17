# MarketForge brand

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/lockup-dark.svg">
  <img alt="MarketForge" src="assets/lockup-light.svg" height="64">
</picture>

The identity is called **Regimes**. MarketForge's differentiator is that every
candle can carry the hidden market regime that produced it, so the brand is
that label made visible: five bands, one per regime, crossed by a single price
path that starts in a crash and climbs into a trend. The colours of the mark
are the colours of the product's legend, so the logo and the charts are one
system.

Everything here is generated from [`tokens.json`](tokens.json) by
[`scripts/build_brand_assets.py`](../../scripts/build_brand_assets.py). Edit the
tokens, not the SVGs.

## The mark

Five bands in a 48 × 48 box, top to bottom: **trend up, trend down, range, high
volatility, crash**. The path is cut out of the bands with a mask, so the mark
has a clean gap around the line and works on any background, including
transparent ones.

| Variant | File | Use |
| --- | --- | --- |
| Full mark, for dark grounds | [`mark-dark.svg`](assets/mark-dark.svg) | Default. 24 px and up. |
| Full mark, for light grounds | [`mark-light.svg`](assets/mark-light.svg) | Same mark with the light-theme regime colours and an ink path. |
| Small mark | [`mark-small-dark.svg`](assets/mark-small-dark.svg), [`mark-small-light.svg`](assets/mark-small-light.svg) | 16 to 24 px. Three bands (trend up, high volatility, crash) and a heavier path. |
| Mono | [`mark-mono-black.svg`](assets/mark-mono-black.svg), [`mark-mono-white.svg`](assets/mark-mono-white.svg) | One colour only: print, stamps, embossing, anything that cannot show five colours. The bands become rules. |
| App icon | [`icon.svg`](assets/icon.svg), [`icon-192.png`](assets/icon-192.png), [`icon-512.png`](assets/icon-512.png), [`apple-touch-icon.png`](assets/apple-touch-icon.png) | Mark on an ink tile with rounded corners. Docs header, app and home-screen icons. |
| Favicon | [`favicon.svg`](assets/favicon.svg), [`favicon-32.png`](assets/favicon-32.png) | Tile with the small mark. Browser tabs. |

Use the small mark whenever the logo is shown below 24 px. The full mark's five
bands turn to mush at that size.

### Lockups

| File | Use |
| --- | --- |
| [`lockup-dark.svg`](assets/lockup-dark.svg), [`lockup-light.svg`](assets/lockup-light.svg) | Mark left of the wordmark. The default for headers, slides and the README. Never narrower than 120 px. |
| [`stacked-dark.svg`](assets/stacked-dark.svg), [`stacked-light.svg`](assets/stacked-light.svg) | Mark above the wordmark. Square and narrow placements. |
| [`og-image.png`](assets/og-image.png), [`og-image.svg`](assets/og-image.svg) | 1200 × 630 link preview (Open Graph, Twitter). |
| [`github-social.png`](assets/github-social.png), [`github-social.svg`](assets/github-social.svg) | 1280 × 640 repository social preview. |

The wordmark is outlined in every file, so nothing here needs the fonts
installed.

### Clear space and size

- Keep clear space of a quarter of the mark's height on every side.
- Full mark: 24 px minimum. Small mark: 16 px minimum. Lockup: 120 px wide minimum.
- Place the mark on the ink or white ground it was drawn for. On anything else
  (a photo, a coloured block) use a mono variant.

### Do not

- Recolour, reorder, add or remove bands. The order is part of the meaning.
- Use the up/down greens and reds. They mean candle direction, nothing else.
- Add gradients, shadows, outlines or glows.
- Rotate, stretch or crop the mark, or put the path outside the bands.
- Set the wordmark in another typeface, in capitals or with spaces.

## The name in text

The logo is lowercase: **market**forge. In prose, write **MarketForge**, one
word with two capitals. Never "Market Forge", "marketforge" in a sentence, or
"MarketForge™" without a registered mark. The Python package and the command
are `marketforge`, in code font.

## Colour

Three families that never mix. The point of the system is that a colour tells
you which kind of thing you are looking at.

1. **Ink and amber** (identity and interface). Ink grounds, one amber accent.
2. **Regime colours** (the state of the market). Only for the five regimes.
3. **Up and down** (the direction of a candle). Only for candles and price
   change. Never a brand, button or status colour.

### Interface

| Token | Dark | Light | Role |
| --- | --- | --- | --- |
| Ground | `#12161B` | `#FFFFFF` | Page background |
| Panel | `#171C22` | `#F5F7F8` | Raised surfaces, code blocks |
| Raised | `#1D242B` | `#ECEFF1` | Hover and nested panels |
| Line | `#262D35` | `#E1E5E8` | Hairlines |
| Line strong | `#323B44` | `#CBD1D6` | Borders that must be seen |
| Text | `#E9EDF1` | `#12161B` | Body and headings |
| Muted | `#8E99A4` | `#58626C` | Secondary text, 6:1 on the ground |
| Amber | `#E0A030` | `#9A5B00` (Amber Ink) | The one accent: links, the current item, the primary button. Use it once per view. |

Amber on white fails contrast, so the light theme uses the darker Amber Ink for
anything the reader must read (5.4:1). Amber is the same hue as the
high-volatility regime colour. That ties the brand to the product, but amber
chrome next to a chart can read as a regime, so keep interface amber away from
charts.

### Regimes

Fills are for shapes (the mark, chart bands, legend swatches). Text colours are
for labels and are tuned for 5.5:1 or better on their ground.

| Regime (`regime` column) | Label | Dark fill | Dark text | Light fill | Light text |
| --- | --- | --- | --- | --- | --- |
| `trend_up` | Trend up | `#5B8DB8` | `#8DB6E8` | `#3F7099` | `#2F6190` |
| `trend_down` | Trend down | `#3E6188` | `#6F96C4` | `#2D4A6E` | `#2D4A6E` |
| `range` | Range | `#8A978E` | `#A3AFA6` | `#7C8A80` | `#5C6B60` |
| `high_volatility` | High volatility | `#E0A030` | `#E0A030` | `#D18F12` | `#9A5B00` |
| `crash` | Crash | `#B5373F` | `#E5646B` | `#A12C35` | `#A12C35` |

Two fills sit under 3:1 against their ground as graphics: trend down on dark
(2.8:1) and high volatility on light (2.8:1). They are always shown with a text
label or legend, so colour is never the only cue, but do not use either as the
sole signal on its own.

### Candle direction

| | Dark | Light |
| --- | --- | --- |
| Up | `#2EBD85` | `#0F8A5F` |
| Down | `#E5484D` | `#C9363B` |

The crash colour is deliberately a deeper crimson than the down red, and the two
trend blues are far from the up green, so a chart can show regime bands and
candles together without confusion.

## Typography

- **DM Sans** for everything that is read: headings at 600 to 650, body at 400,
  the wordmark at 500 and 700.
- **DM Mono** for code, commands, symbols and column names, at 400 and 500.

Both are open source (SIL OFL) and served from the site's own files through
Fontsource; nothing is loaded from a third-party font host. Use tabular
numerals wherever digits line up. Headings use a tight tracking of
`-0.02em`; uppercase labels use `+0.04em` to `+0.08em`.

## The regime strip

A thin horizontal timeline of contiguous coloured runs, one per regime, is the
brand's secondary motif. It appears at the foot of the social images and is the
shape of the hidden regime path itself. Use it as a divider or footer rule, at
most once per page, 8 to 14 px tall. Never use it as a loading bar or progress
indicator.

## Charts

- Candles are up and down colours only.
- Regime bands behind candles are the regime fills at 10 to 24 percent opacity
  (crash strongest, range faintest) so candles stay readable.
- Legends use solid regime fills.
- Never use the regime colours for anything that is not a regime.

## Voice

Plain, specific and checkable. The audience is quantitative researchers and
machine-learning engineers who will test every claim.

- Say what it does and give the number: "208 instruments", "bit-for-bit
  reproducible from the seed". No "revolutionary", "AI-powered" or "unlock".
- Use the project's own words from the [glossary](../../GLOSSARY.md):
  **instrument** (not asset or ticker), **regime**, **market**, **seed**.
- Describe it as synthetic. Never imply it is real market history or a
  prediction of one.
- No investment claims, no promise of profit.

## Implementation

| Where | What |
| --- | --- |
| [`docs/brand/tokens.json`](tokens.json) | Source of truth for every value above. |
| [`website/src/styles/theme.css`](../../website/src/styles/theme.css) | The tokens as CSS custom properties for the docs and landing page. `tests/tooling/test_brand.py` fails if it drifts from `tokens.json`. |
| [`scripts/build_brand_assets.py`](../../scripts/build_brand_assets.py) | Rebuilds `docs/brand/assets/` and the files the site serves. |
| `website/public/` | `favicon.svg`, `apple-touch-icon.png`, `og-image.png`. |
| `website/src/assets/logo.svg` | The docs header logo. |

To change the brand, edit `tokens.json`, mirror the change in `theme.css`, then:

```bash
pip install fonttools brotli uharfbuzz
(cd website && npm ci)
python scripts/build_brand_assets.py
```

## Open items

- **Trademark.** Nobody has cleared "MarketForge", and "Forge" is a crowded word
  in developer tools. Run a trademark and package-name search before investing
  further.
- **GitHub social preview.** GitHub only accepts this image through the
  repository settings (Settings, General, Social preview). Upload
  [`assets/github-social.png`](assets/github-social.png) there; it cannot be set
  from a commit.
