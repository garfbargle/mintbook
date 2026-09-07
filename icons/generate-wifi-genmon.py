#!/usr/bin/env python3
"""
Render standalone wifi SVGs for the genmon panel indicator.

NOT symbolic icons - genmon shows them via <img>, so GTK does no recolouring
and the fill must be an explicit colour. It defaults to white, for the dark
bar; bin/appearance-mode re-runs this with MINTBOOK_PANEL_FG on every
appearance change, and bin/wifi-install reads the same value out of
system-chrome.env, so neither a switch nor a fresh install leaves white ink on
a light bar.

The canvas is wider than the glyph to build in horizontal padding, since genmon
gives panel items no margin of their own.

Output: ~/.local/share/mintbook/wifi/wifi-{0..3}.svg, wifi-off.svg, and
wifi-warn.svg — associated, full bars, no route to anywhere. That one is
wider than the rest, because the exclamation sits beside the fan the way
macOS puts it rather than inside it, where nothing legible fits at 34 px.
The bar reflows by 12 px when it appears, which is the point of it.
"""
import math, os

GLYPH  = 34             # glyph box, px - tuned to sit with the panel icon-size
PAD_X  = 7              # horizontal breathing room baked into the canvas
COLOR  = os.environ.get('MINTBOOK_PANEL_FG', '#ffffff')

# Wide-and-short proportions: a large SPAN keeps the arcs broad and stops the
# glyph looking tall. RADII are capped so the widest band still fits the box.
SPAN, THICK, RADII, CY, DOT = 42.0, 2.4, (4.6, 8.1, 11.6), 13.6, 1.25

def band(cx, cy, ro, t, span):
    ri = ro - t
    def P(r, deg):
        a = math.radians(deg); return (cx + r*math.sin(a), cy - r*math.cos(a))
    x0,y0 = P(ro,-span); x1,y1 = P(ro,span); x2,y2 = P(ri,span); x3,y3 = P(ri,-span)
    return (f'M{x0:.2f} {y0:.2f}A{ro:.2f} {ro:.2f} 0 0 1 {x1:.2f} {y1:.2f}'
            f'L{x2:.2f} {y2:.2f}A{ri:.2f} {ri:.2f} 0 0 0 {x3:.2f} {y3:.2f}Z')

WARN_GAP, WARN_W = 5.0, 3.4      # from the fan's right edge, and the stem


def svg(arcs_on, warn=False):
    k  = GLYPH / 16.0
    w  = GLYPH + 2 * PAD_X
    cx, cy = PAD_X + 8 * k, CY * k
    parts = []
    for i, ro in enumerate(RADII):
        op = '' if i < arcs_on else ' fill-opacity=".35"'
        parts.append(f'  <path d="{band(cx, cy, ro*k, THICK*k, SPAN)}"{op}/>')
    parts.append(f'  <circle cx="{cx:.2f}" cy="{cy:.2f}" r="{DOT*k:.2f}"/>')
    if warn:
        # The widest band decides where the fan actually ends — the canvas is
        # mostly padding, so measuring it rather than assuming leaves the gap
        # the same if RADII or SPAN ever change.
        right = cx + max(RADII) * k * math.sin(math.radians(SPAN))
        top = cy - max(RADII) * k
        ex = right + WARN_GAP + WARN_W / 2
        stem_b = cy - DOT * k - 2.4 * k        # clear of the dot's baseline
        r = WARN_W / 2
        parts.append(
            f'  <rect x="{ex - r:.2f}" y="{top:.2f}" width="{WARN_W:.2f}" '
            f'height="{stem_b - top:.2f}" rx="{r:.2f}"/>')
        parts.append(f'  <circle cx="{ex:.2f}" cy="{cy:.2f}" r="{r:.2f}"/>')
        w = ex + r + PAD_X
    return (f'<svg width="{w:.0f}" height="{GLYPH}" viewBox="0 0 {w:.0f} {GLYPH}" '
            f'version="1.1" xmlns="http://www.w3.org/2000/svg">\n'
            f' <g fill="{COLOR}">\n' + '\n'.join(parts) + '\n </g>\n</svg>\n')

def main():
    out = os.path.expanduser('~/.local/share/mintbook/wifi')
    os.makedirs(out, exist_ok=True)
    for n in range(4):
        open(os.path.join(out, f'wifi-{n}.svg'), 'w').write(svg(n))
    open(os.path.join(out, 'wifi-off.svg'), 'w').write(svg(0))
    open(os.path.join(out, 'wifi-warn.svg'), 'w').write(svg(3, warn=True))
    print(f'wrote 6 SVGs, {GLYPH + 2*PAD_X}x{GLYPH}px canvas '
          f'({GLYPH}px glyph + {PAD_X}px side padding); '
          f'wifi-warn.svg is wider, for the exclamation')

if __name__ == '__main__':
    main()
