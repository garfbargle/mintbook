#!/usr/bin/env python3
"""Render a `bin/doctor` run as an SVG terminal card for the README.

The card is an excerpt — the hardware sections, which are the ones worth
showing a stranger — but the counts in the footer are the real totals from
the same run, so the picture never claims a cleaner machine than the one it
was generated on. Regenerate with:

    icons/generate-doctor-card.py

Details are truncated, never rewritten. If a check's detail is too long to
fit, that is a signal the check should say less, not that the card should
be wider.
"""
import os
import re
import subprocess
import sys

# The sections a stranger should see: this is the hardware-revival story.
SECTIONS = ['Kernel', 'Graphics', 'Audio', 'Camera', 'Bluetooth']

ANSI = re.compile(r'\x1b\[[0-9;]*m')
ROW = re.compile(r'^ {2}(ok|warn|FAIL) {2,}(\S.*?) {2,}(.*)$')

CHAR_W, LINE_H, PAD = 7.8, 21.0, 26.0
LABEL_COL, DETAIL_COL = 8, 38          # in character cells
MAX_DETAIL = 60                        # characters

FG = {'ok': '#3fb950', 'warn': '#d29922', 'FAIL': '#f85149'}
BG, SECTION, LABEL, DETAIL, MUTED = '#161b22', '#ffffff', '#e6edf3', '#8b949e', '#6e7681'
FONT = ('ui-monospace, SFMono-Regular, Menlo, Consolas, '
        '&quot;DejaVu Sans Mono&quot;, monospace')


def run_doctor(root):
    """Return doctor's human output with the colour escapes removed."""
    out = subprocess.run([os.path.join(root, 'bin', 'doctor')],
                         capture_output=True, text=True, timeout=120).stdout
    return ANSI.sub('', out)


def parse(text):
    """Split doctor output into (header, sections, footer)."""
    header, footer, sections, current = '', '', {}, None
    for line in text.splitlines():
        if line.startswith('mintbook doctor'):
            header = line
        elif re.match(r'^\d+ ok, ', line):
            footer = line
        elif line and not line.startswith(' '):
            current = line.strip()
            sections[current] = []
        elif current:
            row = ROW.match(line.rstrip())
            if row:
                sections[current].append(row.groups())
    return header, sections, footer


def esc(text):
    return (text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))


def truncate(text):
    return text if len(text) <= MAX_DETAIL else text[:MAX_DETAIL - 1].rstrip() + '…'


def svg(header, sections, footer, shown, total):
    lines, y = [], PAD + LINE_H

    def text(col, value, fill, weight='normal'):
        # Presentation attributes only: GitHub serves this file as an image,
        # and a <style> block is not guaranteed to survive that path.
        lines.append(
            f'<text x="{PAD + col * CHAR_W:.1f}" y="{y:.1f}" fill="{fill}" '
            f'font-family="{FONT}" font-size="13" '
            f'font-weight="{weight}" xml:space="preserve">{esc(value)}</text>')

    text(0, header, MUTED)
    y += LINE_H * 1.6
    for name in SECTIONS:
        rows = sections.get(name)
        if not rows:
            continue
        text(0, name, SECTION, 'bold')
        y += LINE_H
        for status, label, detail in rows:
            text(2, status, FG[status], 'bold')
            text(LABEL_COL, label, LABEL)
            text(DETAIL_COL, truncate(detail), DETAIL)
            y += LINE_H
        y += LINE_H * 0.5

    y += LINE_H * 0.3
    text(0, f'… {total - shown} more checks across '
            f'{len(sections) - len(SECTIONS)} further sections', MUTED)
    y += LINE_H * 1.5
    text(0, footer, LABEL, 'bold')

    width = PAD * 2 + (DETAIL_COL + MAX_DETAIL) * CHAR_W
    height = y + PAD
    body = '\n  '.join(lines)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" '
            f'height="{height:.0f}" viewBox="0 0 {width:.0f} {height:.0f}" '
            f'role="img" aria-label="{esc(footer)}">\n'
            f'  <rect width="{width:.0f}" height="{height:.0f}" rx="10" '
            f'fill="{BG}"/>\n  {body}\n</svg>\n')


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    header, sections, footer = parse(run_doctor(root))
    if not footer:
        sys.exit('doctor produced no summary line; nothing to render')

    shown = sum(len(sections.get(name, [])) for name in SECTIONS)
    total = sum(len(rows) for rows in sections.values())
    path = os.path.join(root, 'docs', 'images', 'doctor.svg')
    with open(path, 'w') as handle:
        handle.write(svg(header, sections, footer, shown, total))
    print(f'wrote {path} — {shown} of {total} checks, footer: {footer}')


if __name__ == '__main__':
    main()
