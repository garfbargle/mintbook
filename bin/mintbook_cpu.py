"""CPU process history and inspection, shared by panel-cpu and cpu-menu.

panel-cpu is a new Python process every two seconds, so this file stays
stdlib-only and does no work at import. The walk of /proc that feeds it still
lives in panel-cpu; this is the format, the names, the colours, and the
deeper look at one pid that the popup wants when you click a row.
"""
import os
import json
import time

NCPU = os.cpu_count() or 1
CLK = os.sysconf('SC_CLK_TCK')
PAGE = os.sysconf('SC_PAGESIZE') or 4096
CACHE = os.path.expanduser('~/.cache/mintbook')
STATE = os.path.join(CACHE, 'cpu.state')
PROCS = os.path.join(CACHE, 'cpu.procs')
STACK = os.path.join(CACHE, 'cpu.stack')
IO_STATE = os.path.join(CACHE, 'cpu.io')
STACK_KEEP = 60
TOP_N = 8
LIST_N = 6
CHART_N = 12
BAND_N = 7           # bands the bar can carry at 92px wide
BAND_SPAN = 16       # stack samples the bar draws: ~96 s, the trace's window

# comm is 15 characters of kernel truncation. The same idea as the table in
# bin/battery-menu; both are standalone executables, and this is a data table.
PRETTY = {
    'firefox-bin': 'Firefox', 'firefox': 'Firefox',
    'thunderbird': 'Thunderbird',
    'claude-desktop': 'Claude', 'ChatGPT': 'ChatGPT',
    'code': 'VS Code', 'cursor': 'Cursor', 'Cursor': 'Cursor',
    'chrome': 'Chrome', 'chromium': 'Chromium', 'brave': 'Brave',
    'Web Content': 'Firefox', 'WebExtensions': 'Firefox',
    'RDD Process': 'Firefox', 'Privileged Cont': 'Firefox',
    'Xorg': 'X server', 'Xwayland': 'Xwayland',
    'kthreadd': 'Kernel', 'kworker': 'Kernel worker',
    'xfwm4': 'Window manager', 'xfce4-panel': 'Panel',
    'xfdesktop': 'Desktop', 'xfce4-session': 'Session',
    'pipewire': 'PipeWire', 'pipewire-pulse': 'PipeWire',
    'wireplumber': 'PipeWire',
    'NetworkManager': 'NetworkManager',
    'gnome-terminal-': 'Terminal', 'xfce4-terminal': 'Terminal',
    'gnome-system-mo': 'System Monitor',
    'nemo': 'Files', 'thermald': 'thermald',
    'systemd-journal': 'Journal', 'systemd': 'systemd',
    'python3': 'Python', 'python': 'Python',
    'node': 'Node', 'ruby': 'Ruby', 'perl': 'Perl',
    'bash': 'bash', 'zsh': 'zsh', 'fish': 'fish',
    'rsyslogd': 'syslog', 'dbus-daemon': 'D-Bus',
    'pulseaudio': 'PulseAudio', 'xdg-desktop-por': 'Portal',
    'xdg-document-po': 'Portal', 'xdg-permission-': 'Portal',
    'gsd-media-keys': 'Media keys', 'gsd-power': 'Power',
    'evolution-calen': 'Evolution', 'evolution-addre': 'Evolution',
    'containerd': 'containerd', 'dockerd': 'Docker',
    'snapd': 'snapd', 'flatpak': 'Flatpak',
}

ROLES = (
    ('--type=gpu-process', 'GPU'),
    ('--type=renderer', 'Renderer'),
    ('--type=utility', 'Utility'),
    ('--type=zygote', 'Zygote'),
    ('--type=broker', 'Broker'),
    ('--type=crashpad-handler', 'Crashpad'),
)

SKIP_FD = (
    'socket:', 'pipe:', 'anon_inode:', '/dev/null', '/dev/zero',
    '/dev/full', '/dev/tty', '/dev/ptmx', '/dev/pts/', '/dev/urandom',
    '/dev/random', '/dev/stdin', '/dev/stdout', '/dev/stderr',
    '/proc/', '/sys/',
)


def write_atomic(path, text):
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w') as handle:
        handle.write(text)
    os.replace(tmp, path)


def read_text(path, default=''):
    try:
        with open(path) as handle:
            return handle.read()
    except OSError:
        return default


