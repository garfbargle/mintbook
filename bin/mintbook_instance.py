"""Race-free popup ownership; stale pidfiles never authorize a signal."""
import fcntl
import os
from pathlib import Path
import re
import shlex
import signal
import subprocess
import tempfile
import time

_LOCKS = {}
BAR_MENUS = {
    'cpu': 'cpu-menu',
    'temp': 'cpu-menu',
    'bt': 'bt-menu',
    'wifi': 'wifi-menu',
    'battery': 'battery-menu',
    'control': 'control-center',
    'system': 'system-menu',
    'overview': 'overview',
    'night': 'night-menu',
    'power': 'power-menu',
    'updates': 'updates-menu',
}
_WRAPPER_RE = re.compile(
    r'(0x[0-9a-f]+)\s+"wrapper-2\.0".*?(\d+)x(\d+)\+-?\d+\+-?\d+\s+\+(-?\d+)\+(-?\d+)'
)


def owner_matches(pid, script):
    try:
        proc = Path(f'/proc/{pid}')
        if proc.stat().st_uid != os.getuid():
            return False
        argv = [os.fsdecode(a) for a in (proc / 'cmdline').read_bytes().split(b'\0') if a]
        if not argv:
            return False
        # Python scripts appear as interpreter, optional interpreter flags,
        # script path. A name buried in somebody else's arguments is not ours.
        if Path(argv[0]).name == script:
            return True
        if not Path(argv[0]).name.startswith('python'):
            return False
        for arg in argv[1:]:
            if arg.startswith('-'):
                if arg in ('-c', '-m'):
                    return False
                continue
            return Path(arg).name == script
    except (OSError, ValueError):
        pass
    return False


def claim(pidfile, script, signum=signal.SIGTERM):
    pidfile = Path(pidfile)
    pidfile.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(pidfile) + '.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        for _ in range(10):
            try:
                pid = int(pidfile.read_text())
                # pidfd pins the process identity across validation/signalling.
                with os.fdopen(os.pidfd_open(pid), 'rb') as process:
                    if owner_matches(pid, script):
                        signal.pidfd_send_signal(process.fileno(), signum)
                        return False
            except (OSError, ValueError):
                pass
            time.sleep(.02)
        return False
    _LOCKS[str(pidfile)] = fd  # Held for the process lifetime; never unlink it.
    tempfd, temp = tempfile.mkstemp(prefix='.' + pidfile.name, dir=pidfile.parent)
    try:
        with os.fdopen(tempfd, 'w') as handle:
            handle.write(str(os.getpid()))
        os.replace(temp, pidfile)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    return True


def _plugin_target(lib, plugin_id, panel_rc):
    panel_rc = Path.home() / '.config/xfce4/panel' if panel_rc is None else Path(panel_rc)
    if 'libgenmon.so' in lib:
        rc = panel_rc / f'genmon-{plugin_id}.rc'
        try:
            for line in rc.read_text().splitlines():
                if line.startswith('Command='):
                    argv = shlex.split(line.partition('=')[2].strip())
                    if not argv:
                        return None
                    exe = Path(argv[0]).name
                    key = argv[1] if exe == 'panel-read' and len(argv) > 1 else exe.removeprefix('panel-')
                    return BAR_MENUS.get(key)
        except (OSError, ValueError):
            return None
    if 'liblauncher.so' in lib:
        launcher_dir = panel_rc / f'launcher-{plugin_id}'
        try:
            for desktop in sorted(launcher_dir.glob('*.desktop')):
                for line in desktop.read_text().splitlines():
                    if line.startswith('Exec=') and line.partition('=')[2].strip().endswith('/app-grid'):
                        return 'app-grid'
        except OSError:
            return None
    return None


def _cmdline(pid):
    raw = Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')
    return [os.fsdecode(a) for a in raw if a]


def bar_target_at(x, y, panel_rc=None):
    """Resolve which top-bar popup owns screen coordinate (x, y), if any."""
    if not (0 <= y < 56 and x >= 0):
        return None
    try:
        tree = subprocess.check_output(['xwininfo', '-root', '-tree'],
                                       text=True, stderr=subprocess.DEVNULL, timeout=1)
    except (OSError, subprocess.SubprocessError):
        return None
    for line in tree.splitlines():
        if '"wrapper-2.0"' not in line:
            continue
        match = _WRAPPER_RE.search(line)
        if not match:
            continue
        wid, w, h, wx, wy = (match.group(1), int(match.group(2)), int(match.group(3)),
                             int(match.group(4)), int(match.group(5)))
        if w > 10 and h > 10 and wx <= x < wx + w and wy <= y < wy + h:
            try:
                prop = subprocess.check_output(['xprop', '-id', wid, '_NET_WM_PID'],
                                               text=True, stderr=subprocess.DEVNULL, timeout=1)
                pid = int(prop.partition('=')[2].strip())
                args = _cmdline(pid)
            except (OSError, ValueError, subprocess.SubprocessError):
                continue
            if len(args) > 2 and Path(args[0]).name == 'wrapper-2.0':
                target = _plugin_target(args[1], args[2], panel_rc)
                if target:
                    return target
    return None


def bar_handoff(event, current_script, bin_dir=None, panel_rc=None):
    """When an outside click lands on another top-bar icon, open that menu directly."""
    if getattr(event, 'button', 1) != 1:
        return False
    try:
        x = int(round(float(getattr(event, 'x_root', -1))))
        y = int(round(float(getattr(event, 'y_root', -1))))
    except (TypeError, ValueError):
        return False
    target = bar_target_at(x, y, panel_rc=panel_rc)
    if not target or target == current_script:
        return False
    base = Path.home() / '.local/bin' if bin_dir is None else Path(bin_dir)
    exe = base / target
    if not os.access(exe, os.X_OK):
        return False
    env = os.environ.copy()
    env['MINTBOOK_ANCHOR'] = f'{x},{y}'
    subprocess.Popen([str(exe)], env=env, stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)
    return True
