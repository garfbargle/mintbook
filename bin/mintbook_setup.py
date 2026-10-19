"""Repository-driven desktop setup; no source account or exported profiles."""
import argparse
import hashlib
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
HOME = Path.home()
STATE = HOME / '.local/state/mintbook/setup.json'
CHANNELS = ('xsettings', 'xfwm4', 'xfce4-desktop', 'xfce4-panel', 'xfce4-keyboard-shortcuts', 'xfce4-power-manager')
DOCK_PATH = '/net/launchpad/plank/docks/dock1/'


def run(*args, **kwargs):
    return subprocess.run(args, check=True, text=True, capture_output=True, timeout=180, **kwargs)


def manifest(root=None):
    root = ROOT if root is None else root
    data = json.loads((root / 'config/desktop.json').read_text())
    if data.get('schema') != 1:
        raise ValueError('unsupported desktop setup schema')
    for name in data['features']:
        if '/' in name or not name.endswith('-install') or not (root / 'bin' / name).is_file():
            raise ValueError('missing feature installer: ' + name)
    for theme in data['themes']:
        if len(theme['commit']) != 40 or any(c not in '0123456789abcdef' for c in theme['commit']):
            raise ValueError('theme revision must be an exact commit')
    return data


class Xfconf:
    def __init__(self):
        import gi
        from gi.repository import Gio, GLib
        self.GLib = GLib
        self.proxy = Gio.DBusProxy.new_for_bus_sync(
            Gio.BusType.SESSION, Gio.DBusProxyFlags.NONE, None,
            'org.xfce.Xfconf', '/org/xfce/Xfconf', 'org.xfce.Xfconf', None)

    def call(self, method, signature, value):
        from gi.repository import Gio
        return self.proxy.call_sync(method, self.GLib.Variant(signature, value), Gio.DBusCallFlags.NONE, 10000, None)

    def snapshot(self):
        result = {}
        for channel in CHANNELS:
            rows = self.call('GetAllProperties', '(ss)', (channel, '/')).get_child_value(0)
            result[channel] = {}
            for index in range(rows.n_children()) if rows is not None else []:
                row = rows.get_child_value(index)
                key = row.get_child_value(0).unpack()
                value = row.get_child_value(1).get_variant()
                result[channel][key] = [value.get_type_string(), value.print_(True)]
        return result

    def variant(self, signature, value):
        if signature.startswith('a') and signature != 'av':
            return self.GLib.Variant('av', [self.GLib.Variant(signature[1:], item) for item in value])
        return self.GLib.Variant(signature, value)

    def set(self, channel, prop, signature, value):
        self.call('SetProperty', '(ssv)', (channel, prop, self.variant(signature, value)))

    def restore(self, channels):
        current = self.snapshot()
        for channel, properties in channels.items():
            for prop in sorted(set(current.get(channel, {})) - set(properties), key=lambda item: item.count('/'), reverse=True):
                self.call('ResetProperty', '(ssb)', (channel, prop, False))
            # Parents before children: plugins can be strings with children.
            for prop, (signature, text) in sorted(properties.items(), key=lambda pair: pair[0].count('/')):
                value = self.GLib.Variant.parse(self.GLib.VariantType(signature), text, None, None)
                self.call('SetProperty', '(ssv)', (channel, prop, value))


def load_module(name):
    path = ROOT / 'bin' / name
    loader = importlib.machinery.SourceFileLoader('mintbook_setup_' + name.replace('-', '_'), str(path))
    result = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(result)
    return result


def dependencies(data):
    result = subprocess.run(['dpkg-query', '-W', '-f=${binary:Package}\t${Status}\n', *data['packages']],
                            text=True, capture_output=True, timeout=20)
    installed = {line.split('\t')[0].split(':')[0] for line in result.stdout.splitlines() if line.endswith('\tinstall ok installed')}
    return [name for name in data['packages'] if name not in installed]


