"""Race-free popup ownership; stale pidfiles never authorize a signal."""
import fcntl
import os
from pathlib import Path
import signal
import tempfile
import time

_LOCKS = {}


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