def pretty(comm, cmdline=''):
    """A name a person would say, plus the Electron/helper role when it matters."""
    if comm.startswith('kworker/'):
        base = 'Kernel worker'
    else:
        base = PRETTY.get(comm, comm.replace('_', ' '))
    role = next((label for needle, label in ROLES if needle in cmdline), '')
    if role:
        return f'{base} · {role}'
    if comm in ('python3', 'python', 'python3.12', 'python3.11',
                'ruby', 'perl', 'node', 'bash', 'sh', 'zsh'):
        script = script_name(cmdline)
        if script:
            return script
    return base


def script_name(cmdline):
    for part in cmdline.split():
        if part.startswith('-'):
            continue
        base = os.path.basename(part.rstrip('/'))
        if base and base not in ('python', 'python3', 'python3.12', 'python3.11',
                                 'ruby', 'perl', 'node', 'bash', 'sh', 'zsh'):
            return base[:28]
    return ''


def human(value, per_s=False):
    value = float(max(0, value))
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if value < 1000 or unit == 'TB':
            text = f'{value:.0f} {unit}' if value >= 10 or unit == 'B' else f'{value:.1f} {unit}'
            return text + ('/s' if per_s else '')
        value /= 1000
    return '0 B' + ('/s' if per_s else '')


def cores(share, ncpu=None):
    """`share` is percent of the machine; this is how many cores that is."""
    return share / 100.0 * (ncpu or NCPU)


def pct_label(share):
    """Share of the machine, at the precision that share deserves.

    The process list used to print cores — `1.0`, `0.0` — which is the Activity
    Monitor number but reads like a score out of ten, and rounds every quiet
    process to the same nothing. A percentage is the unit the header and the
    chart already use, and a tenth of a percent is the smallest thing worth
    printing on a 4-thread machine.
    """
    share = max(0.0, float(share))
    if share >= 9.95:
        return f'{share:.0f}%'
    if share < 0.05:
        return '0%'
    return f'{share:.1f}%'


def encode_sample(sample):
    return json.dumps(sample, separators=(',', ':')) + '\n'


def parse_stack(text):
    samples = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if not isinstance(row, dict) or 'b' not in row or 'p' not in row:
            continue
        row.setdefault('t', 0)
        row.setdefault('d', 0)
        row['p'] = [p for p in row['p'] if isinstance(p, dict) and 'i' in p]
        samples.append(row)
    return samples


def read_stack(path=None):
    return parse_stack(read_text(path or STACK))


def write_stack(samples, path=None, keep=STACK_KEEP):
    body = ''.join(encode_sample(row) for row in samples[-keep:])
    write_atomic(path or STACK, body)


def read_io_table(path=None):
    out = {}
    for line in read_text(path or IO_STATE).splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        try:
            out[parts[0]] = (int(parts[1]), int(parts[2]))
        except ValueError:
            continue
    return out


def write_io_table(table, path=None):
    body = ''.join(f'{pid} {rb} {wb}\n' for pid, (rb, wb) in table.items())
    write_atomic(path or IO_STATE, body)


def pid_io(pid, proc='/proc'):
    """Physical read/write bytes. Missing or EACCES is None, not zero — zero
    would look like a quiet process rather than one we are not allowed to see."""
    try:
        read_b = write_b = None
        with open(f'{proc}/{pid}/io') as handle:
            for line in handle:
                key, _, value = line.partition(':')
                if key == 'read_bytes':
                    read_b = int(value)
                elif key == 'write_bytes':
                    write_b = int(value)
        if read_b is None or write_b is None:
            return None
        return read_b, write_b
    except (OSError, ValueError):
        return None


def pid_io_full(pid, proc='/proc'):
    out = {}
    try:
        with open(f'{proc}/{pid}/io') as handle:
            for line in handle:
                key, _, value = line.partition(':')
                try:
                    out[key.strip()] = int(value)
                except ValueError:
                    continue
    except OSError:
        return {}
    return out


