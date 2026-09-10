"""An app's colour, taken from its own icon.

The CPU menu used to colour its bands from a hash of the kernel `comm`, which
is stable and distinct but arbitrary: Firefox was whatever the hash said.
Firefox is orange. This finds that orange.

The walk is: process -> `.desktop` file -> `Icon=` -> a file in the icon theme
-> the dominant hue of that file. The icon is rendered once at SIZE px and
*every* pixel is sampled — 4096 of them, ~10 ms — rather than sampled at
random, because a full pass is both cheaper than it sounds and repeatable.
Pixels vote for a 15 degree hue bucket, weighted by saturation x value, so the
band takes the colour the eye reads off the icon and not the grey of its
shadow.

Only the *hue* and its mean saturation are cached, not an RGB. Lightness comes
from the appearance at draw time — the same base makes a darker orange on
pearl and a lighter one on slate, and switching appearance does not re-read a
single icon.

**Monochrome icons have no answer.** ChatGPT and Cursor ship black-and-white
marks; so do most terminals. Their bands keep the old hash palette, which is
distinct but not their colour. A grey band would be honest and invisible.

Two apps whose icons share a hue (Claude at 15 degrees, VLC at 24) get bands
that look alike. Nothing here spreads them apart — the point is fidelity to
the icon, and the legend dot is the tiebreak.

Gtk is imported inside the functions that need it: bin/panel-cpu must never
pay for it, and the pure parts stay testable without a display.
"""
import colorsys
import json
import math
import os

CACHE = os.path.expanduser('~/.cache/mintbook/app-colors.json')
VERSION = 1
SIZE = 64            # icon is rendered this big, then every pixel votes
BUCKETS = 24         # 15 degrees each
MIN_CHROMA = 0.10    # fraction of visible pixels carrying any colour at all
MIN_SAT = 0.35       # mean saturation of the winning hue
SKIP = {'', 'sh', 'bash', 'zsh', 'fish', 'python', 'python3', 'node', 'perl',
        'ruby', 'kernel', 'kernel worker', 'systemd'}
EXEC_WRAPPERS = {'env', 'sh', 'bash', 'dbus-run-session', 'exec', 'nohup'}

# Lightness and the saturation window each appearance can carry. Pearl needs
# ink dark enough to read on near-white glass; slate needs it light enough.
TINT_LIGHT = (0.46, 0.50, 1.00)
TINT_DARK = (0.62, 0.45, 0.92)


def app_dirs():
    """Every applications/ directory XDG says to look in."""
    home = os.path.expanduser('~/.local/share')
    data_home = os.environ.get('XDG_DATA_HOME') or home
    dirs = os.environ.get('XDG_DATA_DIRS') or '/usr/local/share:/usr/share'
    out = [os.path.join(data_home, 'applications')]
    out += [os.path.join(d, 'applications') for d in dirs.split(':') if d]
    out += ['/var/lib/flatpak/exports/share/applications',
            os.path.expanduser('~/.local/share/flatpak/exports/share/applications')]
    seen = []
    for d in out:
        if d not in seen and os.path.isdir(d):
            seen.append(d)
    return seen


def signature(dirs=None, theme=''):
    """Changes when apps are installed or the icon theme is switched.

    The whole cache is dropped when it changes, which is what makes a negative
    answer safe to keep: an app installed later is looked at again.
    """
    bits = [str(VERSION), theme]
    for d in dirs if dirs is not None else app_dirs():
        try:
            bits.append(f'{d}:{int(os.stat(d).st_mtime)}')
        except OSError:
            continue
    return '|'.join(bits)


