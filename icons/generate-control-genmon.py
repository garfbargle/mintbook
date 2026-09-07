#!/usr/bin/env python3
"""
Render the Control Center SVG for the genmon panel indicator.

Two switch pills, knobs on opposite sides — the macOS menu-bar mark. Same
34px glyph on a 7px-padded canvas as wifi / bluetooth / night, so the whole
group lines up. genmon shows these as plain images and GTK does not recolour
them, so the fill is baked from MINTBOOK_PANEL_FG (bin/appearance-mode sets it).

Output: ~/.local/share/mintbook/control-center.svg
"""
import os

GLYPH, PAD_X = 34, 7
COLOR = os.environ.get('MINTBOOK_PANEL_FG', '#ffffff')

PILL_W, PILL_H, STROKE = 25.0, 9.5, 1.9
ROWS = ((10.0, 'right'), (23.5, 'left'))       # centre y, knob side


def svg():
    w = GLYPH + 2 * PAD_X
    x0 = (w - PILL_W) / 2
    parts = []
    for cy, side in ROWS:
        r = PILL_H / 2
        parts.append(
            f'  <rect x="{x0:.2f}" y="{cy - r:.2f}" width="{PILL_W}" '
            f'height="{PILL_H}" rx="{r}" fill="none" stroke="{COLOR}" '
            f'stroke-width="{STROKE}"/>')
        kx = x0 + (PILL_W - r - 1.2 if side == 'right' else r + 1.2)
        parts.append(f'  <circle cx="{kx:.2f}" cy="{cy:.2f}" r="2.5" fill="{COLOR}"/>')
    body = '\n'.join(parts)
    return (f'<svg width="{w}" height="{GLYPH}" viewBox="0 0 {w} {GLYPH}" '
            f'version="1.1" xmlns="http://www.w3.org/2000/svg">\n{body}\n</svg>\n')


def main():
    out = os.path.expanduser('~/.local/share/mintbook')
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, 'control-center.svg')
    with open(path, 'w') as f:
        f.write(svg())
    print(f'wrote {path}, {GLYPH + 2 * PAD_X}x{GLYPH}px canvas')


if __name__ == '__main__':
    main()
