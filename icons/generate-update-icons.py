#!/usr/bin/env python3
"""
Render update-manager icons for the genmon panel indicator.

WhiteSur's mintupdate icon is a 1px-thick ring, which reads far thinner than
the neighbouring panel icons. These are drawn with a 2px stroke to match.

Unlike the symbolic icons under ~/.icons, these are shown by genmon via <img>,
so GTK does no recolouring - which means strokes are safe here (GTK3 only
force-recolours `fill` on symbolic icons, never `stroke`).

Output: ~/.local/share/mintbook/update/update-{ok,pending}.svg
"""
import os

GLYPH, PAD_X, COLOR = 34, 7, '#ffffff'

def wrap(body):
    k = GLYPH / 16.0
    w = GLYPH + 2 * PAD_X
    return (f'<svg width="{w}" height="{GLYPH}" viewBox="0 0 {w/k:.3f} 16" '
            f'version="1.1" xmlns="http://www.w3.org/2000/svg">\n'
            f' <g fill="none" stroke="{COLOR}" stroke-width="1.9" '
            f'stroke-linecap="round" stroke-linejoin="round">\n{body}\n </g>\n</svg>\n')

def main():
    k  = GLYPH / 16.0
    cx = (GLYPH + 2 * PAD_X) / k / 2.0     # centre in viewBox units
    ok = (f'  <circle cx="{cx:.2f}" cy="8" r="6.4"/>\n'
          f'  <path d="M4.9 8.2 7.05 10.4 11.1 6.2" transform="translate({cx-8:.2f},0)"/>')
    pending = (f'  <circle cx="{cx:.2f}" cy="8" r="6.4"/>\n'
               f'  <path d="M8 4.6V10.6M5.4 8.1 8 10.7 10.6 8.1" '
               f'transform="translate({cx-8:.2f},0)"/>')
    out = os.path.expanduser('~/.local/share/mintbook/update')
    os.makedirs(out, exist_ok=True)
    open(os.path.join(out, 'update-ok.svg'), 'w').write(wrap(ok))
    open(os.path.join(out, 'update-pending.svg'), 'w').write(wrap(pending))
    print(f'wrote 2 SVGs, {GLYPH + 2*PAD_X}x{GLYPH}px canvas')

if __name__ == '__main__':
    main()