def collapse_procs(procs):
    """One row per *app*, not per pid. Electron and Firefox otherwise occupy
    the whole list as six same-coloured slices of themselves. The busiest pid
    stays the handle so a click still has something live to inspect."""
    groups = {}
    order = []
    for proc in procs:
        comm = proc.get('n') or str(proc.get('i'))
        name = pretty(comm, '')
        if name not in groups:
            row = dict(proc)
            row['n'] = name
            row['comm'] = comm
            row['count'] = 1
            row['_peak'] = float(proc.get('s', 0.0))
            groups[name] = row
            order.append(name)
            continue
        row = groups[name]
        share = float(proc.get('s', 0.0))
        row['s'] = float(row.get('s', 0.0)) + share
        row['m'] = int(row.get('m', 0) or 0) + int(proc.get('m', 0) or 0)
        row['r'] = int(row.get('r', 0) or 0) + int(proc.get('r', 0) or 0)
        row['w'] = int(row.get('w', 0) or 0) + int(proc.get('w', 0) or 0)
        row['count'] += 1
        if share > row['_peak']:
            row['i'] = proc['i']
            row['comm'] = comm
            row['_peak'] = share
    out = [groups[name] for name in order]
    out.sort(key=lambda row: -float(row.get('s', 0.0)))
    return out


def collapse_samples(samples):
    return [{**sample, 'p': collapse_procs(sample.get('p', []))}
            for sample in samples]


def series_for(samples, keys, by='n'):
    """Share across samples for each key. Missing keys are 0 so bands pinch.

    After collapse_samples the stable key is the comm (`n`), not the pid —
    Electron recycles helper processes and the busiest pid moves.
    """
    out = {key: [] for key in keys}
    other = []
    busy = []
    for sample in samples:
        grouped = {}
        for proc in sample.get('p', []):
            key = proc.get(by, proc.get('n'))
            grouped[key] = grouped.get(key, 0.0) + float(proc.get('s', 0.0))
        used = 0.0
        for key in keys:
            share = float(grouped.get(key, 0.0))
            out[key].append(share)
            used += share
        busy_v = float(sample.get('b', 0.0))
        busy.append(busy_v)
        other.append(max(0.0, busy_v - used))
    return out, other, busy


def chart_names(samples, limit=CHART_N):
    """The names worth a band of their own, ranked over the whole window.

    The *list* is a top few right now. Choosing the bands that way too meant a
    process that slipped to sixth lost its colour and fell into the grey
    `other` band for a sample, then came back — a band blinking in the middle
    of the chart. Bands are chosen over the window instead, so only the
    genuinely small are folded into `other`.
    """
    totals = {}
    for sample in samples:
        for proc in sample.get('p', []):
            name = proc.get('n') or str(proc.get('i'))
            totals[name] = totals.get(name, 0.0) + float(proc.get('s', 0.0))
    return sorted(totals, key=lambda name: (-totals[name], name))[:limit]


def bar_stack(span=BAND_SPAN, limit=BAND_N, path=None):
    """(samples, names) for the bar's hover stack.

    One definition because two processes need the same answer: panel-cpu draws
    these names, and cpu-hover looks up their icon colours before asking the
    panel to repaint. The window is trimmed to roughly the span the resting
    trace already shows, so hovering re-colours the line rather than replacing
    it with a different stretch of time.
    """
    samples = collapse_samples(read_stack(path))[-span:]
    return samples, chart_names(samples, limit)


def name_hints(samples):
    """{name: (comm, pid)} — what the icon walk needs to find a .desktop file.

    The most recent sighting wins, so the pid is one that may still be alive.
    Samples must be collapsed first; that is where `comm` survives grouping.
    """
    hints = {}
    for sample in samples:
        for proc in sample.get('p', []):
            name = proc.get('n')
            if name:
                hints[name] = (proc.get('comm') or name, proc.get('i') or 0)
    return hints


def legend_pids(samples, limit=LIST_N):
    """Current top comms first, then whoever used the most over the window.

    Returns (handle_pid, comm). The pid is the busiest member of that comm
    in the latest sample, which is what a click inspects.
    """
    if not samples:
        return []
    totals = {}
    handle = {}
    for sample in samples:
        for proc in sample.get('p', []):
            name = proc.get('n') or str(proc.get('i'))
            totals[name] = totals.get(name, 0.0) + float(proc.get('s', 0.0))
            handle[name] = proc.get('i', handle.get(name))
    latest = []
    for proc in samples[-1].get('p', []):
        name = proc.get('n') or str(proc.get('i'))
        if name not in latest:
            latest.append(name)
        handle[name] = proc.get('i', handle.get(name))
    ranked = sorted(totals, key=lambda name: (
        -(name in latest), -totals[name], name))
    return [(handle[name], name) for name in ranked[:limit]]


def latest_procs(samples, limit=LIST_N):
    if not samples:
        return []
    return list(samples[-1].get('p', [])[:limit])