def ensure_themes(data, check=False):
    needed = []
    stamp = HOME / '.local/state/mintbook/themes.json'
    old = json.loads(stamp.read_text()) if stamp.exists() else {}
    for theme in data['themes']:
        build_inputs = dict(theme, patch_hashes={name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in theme.get('patches', [])})
        identity = hashlib.sha256(json.dumps(build_inputs, sort_keys=True).encode()).hexdigest()
        required = (HOME / '.themes/WhiteSur-Light/gtk-3.0/gtk.css', HOME / '.icons/WhiteSur-light/index.theme')
        marker = required[0 if theme['name'] == 'WhiteSur-gtk-theme' else 1]
        if old.get(theme['name']) == identity and marker.exists():
            continue
        needed.append(theme['name'])
        if check:
            continue
        cache = HOME / '.cache/mintbook/themes' / (theme['name'] + '-' + theme['commit'])
        if not cache.exists():
            cache.mkdir(parents=True)
            run('git', 'init', str(cache))
            run('git', '-C', str(cache), 'remote', 'add', 'origin', theme['url'])
        run('git', '-C', str(cache), 'fetch', '--depth=1', 'origin', theme['commit'])
        run('git', '-C', str(cache), 'checkout', '--detach', theme['commit'])
        if run('git', '-C', str(cache), 'rev-parse', 'HEAD').stdout.strip() != theme['commit']:
            raise ValueError('theme revision verification failed')
        # Re-create pristine sources after an interrupted upstream build.
        run('git', '-C', str(cache), 'reset', '--hard', theme['commit'])
        for patch in theme.get('patches', []):
            run('git', '-C', str(cache), 'apply', '--unidiff-zero', '--check', str(ROOT / patch))
            run('git', '-C', str(cache), 'apply', '--unidiff-zero', str(ROOT / patch))
        args = [part.replace('@HOME@', str(HOME)) for part in theme['args']]
        result = run('bash', str(cache / 'install.sh'), *args,
                     cwd=cache, env={**os.environ, 'TERM': 'xterm-256color'})
        if not marker.exists():
            raise ValueError('theme installer did not produce ' + str(marker) + '\n' + result.stdout[-1000:])
        old[theme['name']] = identity
        stamp.parent.mkdir(parents=True, exist_ok=True)
        stamp.write_text(json.dumps(old, indent=2) + '\n')
    return needed


def backup_paths():
    # Only GUI/runtime paths modified by this recipe and its feature installers.
    paths = [f'.local/bin/{path.name}' for path in (ROOT / 'bin').iterdir() if path.is_file()]
    paths += [
        '.config/xfce4/panel', '.config/rofi', '.config/gtk-3.0/gtk.css',
        '.config/redshift.conf',
        '.config/plank/dock1/launchers', '.local/share/plank/themes/WhiteSur',
        '.local/share/mintbook/control-center', '.config/mintbook',
        '.local/lib/mintbook/current', '.local/lib/mintbook/manager',
        '.local/state/mintbook/panel-before.json', '.local/state/mintbook/desktop-install.json',
    ]
    paths += [f'.config/autostart/{name}' for name in
              ('plank.desktop', 'mintbook-panel.desktop', 'mintbook-night.desktop', 'mintupdate.desktop', 'nm-applet.desktop', 'blueman.desktop')]
    paths += [f'.config/systemd/user/{path.name}' for path in (ROOT / 'config/systemd').glob('mintbook-*') if path.is_file()]
    paths += [f'.local/share/applications/{name}' for name in ('mintbook-app-grid.desktop',)]
    # Timers enabled by daily/updates; save their enablement links too.
    for directory in ('timers.target.wants', 'paths.target.wants'):
        for name in ('mintbook-health.timer', 'mintbook-updates-check.timer', 'mintbook-updates-check.path'):
            paths.append('.config/systemd/user/' + directory + '/' + name)
    return paths


def snapshot(label):
    from mintbook_deploy import atomic_text
    backup = STATE.parent / (label + '-' + str(time.time_ns()))
    backup.mkdir(parents=True)
    data = {'files': [], 'channels': Xfconf().snapshot(),
            'dock': run('dconf', 'dump', DOCK_PATH).stdout,
            'plank_running': subprocess.run(['pgrep', '-u', str(os.getuid()), '-x', 'plank'], capture_output=True).returncode == 0,
            'units': {name: subprocess.run(['systemctl', '--user', 'is-active', name], capture_output=True).returncode == 0
                      for name in ('mintbook-health.timer', 'mintbook-updates-check.timer', 'mintbook-updates-check.path')}}
    for i, relative in enumerate(backup_paths()):
        target, saved = HOME / relative, backup / str(i)
        present = target.exists() or target.is_symlink()
        if present:
            if target.is_dir() and not target.is_symlink():
                shutil.copytree(target, saved, symlinks=True)
            else:
                shutil.copy2(target, saved, follow_symlinks=False)
        data['files'].append({'path': relative, 'backup': str(saved) if present else None})
    atomic_text(backup / 'snapshot.json', json.dumps(data, indent=2))
    return backup / 'snapshot.json'


