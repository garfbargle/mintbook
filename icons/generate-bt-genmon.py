#!/usr/bin/env python3
"""
Render bluetooth SVGs for the genmon panel indicator.

Same canvas as the wifi genmon icons (34px glyph + 7px side padding) so the
two sit at the same visual size. Shown via genmon <img>, so fill is hardcoded
white; GTK does not recolour these.

The rune is drawn locally as a six-segment stroked mark.

Output: ~/.local/share/mintbook/bt/bt-{on,off}.svg
"""
import os

GLYPH, PAD_X, COLOR = 34, 7, os.environ.get('MINTBOOK_PANEL_FG', '#ffffff')

def svg(opacity):
    k = GLYPH / 16.0
    w = GLYPH + 2 * PAD_X
    op = '' if opacity >= 1 else f' opacity="{opacity}"'
    return (
        f'<svg width="{w}" height="{GLYPH}" viewBox="0 0 {w} {GLYPH}" '
        f'version="1.1" xmlns="http://www.w3.org/2000/svg">\n'
        f' <g fill="none" stroke="{COLOR}" stroke-width="1.45"{op} '
        f'stroke-linecap="round" stroke-linejoin="round" '
        f'transform="translate({PAD_X},0) scale({k})">\n'
        f'  <path d="M 4.5 5.1 L 11.5 10.9 L 8 14.1 L 8 1.9 '
        f'L 11.5 5.1 L 4.5 10.9"/>\n'
        f' </g>\n</svg>\n'
    )

def main():
    out = os.path.expanduser('~/.local/share/mintbook/bt')
    os.makedirs(out, exist_ok=True)
    open(os.path.join(out, 'bt-on.svg'), 'w').write(svg(1))
    open(os.path.join(out, 'bt-off.svg'), 'w').write(svg(0.35))
    print(f'wrote 2 SVGs, {GLYPH + 2 * PAD_X}x{GLYPH}px canvas')

if __name__ == '__main__':
    main()