def span_label(samples):
    if len(samples) < 2:
        return 'collecting…'
    first, last = samples[0].get('t', 0), samples[-1].get('t', 0)
    seconds = max(0, last - first)
    if seconds < 90:
        return f'last {max(1, round(seconds))}s'
    if seconds < 90 * 60:
        return f'last {max(1, round(seconds / 60))} min'
    return f'last {seconds / 3600:.1f} h'


def read_state(path=None):
    """The sparkline file: total, idle, history, tick, top rows."""
    try:
        parts = read_text(path or STATE).split('\n')
        total = int(parts[0])
        idle = int(parts[1])
        hist = [float(x) for x in parts[2].split(',') if x]
        tick = int(parts[3])
        top = []
        for field in parts[4].split('\x1e'):
            if not field:
                continue
            bits = field.split('\x1f')
            pct = float(bits[0])
            name = bits[1] if len(bits) > 1 else ''
            pid = int(bits[2]) if len(bits) > 2 and bits[2].isdigit() else 0
            top.append((pct, name, pid))
        return {'total': total, 'idle': idle, 'hist': hist, 'tick': tick, 'top': top}
    except (OSError, ValueError, IndexError):
        return {'total': None, 'idle': None, 'hist': [], 'tick': -1, 'top': []}


def loadavg(path='/proc/loadavg'):
    try:
        return float(read_text(path).split()[0])
    except (OSError, ValueError, IndexError):
        return 0.0


def meminfo(path='/proc/meminfo'):
    values = {}
    for line in read_text(path).splitlines():
        key, _, rest = line.partition(':')
        try:
            values[key] = int(rest.split()[0]) * 1024
        except (ValueError, IndexError):
            continue
    total = values.get('MemTotal', 0)
    avail = values.get('MemAvailable', 0)
    swap_t = values.get('SwapTotal', 0)
    swap_f = values.get('SwapFree', 0)
    return {
        'total': total, 'avail': avail, 'used': max(0, total - avail),
        'swap_used': max(0, swap_t - swap_f),
    }


def pressure(kind='cpu', path=None):
    """PSI some-avg10: the percent of recent time *some* task was stalled."""
    target = path or f'/proc/pressure/{kind}'
    for line in read_text(target).splitlines():
        if not line.startswith('some '):
            continue
        for field in line.split()[1:]:
            key, _, value = field.partition('=')
            if key == 'avg10':
                try:
                    return float(value)
                except ValueError:
                    return 0.0
    return 0.0


def cmdline_of(pid, proc='/proc'):
    try:
        with open(f'{proc}/{pid}/cmdline', 'rb') as handle:
            raw = handle.read()
    except OSError:
        return ''
    return raw.replace(b'\x00', b' ').decode('utf-8', 'replace').strip()


def readlink_of(pid, name, proc='/proc'):
    try:
        return os.readlink(f'{proc}/{pid}/{name}')
    except OSError:
        return ''


def status_fields(pid, proc='/proc'):
    out = {}
    try:
        with open(f'{proc}/{pid}/status') as handle:
            for line in handle:
                key, _, value = line.partition(':')
                out[key] = value.strip()
    except OSError:
        return out
    return out


def stat_fields(pid, proc='/proc'):
    try:
        with open(f'{proc}/{pid}/stat') as handle:
            text = handle.read()
        comm = text[text.index('(') + 1:text.rindex(')')]
        rest = text[text.rindex(')') + 2:].split()
        return {
            'comm': comm,
            'state': rest[0],
            'ppid': int(rest[1]),
            'utime': int(rest[11]),
            'stime': int(rest[12]),
            'nice': int(rest[16]),
            'threads': int(rest[17]),
            'start': rest[19],
            'rss': int(rest[21]) * PAGE,
            'vsize': int(rest[20]),
        }
    except (OSError, ValueError, IndexError):
        return {}


STATES = {
    'R': 'running', 'S': 'sleeping', 'D': 'disk sleep',
    'T': 'stopped', 't': 'traced', 'Z': 'zombie',
    'X': 'dead', 'I': 'idle', 'P': 'parked',
}


def fd_kind(target):
    if target.startswith('socket:'):
        return 'socket'
    if target.startswith('pipe:'):
        return 'pipe'
    if target.startswith('anon_inode:'):
        return 'anon'
    if any(target.startswith(prefix) for prefix in SKIP_FD):
        return 'other'
    return 'file'