def restore(snapshot_file):
    data = json.loads(Path(snapshot_file).read_text())
    for unit, active in data.get('units', {}).items():
        if not active:
            subprocess.run(['systemctl', '--user', 'stop', unit], capture_output=True, timeout=20)
    for row in reversed(data['files']):
        target = HOME / row['path']
        if target.is_symlink() or target.is_file():
            target.unlink()
        elif target.exists():
            shutil.rmtree(target)
        if row['backup']:
            source = Path(row['backup'])
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.is_dir() and not source.is_symlink():
                shutil.copytree(source, target, symlinks=True)
            else:
                shutil.copy2(source, target, follow_symlinks=False)
    Xfconf().restore(data['channels'])
    run('dconf', 'reset', '-f', DOCK_PATH)
    run('dconf', 'load', DOCK_PATH, input=data['dock'])
    run('systemctl', '--user', 'daemon-reload')
    for unit, active in data.get('units', {}).items():
        if active:
            run('systemctl', '--user', 'start', unit)
    if not data.get('plank_running', True):
        subprocess.run(['pkill', '-u', str(os.getuid()), '-x', 'plank'], capture_output=True)


def put(source, destination):
    mode = source.stat().st_mode & 0o777
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + '.setup-new')
    temporary.unlink(missing_ok=True)
    shutil.copy2(source, temporary)
    temporary.chmod(mode | 0o200)
    temporary.replace(destination)


