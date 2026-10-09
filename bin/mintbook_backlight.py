"""One brightness scale for keys, hardware changes, and Control Center."""
import configparser
import fcntl
import os
from pathlib import Path
import subprocess
import tempfile

BL = Path('/sys/class/backlight/acpi_video0')
CONFIG = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config'))
STATE_DIR = CONFIG / 'mintbook'
STATE = STATE_DIR / 'backlight-curve.state'
SOFT = STATE_DIR / 'soft-brightness'
LOCK = Path.home() / '.cache/mintbook/backlight-curve.lock'


def atomic(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as handle:
            handle.write(text)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def read_state(path=STATE):
    try:
        return dict(line.split('=', 1) for line in path.read_text().splitlines() if '=' in line)
    except OSError:
        return {}


def level(hardware, maximum, state):
    try:
        requested = int(state['req_pct'])
        if int(state['hw']) == hardware and 0 <= requested <= 100:
            return requested
    except (KeyError, ValueError):
        pass
    return max(0, min(100, round(hardware * 100 / maximum)))


def curve(percent, maximum, settings):
    gamma = float(settings.get('BACKLIGHT_CURVE_GAMMA', 1.7))
    floor = float(settings.get('BACKLIGHT_CURVE_SOFT_FLOOR', .35))
    hardware_floor = int(settings.get('BACKLIGHT_CURVE_HW_FLOOR', 12))
    if not (.1 <= gamma <= 5 and .1 <= floor <= 1 and 1 <= hardware_floor <= maximum):
        raise ValueError('invalid brightness curve settings')
    percent = max(0, min(100, int(percent)))
    return max(hardware_floor, round(percent * maximum / 100)), floor + (1 - floor) * (percent / 100) ** gamma


def apply(percent=None, step=None, external=False):
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    with LOCK.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        maximum = int((BL / 'max_brightness').read_text())
        hardware = int((BL / 'brightness').read_text())
        state = read_state()
        current = level(hardware, maximum, state)
        if external and state.get('hw') == str(hardware):
            return current
        requested = max(0, min(100, int(percent if percent is not None else current + (step or 0))))
        settings = read_state(STATE_DIR / 'backlight-curve.env')
        want, soft = curve(requested, maximum, settings)
        if hardware != want:
            subprocess.run(['busctl', '--system', 'call', 'org.freedesktop.login1',
                            '/org/freedesktop/login1/session/auto', 'org.freedesktop.login1.Session',
                            'SetBrightness', 'ssu', 'backlight', BL.name, str(want)],
                           check=True, capture_output=True, timeout=3)
        actual = int((BL / 'brightness').read_text())
        if actual != want:
            raise RuntimeError('the hardware did not apply the requested brightness')
        soft_text = f'{soft:.4f}'
        old_soft = SOFT.read_text() if SOFT.exists() else None
        changed = old_soft is None or old_soft.strip() != soft_text
        atomic(SOFT, soft_text + '\n')
        if changed:
            try:
                subprocess.run(['systemctl', '--user', 'restart', 'mintbook-redshift.service'],
                               check=True, capture_output=True, timeout=5)
            except Exception:
                # Keep failures retryable and report actual hardware until reconciliation.
                if old_soft is None:
                    SOFT.unlink(missing_ok=True)
                else:
                    atomic(SOFT, old_soft)
                raise
        atomic(STATE, f'req_pct={requested}\nsoft={soft_text}\nhw={actual}\n')
        return requested


def redshift_args(config, soft, mode='auto'):
    brightness = float(soft)
    if not .1 <= brightness <= 1:
        raise ValueError('invalid software brightness')
    # CLI overrides retain the distro/AppArmor-approved base config path.
    args = ['/usr/bin/redshift', '-c', str(config), '-b',
            f'{brightness}:{brightness}', '-r']
    if mode == 'on':
        conf = configparser.ConfigParser(interpolation=None)
        conf.read(config)
        temperature = conf.getint('redshift', 'temp-night', fallback=3500)
        args += ['-t', f'{temperature}:{temperature}']
    elif mode == 'off':
        args += ['-t', '6500:6500']
    return args
