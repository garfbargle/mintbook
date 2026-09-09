#!/usr/bin/env python3
"""Render Mintbook's original power-profile glyphs for the genmon panel."""
import os


GLYPH, PAD_X = 34, 7
COLOR = os.environ.get('MINTBOOK_PANEL_FG', '#ffffff')


def leaf():
    """A narrow leaf and midrib for the saver profile."""
    return (
        '<path d="M 8 1.6 C 13.2 4.3 13.2 11.7 8 14.4 '
        'C 2.8 11.7 2.8 4.3 8 1.6 Z"/>'
        '<path d="M 8 13.9 L 8 5"/>'
    )


def bolt():
    """A compact bolt for the balanced profile."""
    return '<path d="M 9.3 1.5 L 3.8 8.7 H 7.4 L 6.7 14.5 L 12.3 6.8 H 8.7 Z"/>'


def gauge():
    """A high needle for the sustained-performance profile."""
    return (
        '<path d="M 2.4 11.7 A 6.3 6.3 0 1 1 13.6 11.7"/>'
        '<path d="M 8 10.2 L 11.5 6.7"/>'
        '<circle cx="8" cy="10.2" r="0.75" fill="currentColor" stroke="none"/>'
    )


ICONS = {
    'power-saver': leaf,
    'balanced': bolt,
    'performance': gauge,
}


def svg(draw):
    scale = GLYPH / 16.0
    width = GLYPH + 2 * PAD_X
    return (
        f'<svg width="{width}" height="{GLYPH}" viewBox="0 0 {width} {GLYPH}" '
        f'version="1.1" xmlns="http://www.w3.org/2000/svg">\n'
        f' <g color="{COLOR}" fill="none" stroke="{COLOR}" stroke-width="1.35" '
        f'stroke-linecap="round" stroke-linejoin="round" '
        f'transform="translate({PAD_X},0) scale({scale})">\n'
        f'  {draw()}\n'
        f' </g>\n</svg>\n'
    )


def main():
    out = os.path.expanduser('~/.local/share/mintbook/power')
    os.makedirs(out, exist_ok=True)
    for name, draw in ICONS.items():
        with open(os.path.join(out, f'{name}.svg'), 'w', encoding='utf-8') as handle:
            handle.write(svg(draw))
    print(f'wrote {len(ICONS)} SVGs, {GLYPH + 2 * PAD_X}x{GLYPH}px canvas')


if __name__ == '__main__':
    main()