def install_recipe():
    data = manifest()
    state = json.loads(STATE.read_text())
    options = state['pending_options']
    # All runtime modules travel together. Feature installers below own their
    # files, panel ordering and shortcut behavior, exactly as on existing users.
    for source in (ROOT / 'bin').iterdir():
        if source.is_file() and (source.suffix == '.py' or source.stat().st_mode & 0o111):
            put(source, HOME / '.local/bin' / source.name)
    xfconf = Xfconf()
    previous = state.get('defaults', {})
    current = xfconf.snapshot()
    applied = {}
    for channel, properties in data['settings'].items():
        for prop, (signature, value) in properties.items():
            if prop == '/Xft/DPI':
                value = options['dpi']
            if isinstance(value, str):
                value = value.replace('@HOME@', str(HOME))
            key = channel + ':' + prop
            # Layout structure belongs to the recipe. Appearance and DPI are
            # defaults on first install; later setup runs keep user changes.
            prior = previous.get(key)
            now = current.get(channel, {}).get(prop)
            variant = xfconf.variant(signature, value)
            desired = [variant.get_type_string(), variant.print_(True)]
            if channel in ('xfce4-panel', 'xfce4-keyboard-shortcuts') or prior is None or now == prior or options['reset_defaults'] or (prop == '/Xft/DPI' and options.get('dpi_explicit')):
                xfconf.set(channel, prop, signature, value)
                applied[key] = desired
            else:
                applied[key] = prior
    wallpaper = data.get('wallpaper')
    if wallpaper and Path(wallpaper).is_file():
        for prop, now in current.get('xfce4-desktop', {}).items():
            if prop.endswith('/last-image'):
                key = 'xfce4-desktop:' + prop
                prior = previous.get(key)
                if prior is None or now == prior or options['reset_defaults']:
                    xfconf.set('xfce4-desktop', prop, 's', wallpaper)
                    applied[key] = ['s', xfconf.variant('s', wallpaper).print_(True)]
                else:
                    applied[key] = prior
    state['defaults'] = applied
    for source in (ROOT / 'config/xfce4-panel').glob('genmon-*.rc'):
        target = HOME / '.config/xfce4/panel' / source.name
        if not target.exists():
            text = source.read_text()
            rows = text.splitlines()
            for index, row in enumerate(rows):
                if row.startswith('Command='):
                    component = Path(row.partition('=')[2].split()[0]).name
                    rows[index] = 'Command=' + str(HOME / '.local/bin' / component)
            from mintbook_deploy import atomic_text
            atomic_text(target, '\n'.join(rows) + '\n')
    if options.get('location'):
        load_module('night-config').prepare(HOME, options['location'])
    if (HOME / '.config/redshift.conf').exists():
        from mintbook_deploy import atomic_text
        template = (ROOT / 'config/autostart/mintbook-night.desktop').read_text()
        executable = str(HOME / '.local/bin/night-apply').replace('\\', '\\\\').replace('"', '\\"')
        atomic_text(HOME / '.config/autostart/mintbook-night.desktop',
                    template.replace('Exec=night-apply', f'Exec="{executable}"'))
    for name in ('config.rasi', 'spotlight.rasi'):
        put(ROOT / 'config/rofi' / name, HOME / '.config/rofi' / name)
    appearance = HOME / '.config/mintbook/appearance.mode'
    if not appearance.exists():
        appearance.parent.mkdir(parents=True, exist_ok=True)
        appearance.write_text('light\n')
    if not (HOME / '.config/rofi/palette.rasi').exists():
        put(ROOT / 'config/rofi/palette-light.rasi', HOME / '.config/rofi/palette.rasi')
    put(ROOT / 'config/autostart/plank.desktop', HOME / '.config/autostart/plank.desktop')
    put(ROOT / 'config/plank/WhiteSur/dock.theme', HOME / '.local/share/plank/themes/WhiteSur/dock.theme')
    for name in data['dock']['dock-items']:
        put(ROOT / 'config/plank' / name, HOME / '.config/plank/dock1/launchers' / name)
    dock = ['[/]']
    dock_defaults = state.get('dock_defaults', {})
    for key, value in data['dock'].items():
        if isinstance(value, bool):
            text = str(value).lower()
        else:
            text = repr(value)
        current_dock = run('gsettings', 'get', 'net.launchpad.plank.dock.settings:' + DOCK_PATH, key).stdout.strip()
        if key not in dock_defaults or current_dock == dock_defaults[key] or options['reset_defaults']:
            dock.append(key + '=' + text)
            dock_defaults[key] = text
    state['dock_defaults'] = dock_defaults
    run('dconf', 'load', DOCK_PATH, input='\n'.join(dock) + '\n')
    for name in data['features']:
        print('Configuring', name, flush=True)
        result = run(str(ROOT / 'bin' / name), env={**os.environ, 'MINTBOOK_INSTALL_TRANSACTION': '1', 'MINTBOOK_PANEL_MAINTENANCE': '1'})
        print(result.stdout, end='', flush=True)
    # This only affects the user: no automatic firmware, boot or power tuning.
    (HOME / '.config/mintbook/appearance.applied').unlink(missing_ok=True)
    run(str(ROOT / 'bin/appearance-mode'), '--refresh',
        env={**os.environ, 'MINTBOOK_PANEL_MAINTENANCE': '1'})
    STATE.write_text(json.dumps(state, indent=2) + '\n')


