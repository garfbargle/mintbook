#!/usr/bin/env python3
"""Render locally drawn night-light SVGs for the genmon panel indicator.

The crescent uses the same 34px glyph + 7px side-padding canvas as wifi/bt.
Shown via genmon <img>, so the fill colour is explicit; GTK does not recolour
these files.

Output: ~/.local/share/mintbook/night/{night-on,night-off}.svg
"""
import os

GLYPH, PAD_X, COLOR = 34, 7, os.environ.get('MINTBOOK_PANEL_FG', '#ffffff')

MOON = (
    'M 10.4 1.7 '
    'C 5.3 2.6 2.5 7.4 4.2 11.8 '
    'C 6.3 17.0 13.1 17.1 15.7 12.3 '
    'C 12.9 13.6 9.8 12.9 8.0 10.6 '
    'C 5.8 7.7 6.9 3.8 10.4 1.7 Z'
)


def svg(opacity):
    k = GLYPH / 16.0
    w = GLYPH + 2 * PAD_X
    op = '' if opacity >= 1 else f' fill-opacity="{opacity}"'
    return (
        f'<svg width="{w}" height="{GLYPH}" viewBox="0 0 {w} {GLYPH}" '
        f'version="1.1" xmlns="http://www.w3.org/2000/svg">\n'
        f' <g fill="{COLOR}"{op} transform="translate({PAD_X},0) scale({k})">\n'
        f'  <path d="{MOON}"/>\n'
        f' </g>\n</svg>\n'
    )


def main():
    out = os.path.expanduser('~/.local/share/mintbook/night')
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, 'night-on.svg'), 'w', encoding='utf-8') as handle:
        handle.write(svg(1))
    with open(os.path.join(out, 'night-off.svg'), 'w', encoding='utf-8') as handle:
        handle.write(svg(0.35))
    print(f'wrote 2 SVGs, {GLYPH + 2 * PAD_X}x{GLYPH}px canvas')


if __name__ == '__main__':
    main()
