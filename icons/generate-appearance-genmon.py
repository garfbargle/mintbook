#!/usr/bin/env python3
"""Render the light/dark appearance indicator in the current panel foreground."""
import os
COLOR = os.environ.get('MINTBOOK_PANEL_FG', '#ffffff')
OUT = os.path.expanduser('~/.local/share/mintbook/appearance')
def write(name, body):
    os.makedirs(OUT, exist_ok=True)
    open(os.path.join(OUT, name), 'w').write(f'<svg width="48" height="34" viewBox="0 0 48 34" xmlns="http://www.w3.org/2000/svg"><g fill="{COLOR}">{body}</g></svg>\n')
write('appearance-light.svg', '<circle cx="24" cy="17" r="7"/><path d="M23 2h2v6h-2zM23 26h2v6h-2zM9 16h6v2H9zM33 16h6v2h-6zM13 6l1.4-1.4 4.2 4.2-1.4 1.4zM33.6 4.6L35 6l-4.2 4.2-1.4-1.4zM13 28l1.4 1.4 4.2-4.2-1.4-1.4zM33.6 29.4l1.4-1.4-4.2-4.2-1.4 1.4z')
write('appearance-dark.svg', '<path d="M29.8 3.6C19 4.8 14.2 17.9 21.2 25.5c4.5 4.9 12 5 16.7.6-9.2 1.5-15-8.6-8.1-16.2z"/>')