def preflight(data, install_deps=False, check_dependencies=True):
    if os.geteuid() == 0:
        raise ValueError('run bin/setup as the desktop user, without sudo')
    if not shutil.which('dpkg-query'):
        raise ValueError('setup supports Linux Mint with apt/dpkg')
    missing = dependencies(data) if check_dependencies else []
    if missing and install_deps:
        subprocess.run(['sudo', 'apt-get', 'update'], check=True)
        subprocess.run(['sudo', 'apt-get', 'install', '--', *missing], check=True)
        missing = dependencies(data)
    if missing:
        raise ValueError('missing packages: ' + ' '.join(missing) + '\nRun bin/setup --install-deps in your XFCE session.')
    panel = load_module('panel-session')
    if panel.session_pid() is None or os.environ.get('XDG_SESSION_TYPE') == 'wayland':
        raise ValueError('run bin/setup from a terminal in the target user\'s XFCE X11 session')
    run('systemctl', '--user', 'show-environment')
    return panel


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--install-deps', action='store_true', help='ask sudo to install missing distro packages')
    parser.add_argument('--check', action='store_true', help='report prerequisites without changing anything')
    parser.add_argument('--dpi', type=int, help='initial font DPI, e.g. 168 on the reference Retina display')
    parser.add_argument('--location', nargs=2, type=float, metavar=('LATITUDE', 'LONGITUDE'), help='set Night Light coordinates for a new configuration')
    parser.add_argument('--reset-defaults', action='store_true', help='reapply repository appearance defaults')
    parser.add_argument('--recover', action='store_true', help='restore a setup interrupted before it completed')
    parser.add_argument('--revert', action='store_true', help='restore the GUI settings from before setup')
    args = parser.parse_args(argv)
    if args.dpi is not None and not 72 <= args.dpi <= 288:
        parser.error('--dpi must be between 72 and 288')
    if args.check and args.install_deps:
        parser.error('--check cannot install dependencies')
    try:
        data = manifest()
        panel = preflight(data, args.install_deps, check_dependencies=not (args.revert or args.recover))
        if args.location:
            load_module('night-config').prepare(HOME, args.location, check=True)
        if args.check:
            needed = ensure_themes(data, check=True)
            print('Desktop prerequisites passed.')
            print('Pinned themes to install:', ', '.join(needed) or 'none')
            return 0
        from mintbook_deploy import Deployment, atomic_text
        deployment = Deployment(ROOT)
        lock = deployment.base / 'install.lock'
        lock.parent.mkdir(parents=True, exist_ok=True)
        import fcntl
        with lock.open('a') as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            state = json.loads(STATE.read_text()) if STATE.exists() else {}
            if state.get('pending'):
                if not args.recover:
                    raise ValueError('an interrupted setup needs recovery: run bin/setup --recover')
                panel.stop()
                restore(state.pop('pending'))
                state.pop('pending_options', None)
                atomic_text(STATE, json.dumps(state, indent=2))
                run('systemctl', '--user', 'daemon-reload')
                panel.start()
                print('Interrupted setup restored. You can rerun bin/setup.')
                return 0
            if args.recover:
                raise ValueError('no interrupted setup to recover')
            if args.revert:
                if 'original' not in state:
                    raise ValueError('no setup backup exists')
                panel.stop()
                restore(state['original'])
                run('systemctl', '--user', 'daemon-reload')
                STATE.unlink()
                panel.start()
                print('Original GUI settings restored. Downloaded themes remain installed.')
                return 0
            # Themes are immutable external dependencies selected by the repo.
            ensure_themes(data)
            recovery = snapshot('setup-run')
            state.setdefault('original', str(recovery))
            state['pending'] = str(recovery)
            initial_dpi = state.get('dpi', 96)
            if 'dpi' not in state:
                current_dpi = Xfconf().snapshot().get('xsettings', {}).get('/Xft/DPI')
                if current_dpi:
                    initial_dpi = int(Xfconf().GLib.Variant.parse(None, current_dpi[1], None, None).unpack())
                if not 72 <= initial_dpi <= 288:
                    initial_dpi = 96
            state['pending_options'] = {'dpi': args.dpi or initial_dpi, 'reset_defaults': args.reset_defaults, 'dpi_explicit': args.dpi is not None, 'location': args.location}
            atomic_text(STATE, json.dumps(state, indent=2))
            try:
                release = deployment.transaction(['desktop-setup-install'])
                state = json.loads(STATE.read_text())
                state['dpi'] = state['pending_options']['dpi']
                state.pop('pending', None); state.pop('pending_options', None)
                state['release'] = release.name
                atomic_text(STATE, json.dumps(state, indent=2))
            except BaseException:
                panel.stop()
                restore(recovery)
                state.pop('pending', None); state.pop('pending_options', None)
                atomic_text(STATE, json.dumps(state, indent=2))
                run('systemctl', '--user', 'daemon-reload')
                panel.start()
                raise
        # Plank is session-owned, not a second resident management service.
        if subprocess.run(['pgrep', '-u', str(os.getuid()), '-x', 'plank'], capture_output=True).returncode == 1:
            subprocess.Popen(['plank'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        print('Mintbook desktop installed:', release.name)
        print('Update: git pull --ff-only && bin/setup')
        print('Undo desktop settings: bin/setup --revert')
        return 0
    except Exception as error:
        print('Setup failed:', error, file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError):
            print((error.stderr or '')[-2000:], file=sys.stderr)
        return 1
