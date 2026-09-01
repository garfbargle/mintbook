#!/usr/bin/env python3
"""
Regenerate the wifi status icons for the WhiteSur-light icon theme.

Why this exists
---------------
1. WhiteSur ships its NetworkManager icons with a doubled prefix
   (`nm-nm-signal-100-symbolic.svg`), so nm-applet's request for
   `nm-signal-100-symbolic` fell through to the stock hicolor icon.
2. WhiteSur's own wifi glyph is drawn on a 16x16 canvas but only fills ~69%
   of the height with ~0.7px hairlines, so it renders small and reads grey
   rather than white next to the other panel icons.

This script writes a bolder glyph that fills its box, under BOTH the
`nm-signal-*` and `network-wireless-signal-*` names.

Note: GTK3 recolors symbolic icons by forcing `fill` only - never `stroke`.
The arcs must therefore be filled bands, not stroked paths, or they will not
follow the panel's foreground color.

Re-run after any WhiteSur theme update, which will overwrite these files:
    python3 generate-wifi-icons.py && gtk-update-icon-cache -f ~/.icons/WhiteSur-light
"""
import math, os

SPAN   = 32.0            # half-angle of each arc, degrees
THICK  = 2.8             # arc band thickness, in 16px design units
RADII  = (5.5, 10.0, 14.5)
CY     = 14.5            # arc origin, near the bottom of the box
DOT    = 1.45

def band(cx, cy, ro, t, span):
    ri = ro - t
    def P(r, deg):
        a = math.radians(deg)
        return (cx + r * math.sin(a), cy - r * math.cos(a))
    x0, y0 = P(ro, -span); x1, y1 = P(ro, span)
    x2, y2 = P(ri,  span); x3, y3 = P(ri, -span)
    return (f'M{x0:.2f} {y0:.2f}A{ro:.2f} {ro:.2f} 0 0 1 {x1:.2f} {y1:.2f}'
            f'L{x2:.2f} {y2:.2f}A{ri:.2f} {ri:.2f} 0 0 0 {x3:.2f} {y3:.2f}Z')

def svg(size, arcs_on):
    k = size / 16.0
    cx, cy = 8 * k, CY * k
    parts = []
    for i, ro in enumerate(RADII):
        dim = '' if i < arcs_on else ' fill-opacity=".40"'
        parts.append(f'  <path d="{band(cx, cy, ro * k, THICK * k, SPAN)}"{dim}/>')
    parts.append(f'  <circle cx="{cx:.2f}" cy="{cy:.2f}" r="{DOT * k:.2f}"/>')
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}" '
            f'version="1.1" xmlns="http://www.w3.org/2000/svg">\n'
            f' <g fill="#363636">\n' + '\n'.join(parts) + '\n </g>\n</svg>\n')

LEVELS = {'00': 0, '25': 1, '50': 2, '75': 3, '100': 3}
NAMES  = {'00': 'none', '25': 'weak', '50': 'ok', '75': 'good', '100': 'excellent'}

def main():
    base = os.path.expanduser('~/.icons/WhiteSur-light/status')
    written = 0
    for d, size in (('16', 16), ('22', 22), ('24', 24), ('symbolic', 16)):
        dd = os.path.join(base, d)
        if not os.path.isdir(dd):
            continue
        for lv, on in LEVELS.items():
            data = svg(size, on)
            for name in (f'nm-signal-{lv}-symbolic.svg',
                         f'nm-signal-{lv}-secure-symbolic.svg',
                         f'network-wireless-signal-{NAMES[lv]}-symbolic.svg',
                         f'network-wireless-signal-{NAMES[lv]}-secure-symbolic.svg'):
                p = os.path.join(dd, name)
                if os.path.islink(p):
                    os.unlink(p)          # replace WhiteSur's symlinks with real files
                with open(p, 'w') as f:
                    f.write(data)
                written += 1
    print(f'wrote {written} icons')

if __name__ == '__main__':
    main()