def read_cache(path=None, sig=None):
    """{key: (hue, sat) or None}, empty if the signature moved on."""
    try:
        with open(path or CACHE) as handle:
            blob = json.load(handle)
    except (OSError, ValueError):
        return {}
    if not isinstance(blob, dict) or blob.get('v') != VERSION:
        return {}
    if sig is not None and blob.get('sig') != sig:
        return {}
    out = {}
    for key, value in (blob.get('keys') or {}).items():
        if isinstance(value, list) and len(value) == 2:
            out[key] = (float(value[0]), float(value[1]))
        elif value is None:
            out[key] = None
    return out


def write_cache(entries, path=None, sig=''):
    target = path or CACHE
    os.makedirs(os.path.dirname(target), exist_ok=True)
    body = json.dumps({'v': VERSION, 'sig': sig, 'keys': {
        key: (list(value) if value else None) for key, value in entries.items()}},
        separators=(',', ':'))
    tmp = target + '.tmp'
    with open(tmp, 'w') as handle:
        handle.write(body)
    os.replace(tmp, target)


def parse_desktop(text):
    """Icon name plus the names a process could be recognised by.

    Only the `[Desktop Entry]` group: an action's `Exec` is the same binary
    with a flag, and its `Name` ('New Window') is not an app.
    """
    icon = ''
    keys = []
    in_entry = False
    for line in text.splitlines():
        line = line.strip()
        if line.startswith('['):
            in_entry = line == '[Desktop Entry]'
            continue
        if not in_entry or '=' not in line:
            continue
        field, _, value = line.partition('=')
        value = value.strip()
        field = field.strip()
        if field == 'Icon':
            icon = value
        elif field == 'Exec':
            for part in value.split():
                # `Exec=env GDK_BACKEND=x11 /usr/bin/firefox %u` is a real
                # line: step over the wrapper and its assignments to reach
                # the binary a running process would be called after.
                if (part.startswith('%') or part.startswith('-')
                        or '=' in part
                        or os.path.basename(part) in EXEC_WRAPPERS):
                    continue
                keys.append(os.path.basename(part))
                break
        elif field in ('Name', 'StartupWMClass'):
            keys.append(value)
    if not icon:
        return '', []
    return icon, [k.lower() for k in keys if k]


def desktop_index(dirs=None):
    """{recognisable name: icon name}. Built only when something misses."""
    index = {}
    for directory in dirs if dirs is not None else app_dirs():
        try:
            names = sorted(os.listdir(directory))
        except OSError:
            continue
        for name in names:
            if not name.endswith('.desktop'):
                continue
            try:
                with open(os.path.join(directory, name)) as handle:
                    icon, keys = parse_desktop(handle.read())
            except OSError:
                continue
            if not icon:
                continue
            for key in keys + [name[:-len('.desktop')].lower()]:
                index.setdefault(key, icon)   # the first directory listed wins
    return index


def candidates(comm='', name='', exe='', index=None):
    """Icon names to try, best guess first.

    `exe` is the truth about what is running; `comm` is 15 characters of
    kernel truncation; the pretty name is what a `.desktop` file calls itself.
    `firefox-bin` is the exe of an app whose desktop file says `firefox`.
    """
    index = index or {}
    words = []
    for raw in (os.path.basename(exe), comm, name):
        word = (raw or '').strip().lower()
        if not word or word in SKIP:
            continue
        for form in (word, word[:-4] if word.endswith('-bin') else ''):
            if form and form not in words and form not in SKIP:
                words.append(form)
    out = []
    for word in words:
        for icon in (index.get(word), word):
            if icon and icon not in out:
                out.append(icon)
    return out


def icon_file(name, size=SIZE):
    if not name:
        return ''
    if name.startswith('/'):
        return name if os.path.exists(name) else ''
    import gi
    gi.require_version('Gtk', '3.0')
    from gi.repository import Gtk
    info = Gtk.IconTheme.get_default().lookup_icon(name, size, 0)
    return info.get_filename() or '' if info else ''


def icon_theme_name():
    try:
        import gi
        gi.require_version('Gtk', '3.0')
        from gi.repository import Gtk
        return Gtk.Settings.get_default().get_property('gtk-icon-theme-name') or ''
    except Exception:
        return ''


