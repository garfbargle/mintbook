"""Self-contained desktop releases and one reversible activation boundary."""
import hashlib
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

TREES = ('bin', 'icons', 'config', 'control-center', 'vendor')
CORE = {'desktop-install', 'desktop-status', 'panel-read', 'panel-session', 'mintbook_deploy.py'}
STATUS_NAMES = {'cpu', 'temp', 'wifi', 'bt', 'battery', 'system', 'control', 'overview'}


def run(*args, check=True, timeout=30):
    return subprocess.run(args, check=check, timeout=timeout, capture_output=True, text=True)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def git_blob(data):
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def atomic_text(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.new')
    temporary.write_text(value)
    temporary.replace(path)


def atomic_link(target, source):
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + '.new')
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(source)
    temporary.replace(target)


def load_panel(root):
    loader = importlib.machinery.SourceFileLoader('mintbook_install_panel', str(root / 'bin/panel-session'))
    result = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(result)
    return result


class Deployment:
    def __init__(self, root, home=None):
        self.root = Path(root).resolve()
        self.home = Path.home() if home is None else Path(home)
        self.base = self.home / '.local/lib/mintbook'
        self.releases = self.base / 'releases'
        self.current = self.base / 'current'
        self.state = self.home / '.local/state/mintbook/desktop-install.json'
        self.panel = None

    def source_files(self):
        result = {}
        for tree in TREES:
            for path in (self.root / tree).rglob('*'):
                if not path.is_file() or '__pycache__' in path.parts or path.suffix == '.pyc':
                    continue
                if not path.resolve().is_relative_to(self.root):
                    raise ValueError('runtime source leaves its checkout: ' + str(path))
                result[str(path.relative_to(self.root))] = (path.read_bytes(), path.stat().st_mode & 0o777)
        return result

    def installed_paths(self):
        result = {}
        for path in (self.home / '.local/bin').glob('*'):
            if path.name in CORE or (self.root / 'bin' / path.name).is_file():
                if path.is_file(): result['bin/' + path.name] = path
        for path in (self.home / '.local/share/mintbook/control-center/plugins').glob('*'):
            if path.is_file(): result['control-center/plugins/' + path.name] = path
        for path in (self.home / '.config/systemd/user').glob('mintbook-*'):
            if path.is_file() and (self.root / 'config/systemd' / path.name).is_file():
                result['config/systemd/' + path.name] = path
        for path in (self.home / '.config/autostart').glob('mintbook-*'):
            if path.is_file() and (self.root / 'config/autostart' / path.name).is_file():
                result['config/autostart/' + path.name] = path
        for path in (self.home / '.config/xfce4/panel').glob('genmon-*.rc'):
            if path.is_file(): result['config/xfce4-panel/' + path.name] = path
        return result

    def known_blobs(self):
        result = run('git', '-C', str(self.root), 'rev-list', '--objects', '--all', '--', *TREES, check=False)
        return {line.split()[0] for line in result.stdout.splitlines() if line}

    def changed_paths(self):
        result = run('git', '-C', str(self.root), 'diff', '--name-only', 'origin/main', '--', *TREES, check=False)
        added = run('git', '-C', str(self.root), 'ls-files', '--others', '--exclude-standard', '--', *TREES, check=False)
        return set(result.stdout.splitlines() + added.stdout.splitlines())

    def payload(self, baseline=False):
        files = self.source_files()
        installed = self.installed_paths()
        overrides = []
        known = self.known_blobs() if not baseline else set()
        changed = self.changed_paths()
        for relative, path in installed.items():
            data = path.read_bytes()
            mode = path.stat().st_mode & 0o777
            # Preserve actual rc layout/fonts/periods; source templates are not
            # the user's configuration. The command is transformed below.
            if relative.startswith('config/xfce4-panel/'):
                files[relative] = (data, mode)
                continue
            if relative in ('bin/desktop-install', 'bin/mintbook_deploy.py', 'bin/panel-session'):
                continue  # lifecycle/deployment commands also operate a baseline
            if baseline or relative not in files:
                files[relative] = (data, mode)
            elif (relative not in changed and data != files[relative][0]
                  and git_blob(data) not in known):
                files[relative] = (data, mode)
                overrides.append(relative)
        if not baseline:
            for relative, (data, mode) in list(files.items()):
                if relative.startswith('config/xfce4-panel/') and relative in installed:
                    rows = data.decode().splitlines()
                    command = next((row.partition('=')[2].strip() for row in rows if row.startswith('Command=')), '')
                    component = Path(command.split()[0]).name if command else ''
                    if component == 'panel-read':
                        name = command.split()[-1]
                    else:
                        name = component.removeprefix('panel-')
                    if name in STATUS_NAMES:
                        rows = [('Command=' + str(self.home / '.local/bin/panel-read') + ' ' + name)
                                if row.startswith('Command=') else row for row in rows]
                        files[relative] = (('\n'.join(rows) + '\n').encode(), mode)
        return files, overrides

    def build(self, baseline=False):
        files, overrides = self.payload(baseline)
        hashes = {name: digest(data) for name, (data, _mode) in sorted(files.items())}
        targets = self.target_paths(files)
        content = digest(json.dumps({'files': hashes, 'targets': targets}, sort_keys=True).encode())[:16]
        commit = run('git', '-C', str(self.root), 'rev-parse', '--short=12', 'HEAD', check=False).stdout.strip() or 'local'
        identity = ('baseline-' if baseline else '') + commit + '-' + content
        target = self.releases / identity
        if target.exists():
            self.validate(target)
            return target
        self.releases.mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix='.stage-', dir=self.releases))
        try:
            for name, (data, mode) in files.items():
                path = stage / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
                path.chmod(mode)
            manifest = {'version': identity, 'commit': commit, 'created': time.time(),
                        'baseline': baseline, 'files': hashes, 'targets': targets, 'local_overrides': overrides}
            (stage / 'manifest.json').write_text(json.dumps(manifest, indent=2))
            # Syntax and embedded palette checks happen before switching code.
            for path in (stage / 'bin').glob('*'):
                if not path.is_file(): continue
                if path.suffix == '.py' or path.read_bytes().split(b'\n', 1)[0].startswith((b'#!/usr/bin/env python', b'#!/usr/bin/python')):
                    compile(path.read_bytes(), str(path), 'exec')
            self.validate(stage)
            # Read-only release payloads prevent legacy installers from
            # accidentally following a command symlink and editing active code.
            for path in stage.rglob('*'):
                if path.is_file(): path.chmod(0o555 if path.stat().st_mode & 0o111 else 0o444)
            stage.rename(target)
            return target
        finally:
            if stage.exists(): shutil.rmtree(stage)

    def validate(self, release):
        manifest = json.loads((release / 'manifest.json').read_text())
        allowed = (self.home / '.local/bin', self.home / '.local/share/mintbook/control-center/plugins',
                   self.home / '.config/systemd/user', self.home / '.config/autostart', self.home / '.config/xfce4/panel')
        for target in manifest['targets'].values():
            if not any(Path(target).is_relative_to(parent) for parent in allowed):
                raise ValueError('release target leaves desktop installation paths')
        for name, expected in manifest['files'].items():
            path = release / name
            if not path.resolve().is_relative_to(release.resolve()) or not path.is_file() or path.is_symlink():
                raise ValueError('release is not self-contained: ' + name)
            if digest(path.read_bytes()) != expected:
                raise ValueError('release file changed: ' + name)
        return manifest

    def target_paths(self, files):
        result = self.installed_paths()
        for name in CORE:
            result['bin/' + name] = self.home / '.local/bin' / name
        result['config/systemd/mintbook-panel.service'] = self.home / '.config/systemd/user/mintbook-panel.service'
        result['config/systemd/mintbook-appearance-refresh.service'] = self.home / '.config/systemd/user/mintbook-appearance-refresh.service'
        result['config/systemd/mintbook-status.service'] = self.home / '.config/systemd/user/mintbook-status.service'
        result['config/autostart/mintbook-panel.desktop'] = self.home / '.config/autostart/mintbook-panel.desktop'
        return {name: str(path) for name, path in result.items() if name in files}

    def destinations(self, release):
        manifest = self.validate(release)
        return {name: Path(path) for name, path in manifest['targets'].items()}

    def snapshot(self):
        if self.state.exists(): return json.loads(self.state.read_text())
        baseline = self.build(baseline=True)
        data = {'baseline': baseline.name, 'previous': None, 'current': None, 'files': []}
        for relative, path in self.destinations(baseline).items():
            data['files'].append({'relative': relative, 'path': str(path), 'present': path.exists() or path.is_symlink()})
        atomic_text(self.state, json.dumps(data, indent=2))
        return data

    def activate(self, release, data=None):
        self.validate(release)
        data = self.snapshot() if data is None else data
        previous = self.current.resolve() if self.current.exists() else self.releases / data['baseline']
        # On the first migration all bridges point at the prepared baseline.
        # Subsequent releases change one symlink; targets never point at Git.
        if not self.current.exists(): atomic_link(self.current, previous)
        destinations = self.destinations(release)
        if self.current.exists():
            for relative, path in self.destinations(self.current.resolve()).items():
                if relative not in destinations and path.is_symlink():
                    if str(path.readlink()).startswith(str(self.current) + '/'):
                        path.unlink()
        known = {entry['path'] for entry in data['files']}
        for relative, path in destinations.items():
            if str(path) not in known:
                data['files'].append({'relative': relative, 'path': str(path), 'present': path.exists() or path.is_symlink()})
            atomic_link(path, self.current / relative)
        atomic_link(self.current, release)
        if previous != release:
            data['previous'] = previous.name
        data['current'] = release.name
        atomic_text(self.state, json.dumps(data, indent=2))
        return previous

    def verify(self, timeout=15):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            owner = self.panel.bus_owner()
            ok = owner is not None and self.panel.unhealthy(owner) is None
            if ok and 'Wants=mintbook-status.service' in (self.current / 'config/systemd/mintbook-panel.service').read_text():
                heartbeat = self.home / '.cache/mintbook/status/heartbeat'
                try:
                    report = json.loads((heartbeat.parent / 'report.json').read_text())
                    ok = (int(heartbeat.read_text()) >= time.time()
                          and Path(report['release']).resolve() == self.current.resolve())
                except (OSError, ValueError, KeyError):
                    ok = False
            if ok: return
            time.sleep(.2)
        raise RuntimeError('new desktop did not become healthy within the activation budget')

    def transaction(self, feature=None):
        self.panel = load_panel(self.root)
        if self.panel.session_pid() is None:
            raise RuntimeError('run desktop-install from the matching XFCE session')
        data = self.snapshot()
        previous = self.current.resolve() if self.current.exists() else self.releases / data['baseline']
        self.panel.stop()
        try:
            if feature:
                # Legacy feature installers write rc/autostart/plugin files in
                # place. Materialize only settings, never the release payload.
                if self.current.exists():
                    for relative, target in self.destinations(self.current.resolve()).items():
                        if relative.startswith(('config/', 'control-center/')) and target.is_symlink():
                            content = target.read_bytes()
                            atomic_text(target, content.decode())
                            target.chmod(0o755 if relative.startswith('control-center/') else 0o644)
                name, *args = feature
                if '/' in name or not name.endswith('-install') or not (self.root / 'bin' / name).is_file():
                    raise ValueError('unknown desktop feature installer')
                result = subprocess.run([str(self.root / 'bin' / name), *args],
                    env=dict(os.environ, MINTBOOK_INSTALL_TRANSACTION='1', MINTBOOK_PANEL_MAINTENANCE='1'))
                if result.returncode:
                    raise RuntimeError(f'{name} failed ({result.returncode})')
            release = self.build()
            self.activate(release, data)
            run('systemctl', '--user', 'daemon-reload')
            self.panel.start()
            self.verify()
            return release
        except BaseException:
            self.panel.stop()
            self.activate(previous, data)
            run('systemctl', '--user', 'daemon-reload')
            self.panel.start()
            raise

    def rollback(self, baseline=False):
        data = json.loads(self.state.read_text())
        name = data['baseline'] if baseline else data.get('previous')
        if not name: raise RuntimeError('no previous release is recorded')
        release = self.releases / name
        self.validate(release)
        original = self.current.resolve()
        self.panel = load_panel(self.root)
        self.panel.stop()
        try:
            self.activate(release, data)
            run('systemctl', '--user', 'daemon-reload')
            self.panel.start()
            self.verify()
            return release
        except BaseException:
            self.panel.stop()
            self.activate(original, data)
            run('systemctl', '--user', 'daemon-reload')
            self.panel.start()
            raise