def open_files(pid, proc='/proc', limit=8, home=None):
    fd_dir = f'{proc}/{pid}/fd'
    try:
        names = os.listdir(fd_dir)
    except OSError:
        return [], {'socket': 0, 'pipe': 0, 'anon': 0, 'other': 0, 'files': 0}
    counts = {'socket': 0, 'pipe': 0, 'anon': 0, 'other': 0, 'files': 0}
    files = []
    seen = set()
    home = home if home is not None else os.path.expanduser('~')
    ordered = sorted(names, key=lambda n: int(n) if n.isdigit() else 0)
    for name in ordered[:256]:
        try:
            target = os.readlink(f'{fd_dir}/{name}')
        except OSError:
            continue
        kind = fd_kind(target)
        if kind != 'file':
            counts[kind] = counts.get(kind, 0) + 1
            continue
        counts['files'] += 1
        if target in seen:
            continue
        seen.add(target)
        files.append(target)
    files.sort(key=lambda path: (
        not path.startswith(home),
        path.startswith('/usr') or path.startswith('/lib'),
        path,
    ))
    return files[:limit], counts


def inspect(pid, proc='/proc', prev=None, now=None):
    """Live facts for one process. `prev` is the previous inspect() dict so
    rates can be interval deltas rather than since-start averages."""
    now = time.monotonic() if now is None else now
    stat = stat_fields(pid, proc)
    if not stat:
        return None
    status = status_fields(pid, proc)
    cmd = cmdline_of(pid, proc)
    io = pid_io_full(pid, proc)
    files, fd_counts = open_files(pid, proc)
    rss = stat['rss']
    cpu_j = stat['utime'] + stat['stime']
    rate_cpu = rate_r = rate_w = rate_rchar = 0.0
    if prev and prev.get('pid') == pid:
        dt = max(1e-3, now - prev.get('at', now))
        rate_cpu = max(0.0, (cpu_j - prev['cpu_j']) / CLK / dt)  # cores
        if io and prev.get('io'):
            rate_r = max(0.0, (io.get('read_bytes', 0) - prev['io'].get('read_bytes', 0)) / dt)
            rate_w = max(0.0, (io.get('write_bytes', 0) - prev['io'].get('write_bytes', 0)) / dt)
            rate_rchar = max(0.0, (io.get('rchar', 0) - prev['io'].get('rchar', 0)) / dt)
    name = pretty(stat['comm'], cmd)
    return {
        'pid': pid,
        'at': now,
        'comm': stat['comm'],
        'name': name,
        'state': STATES.get(stat['state'], stat['state']),
        'state_code': stat['state'],
        'ppid': stat['ppid'],
        'nice': stat['nice'],
        'threads': stat['threads'],
        'rss': rss,
        'vsize': stat['vsize'],
        'cpu_j': cpu_j,
        'cores': rate_cpu,
        'cmd': cmd,
        'cwd': readlink_of(pid, 'cwd', proc),
        'exe': readlink_of(pid, 'exe', proc),
        'io': io,
        'read_s': rate_r,
        'write_s': rate_w,
        'rchar_s': rate_rchar,
        'files': files,
        'fd': fd_counts,
        'vmpeak': _kb(status.get('VmPeak')),
        'cgroup': _cgroup(pid, proc),
    }


def _kb(value):
    if not value:
        return 0
    try:
        return int(value.split()[0]) * 1024
    except (ValueError, IndexError):
        return 0


def _cgroup(pid, proc='/proc'):
    for line in read_text(f'{proc}/{pid}/cgroup').splitlines():
        _, _, path = line.partition(':')
        path = path.strip()
        if '/snap.' in path:
            return 'snap'
        if 'flatpak' in path:
            return 'flatpak'
        if 'app-' in path and 'scope' in path:
            return 'app'
    return ''


def io_story(detail):
    """One line about whether the bytes are coming from disk or from cache."""
    if not detail:
        return ''
    disk = detail.get('read_s', 0.0)
    cache = detail.get('rchar_s', 0.0)
    write = detail.get('write_s', 0.0)
    bits = []
    if disk >= 50_000:
        bits.append(f'reading {human(disk, True)} from disk')
    elif cache >= 200_000 and cache > disk * 4:
        bits.append(f'reading {human(cache, True)} from cache')
    if write >= 50_000:
        bits.append(f'writing {human(write, True)}')
    return ' · '.join(bits)


def home_short(path, home=None):
    home = home if home is not None else os.path.expanduser('~')
    if home and path.startswith(home + '/'):
        return '~' + path[len(home):]
    if home and path == home:
        return '~'
    return path