def dominant(path, size=SIZE):
    """(hue, mean saturation) of the colour the eye reads off an icon.

    None when there is no colour to read: a black-on-transparent mark votes
    only with its antialiasing, and that vote is noise.
    """
    try:
        import gi
        gi.require_version('GdkPixbuf', '2.0')
        from gi.repository import GdkPixbuf
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(path, size, size)
    except Exception:
        return None
    return dominant_pixels(pixbuf.get_pixels(), pixbuf.get_width(),
                           pixbuf.get_height(), pixbuf.get_rowstride(),
                           pixbuf.get_n_channels())


def dominant_pixels(data, width, height, rowstride, channels):
    buckets = [[0.0, 0.0, 0.0, 0.0] for _ in range(BUCKETS)]
    visible = coloured = 0.0
    for y in range(height):
        row = y * rowstride
        for x in range(width):
            off = row + x * channels
            alpha = data[off + 3] / 255 if channels == 4 else 1.0
            if alpha < 0.4:
                continue
            visible += alpha
            hue, sat, val = colorsys.rgb_to_hsv(data[off] / 255,
                                                data[off + 1] / 255,
                                                data[off + 2] / 255)
            if sat < 0.18 or val < 0.12:
                continue
            coloured += alpha
            weight = alpha * sat * val
            bucket = buckets[int(hue * BUCKETS) % BUCKETS]
            bucket[0] += weight
            bucket[1] += weight * math.sin(hue * 2 * math.pi)
            bucket[2] += weight * math.cos(hue * 2 * math.pi)
            bucket[3] += weight * sat
    if not visible or coloured / visible < MIN_CHROMA:
        return None
    # The winner takes its neighbours with it: a gradient across a bucket edge
    # should not lose to a flat fill half its size.
    def score(i):
        return (buckets[i][0] + 0.5 * (buckets[(i + 1) % BUCKETS][0]
                                       + buckets[(i - 1) % BUCKETS][0]))
    best = max(range(BUCKETS), key=score)
    total = sin = cos = sat_sum = 0.0
    for i in (best - 1, best, best + 1):
        bucket = buckets[i % BUCKETS]
        total += bucket[0]
        sin += bucket[1]
        cos += bucket[2]
        sat_sum += bucket[3]
    if total <= 0:
        return None
    sat = sat_sum / total
    if sat < MIN_SAT:
        return None
    hue = (math.atan2(sin / total, cos / total) / (2 * math.pi)) % 1.0
    return round(hue, 4), round(sat, 3)


def tint(base, dark=False, step=0):
    """The base hue as ink for one appearance, or None if there is no base.

    `step` moves a hue that a second app already claimed — same colour, a
    shade along — rather than handing both bands the same orange.
    """
    if not base:
        return None
    lightness, floor, ceiling = TINT_DARK if dark else TINT_LIGHT
    hue, sat = base
    lightness = min(0.80, max(0.30, lightness + 0.11 * step * (1 if dark else -1)))
    sat = min(ceiling, max(floor, sat * 1.15))
    red, green, blue = colorsys.hls_to_rgb(hue, lightness, sat)
    return round(red * 255), round(green * 255), round(blue * 255)


def resolve(wants, cache=None, index=None):
    """Fill in the bases for `wants` — (key, comm, name, exe) tuples.

    Returns (bases, misses_resolved). Everything looked at is recorded, hit or
    miss, so the second popup does no work at all.
    """
    bases = dict(cache or {})
    todo = [w for w in wants if w[0] not in bases]
    if not todo:
        return bases, 0
    if index is None:
        index = desktop_index()
    for key, comm, name, exe in todo:
        found = None
        for icon in candidates(comm, name, exe, index):
            path = icon_file(icon)
            if not path:
                continue
            found = dominant(path)
            if found:
                break
        bases[key] = found
    return bases, len(todo)
