#!/usr/bin/env python3
"""
Render the software-update SVGs for the genmon panel indicator.

The shape is bin/updates-menu's update_glyph(): an arrow coming down into an
open tray. The proportions below are that function's, as fractions of a unit
box, for the reason the Wi-Fi generator carries the same note — the bar and
the popup should be drawing one icon, not two drawings of one idea.

NOT symbolic icons. genmon shows them through <img>, so GTK does no
recolouring and the fill has to be an explicit colour. It defaults to white,
for the dark bar; bin/appearance-mode re-runs this with MINTBOOK_PANEL_FG on
every appearance change, and bin/updates-install reads the same value out of
system-chrome.env, so neither a switch nor a fresh install leaves white ink on
a light bar.

Output: ~/.local/share/mintbook/updates/updates.svg and updates-alert.svg.
The alert one carries a dot to the right of the tray and is wider, the way
wifi-warn.svg carries its exclamation — beside the glyph rather than inside
it, where nothing legible fits at this size. The bar reflows when the icon
appears at all, so it reflows again for the dot, which is the point of both.

There is no "up to date" icon on purpose. bin/panel-updates prints no image
when there is nothing waiting, and the indicator disappears; the Control
Center's Updates tile is the door that is always there. See docs/updates.md.
"""
import os

GLYPH = 34              # canvas height, px — the shared panel icon box
PAD_X = 7               # horizontal breathing room; genmon gives items none
COLOR = os.environ.get('MINTBOOK_PANEL_FG', '#ffffff')

# bin/updates-menu's update_glyph(), as fractions of its box. Keep them in step.
STEM_TOP, STEM_BOT = .08, .50
HEAD_X, HEAD_Y, TIP_Y = .27, .33, .56
TRAY_X, TRAY_TOP, TRAY_BOT = .16, .64, .88
STROKE = .092

HALF = STROKE / 2
EXTENT_TOP, EXTENT_BOT = STEM_TOP - HALF, TRAY_BOT + HALF
EXTENT_L, EXTENT_R = TRAY_X - HALF, (1 - TRAY_X) + HALF

# Solved from the height, not the width: this glyph is taller than it is wide
# and every other icon in the group is the other way round, so matching it on
# width would have made it the tallest thing on the bar. 27.3px is what the
# Wi-Fi fan measures; a hair under it, because a vertical glyph at the same
# height reads taller than a horizontal one at that height. See
# icons/generate-wifi-genmon.py.
TARGET_H = 26.4
BOX = TARGET_H / (EXTENT_BOT - EXTENT_TOP)
TARGET_W = (EXTENT_R - EXTENT_L) * BOX

DOT_GAP, DOT_R = 4.6, 2.7        # from the tray's right edge, and the badge


def svg(alert=False):
    bx = PAD_X - EXTENT_L * BOX
    by = (GLYPH - TARGET_H) / 2 - EXTENT_TOP * BOX
    def X(u):
        return bx + u * BOX
    def Y(u):
        return by + u * BOX

    strokes = [
        f'  <path d="M{X(.5):.2f} {Y(STEM_TOP):.2f}L{X(.5):.2f} {Y(TIP_Y):.2f}"/>',
        f'  <path d="M{X(HEAD_X):.2f} {Y(HEAD_Y):.2f}L{X(.5):.2f} {Y(TIP_Y):.2f}'
        f'L{X(1 - HEAD_X):.2f} {Y(HEAD_Y):.2f}"/>',
        f'  <path d="M{X(TRAY_X):.2f} {Y(TRAY_TOP):.2f}L{X(TRAY_X):.2f} '
        f'{Y(TRAY_BOT):.2f}L{X(1 - TRAY_X):.2f} {Y(TRAY_BOT):.2f}'
        f'L{X(1 - TRAY_X):.2f} {Y(TRAY_TOP):.2f}"/>',
    ]
    dots = []
    w = bx + EXTENT_R * BOX + PAD_X
    if alert:
        cx = bx + EXTENT_R * BOX + DOT_GAP + DOT_R
        cy = (Y(EXTENT_TOP) + Y(EXTENT_BOT)) / 2
        dots.append(f'  <circle cx="{cx:.2f}" cy="{cy:.2f}" '
                    f'r="{DOT_R}" fill="{COLOR}"/>')
        w = cx + DOT_R + PAD_X
    body = ('\n'.join(strokes) + '\n </g>\n'
            + (' <g>\n' + '\n'.join(dots) + '\n </g>\n' if dots else ''))
    return (f'<svg width="{w:.0f}" height="{GLYPH}" viewBox="0 0 {w:.0f} {GLYPH}" '
            f'version="1.1" xmlns="http://www.w3.org/2000/svg">\n'
            f' <g fill="none" stroke="{COLOR}" stroke-width="{STROKE * BOX:.2f}" '
            f'stroke-linecap="round" stroke-linejoin="round">\n{body}</svg>\n')


def main():
    out = os.path.expanduser('~/.local/share/mintbook/updates')
    os.makedirs(out, exist_ok=True)
    for name, alert in (('updates.svg', False), ('updates-alert.svg', True)):
        with open(os.path.join(out, name), 'w') as f:
            f.write(svg(alert))
    print(f'wrote 2 SVGs, {GLYPH}px canvas, glyph {TARGET_W:.1f}x{TARGET_H:.1f}px '
          f'in a {BOX:.1f}px box + {PAD_X}px side padding; '
          f'updates-alert.svg is wider, for the badge')


if __name__ == '__main__':
    main()
