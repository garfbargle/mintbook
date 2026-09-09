#!/usr/bin/env python3
"""Render Overview's magnifying-glass panel icon."""
import os

GLYPH, PAD_X = 34, 7
COLOR = os.environ.get('MINTBOOK_PANEL_FG', '#ffffff')


def svg():
    width = GLYPH + 2 * PAD_X
    # A slightly open, optical-size-adjusted magnifier. It uses the same 34px
    # glyph and padded canvas as the other Mintbook status indicators.
    return f'''<svg width="{width}" height="{GLYPH}" viewBox="0 0 {width} {GLYPH}"
  xmlns="http://www.w3.org/2000/svg">
  <g fill="none" stroke="{COLOR}" stroke-width="2.35" stroke-linecap="round">
    <circle cx="22" cy="14" r="7.8"/>
    <path d="M27.7 19.7 L34.1 26.1"/>
  </g>
</svg>
'''


def main():
    out = os.path.expanduser('~/.local/share/mintbook')
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, 'overview.svg')
    with open(path, 'w') as handle:
        handle.write(svg())
    print(f'wrote {path}, {GLYPH + 2 * PAD_X}x{GLYPH}px canvas')


if __name__ == '__main__':
    main()
