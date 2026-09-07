#!/usr/bin/env python3
"""
Render standalone wifi SVGs for the genmon panel indicator.

The shape is bin/wifi-menu's wifi_glyph(), not a second drawing of the same
idea: three arcs *stroked* with round caps, and a round dot. It used to be
three filled annular wedges, which have square ends and read as heavier and
blockier than the same fan in the popup — the bar and the menu were drawing
two different Wi-Fi icons. The proportions below are that function's, as
fractions of a box, and BOX is solved so the drawn glyph keeps the height the
wedge version had.

NOT symbolic icons - genmon shows them via <img>, so GTK does no recolouring
and the fill must be an explicit colour. It defaults to white, for the dark
bar; bin/appearance-mode re-runs this with MINTBOOK_PANEL_FG on every
appearance change, and bin/wifi-install reads the same value out of
system-chrome.env, so neither a switch nor a fresh install leaves white ink on
a light bar.

The canvas is wider than the glyph to build in horizontal padding, since genmon
gives panel items no margin of their own.

Output: ~/.local/share/mintbook/wifi/wifi-{0..3}.svg, wifi-off.svg, and
wifi-warn.svg - associated, full bars, no route to anywhere. That one is wider
than the rest, because the exclamation sits beside the fan the way macOS puts
it rather than inside it, where nothing legible fits at this size. The bar
reflows when it appears, which is the point of it.
"""
import math, os

GLYPH  = 34             # canvas height, px - tuned to sit with the panel icon-size
PAD_X  = 7              # horizontal breathing room baked into the canvas
COLOR  = os.environ.get('MINTBOOK_PANEL_FG', '#ffffff')
DIM    = .22            # arcs past the signal level, same as the menu's

# bin/wifi-menu's wifi_glyph(), as fractions of its box. Keep the two in step.
CX, CY, DOTY = .50, .78, .77
RADII        = (.16, .31, .46)
STROKE, DOT  = .085, .055
A0, A1       = math.pi * 1.22, math.pi * 1.78

# The drawn glyph, also as fractions of the box: the outer arc's top and the
# dot's bottom, and the half-width at the arc ends. Round caps put another
# half-stroke past each, which is why STROKE is in all three.
EXTENT_TOP = CY - RADII[-1] - STROKE / 2
EXTENT_BOT = DOTY + DOT
HALF       = RADII[-1] * abs(math.cos(A0)) + STROKE / 2

# Solved from the *width*, not the height. The menu's fan sweeps 101 degrees
# against the wedge version's 84, so matching the two on height made it 20%
# wider than the icon it replaced and it read as a size larger than the
# battery beside it. Matched on width it sits with the rest of the bar, and
# the extra vertical padding is how the same glyph sits in the popup anyway.
TARGET_W = 34.0
BOX      = TARGET_W / (2 * HALF)
TARGET_H = (EXTENT_BOT - EXTENT_TOP) * BOX

WARN_GAP, WARN_W = 5.0, 3.4      # from the fan's right edge, and the stem


def arc(cx, cy, r):
    """An SVG arc for the same sweep cairo's arc() walks. Under 180 degrees, so
    large-arc is 0; y is down in both, so increasing angle is sweep 1."""
    x0, y0 = cx + r * math.cos(A0), cy + r * math.sin(A0)
    x1, y1 = cx + r * math.cos(A1), cy + r * math.sin(A1)
    return f'M{x0:.2f} {y0:.2f}A{r:.2f} {r:.2f} 0 0 1 {x1:.2f} {y1:.2f}'


def svg(arcs_on, warn=False):
    # Box origin, placed so the glyph's own left edge lands on PAD_X and its
    # own top and bottom sit centred in GLYPH.
    bx = PAD_X - (CX - HALF) * BOX
    by = (GLYPH - TARGET_H) / 2 - EXTENT_TOP * BOX
    cx, cy = bx + CX * BOX, by + CY * BOX
    lw = STROKE * BOX
    parts = []
    for i, r in enumerate(RADII):
        op = '' if i < arcs_on else f' stroke-opacity="{DIM}"'
        parts.append(f'  <path d="{arc(cx, cy, r * BOX)}"{op}/>')
    dots = [f'  <circle cx="{cx:.2f}" cy="{by + DOTY * BOX:.2f}" '
            f'r="{DOT * BOX:.2f}"/>']
    w = bx + (CX + HALF) * BOX + PAD_X
    if warn:
        right = bx + (CX + HALF) * BOX
        top = cy - RADII[-1] * BOX
        ex = right + WARN_GAP + WARN_W / 2
        r = WARN_W / 2
        stem_b = by + DOTY * BOX - DOT * BOX - 2.4
        dots.append(
            f'  <rect x="{ex - r:.2f}" y="{top:.2f}" width="{WARN_W:.2f}" '
            f'height="{stem_b - top:.2f}" rx="{r:.2f}"/>')
        dots.append(f'  <circle cx="{ex:.2f}" cy="{by + DOTY * BOX:.2f}" '
                    f'r="{r:.2f}"/>')
        w = ex + r + PAD_X
    return (f'<svg width="{w:.0f}" height="{GLYPH}" viewBox="0 0 {w:.0f} {GLYPH}" '
            f'version="1.1" xmlns="http://www.w3.org/2000/svg">\n'
            f' <g fill="none" stroke="{COLOR}" stroke-width="{lw:.2f}" '
            f'stroke-linecap="round">\n' + '\n'.join(parts) + '\n </g>\n'
            f' <g fill="{COLOR}">\n' + '\n'.join(dots) + '\n </g>\n</svg>\n')


def main():
    out = os.path.expanduser('~/.local/share/mintbook/wifi')
    os.makedirs(out, exist_ok=True)
    for n in range(4):
        open(os.path.join(out, f'wifi-{n}.svg'), 'w').write(svg(n))
    open(os.path.join(out, 'wifi-off.svg'), 'w').write(svg(0))
    open(os.path.join(out, 'wifi-warn.svg'), 'w').write(svg(3, warn=True))
    print(f'wrote 6 SVGs, {GLYPH}px canvas, glyph {TARGET_W:.0f}x{TARGET_H:.1f}px '
          f'in a {BOX:.1f}px box + {PAD_X}px side padding; '
          f'wifi-warn.svg is wider, for the exclamation')


if __name__ == '__main__':
    main()
