#!/usr/bin/env python3
"""
Render bluetooth SVGs for the genmon panel indicator.

Same canvas as the wifi genmon icons (34px glyph + 7px side padding) so the
two sit at the same visual size. Shown via genmon <img>, so fill is hardcoded
white; GTK does not recolour these.

The rune is WhiteSur's bluetooth-symbolic path, scaled into the canvas.

Output: ~/.local/share/mintbook/bt/bt-{on,off}.svg
"""
import os

GLYPH, PAD_X, COLOR = 34, 7, os.environ.get('MINTBOOK_PANEL_FG', '#ffffff')

# 16x16 WhiteSur bluetooth-symbolic
RUNE = (
    'm7.2949 1.0449a0.50005 0.50005 0 0 0-0.29492 0.45508v5.2852l-2.7344-1.709'
    'a0.5 0.5 0 0 0-0.68945 0.1582 0.5 0.5 0 0 0 0.1582 0.68945l3.2656 2.041v0.070313'
    'l-3.2656 2.041a0.5 0.5 0 0 0-0.1582 0.68945 0.5 0.5 0 0 0 0.68945 0.1582l2.7344-1.709'
    'v5.2852a0.50005 0.50005 0 0 0 0.83203 0.37305l4.5-4a0.50005 0.50005 0 0 0-0.06641-0.79688'
    'l-3.3223-2.0762 3.3223-2.0762a0.50005 0.50005 0 0 0 0.06641-0.79688l-4.5-4'
    'a0.50005 0.50005 0 0 0-0.53711-0.082031zm0.70508 1.5684 3.1699 2.8164-3.1699 1.9805z'
    'm0 5.9766 3.1699 1.9805-3.1699 2.8164z'
)

def svg(opacity):
    k = GLYPH / 16.0
    w = GLYPH + 2 * PAD_X
    op = '' if opacity >= 1 else f' fill-opacity="{opacity}"'
    return (
        f'<svg width="{w}" height="{GLYPH}" viewBox="0 0 {w} {GLYPH}" '
        f'version="1.1" xmlns="http://www.w3.org/2000/svg">\n'
        f' <g fill="{COLOR}"{op} transform="translate({PAD_X},0) scale({k})">\n'
        f'  <path d="{RUNE}"/>\n'
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
