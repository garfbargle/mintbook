#!/usr/bin/env python3
"""Render the System panel icon and its compact semantic badge variants."""
import os
from pathlib import Path

GLYPH, PAD_X = 34, 7
COLOR = os.environ.get('MINTBOOK_PANEL_FG', '#ffffff')
BADGES = {'system.svg': None, 'system-update.svg': '#0a84ff',
          'system-security.svg': '#ff9f0a', 'system-alert.svg': '#ff453a'}


def svg(badge):
    width = GLYPH + 2 * PAD_X
    dot = '' if not badge else (f'<circle cx="37" cy="7" r="4.2" fill="{badge}" '
                                f'stroke="{COLOR}" stroke-width="1.2"/>')
    return f'''<svg width="{width}" height="{GLYPH}" viewBox="0 0 {width} {GLYPH}"
 xmlns="http://www.w3.org/2000/svg">
 <g fill="none" stroke="{COLOR}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <rect x="13" y="7" width="22" height="16" rx="3"/>
  <path d="M10 27h28M18 27l1.6-4h8.8L30 27"/>
 </g>{dot}
</svg>\n'''


def main():
    out = Path.home() / '.local/share/mintbook/system'; out.mkdir(parents=True, exist_ok=True)
    for name, badge in BADGES.items(): (out / name).write_text(svg(badge))
    print(f'wrote {len(BADGES)} System icons to {out}')


if __name__ == '__main__': main()
