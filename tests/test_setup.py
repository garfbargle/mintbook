"""A checkout defines setup, dependencies and updates; no source account is needed."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'bin'))
import mintbook_setup as setup
from mintbook_deploy import Deployment


class SetupTests(unittest.TestCase):
    def test_recipe_pins_themes_and_uses_existing_installers(self):
        data = setup.manifest()
        self.assertEqual(len(data['themes']), 2)
        for theme in data['themes']:
            self.assertRegex(theme['commit'], r'^[0-9a-f]{40}$')
        self.assertIn('control-install', data['features'])
        self.assertIn('overview-install', data['features'])
        self.assertEqual(data['features'][-1], 'app-grid-install')
        self.assertNotIn('/home/cobo', json.dumps(data))
        payload = Deployment(ROOT, Path('/tmp/unused-setup-home')).source_files()
        self.assertIn('config/desktop.json', payload)
        self.assertIn('bin/mintbook_setup.py', payload)

    def test_new_managed_files_join_original_undo_without_overwriting_old_backups(self):
        with tempfile.TemporaryDirectory() as tmp:
            original, recovery = Path(tmp) / 'original.json', Path(tmp) / 'run.json'
            old = {'path': '.config/autostart/nm-applet.desktop', 'backup': '/old/original'}
            original.write_text(json.dumps({'files': [old]}))
            added = {'path': '.config/autostart/mintreport.desktop', 'backup': None}
            recovery.write_text(json.dumps({'files': [dict(old, backup='/new/changed'), added]}))
            setup.extend_original_snapshot(original, recovery)
            setup.extend_original_snapshot(original, recovery)
            self.assertEqual(json.loads(original.read_text())['files'], [old, added])

    def test_multiarch_packages_count_as_installed(self):
        result = SimpleNamespace(stdout='python3\tinstall ok installed\ngir1.2-gtk-3.0:amd64\tinstall ok installed\n')
        with patch.object(setup.subprocess, 'run', return_value=result):
            self.assertEqual(setup.dependencies({'packages': ['python3', 'gir1.2-gtk-3.0', 'plank']}), ['plank'])

    def test_check_never_installs_dependencies(self):
        with patch.object(setup, 'preflight', side_effect=ValueError('missing packages')) as preflight:
            self.assertEqual(setup.main(['--check']), 1)
            self.assertFalse(preflight.call_args.args[1])

    def test_theme_cache_uses_exact_revision_and_rebuilds_after_pin_change(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(setup, 'HOME', Path(tmp)):
            theme = setup.manifest()['themes'][0]
            marker = Path(tmp) / '.themes/WhiteSur-Light/gtk-3.0/gtk.css'
            calls = []

            def run(*args, **kwargs):
                calls.append(args)
                if args[0] == 'bash':
                    marker.parent.mkdir(parents=True, exist_ok=True); marker.write_text('css')
                return SimpleNamespace(stdout=theme['commit'] + '\n')

            with patch.object(setup, 'run', side_effect=run):
                self.assertEqual(setup.ensure_themes({'themes': [theme]}), [theme['name']])
                fetch = [args for args in calls if 'fetch' in args][0]
                self.assertEqual(fetch[-1], theme['commit'])
                calls.clear()
                self.assertEqual(setup.ensure_themes({'themes': [theme]}), [])
                self.assertEqual(calls, [])
                changed = dict(theme, commit='a' * 40)
                self.assertEqual(setup.ensure_themes({'themes': [changed]}, check=True), [theme['name']])
                self.assertEqual(calls, [])

    def test_rejects_invalid_dpi_before_setup(self):
        with patch.object(setup, 'preflight') as preflight, self.assertRaises(SystemExit):
            setup.main(['--dpi', '0'])
        preflight.assert_not_called()


@unittest.skipUnless(shutil.which('dbus-run-session') and importlib.util.find_spec('gi'), 'needs private D-Bus and GTK bindings')
class PrivateSessionSetupTests(unittest.TestCase):
    def test_fresh_settings_feature_composition_and_preference_preservation(self):
        with tempfile.TemporaryDirectory() as tmp:
            home, source = Path(tmp) / 'natalia', Path(tmp) / 'checkout'
            home.mkdir(); (source / 'bin').mkdir(parents=True)
            shutil.copytree(ROOT / 'config', source / 'config')
            data = json.loads((source / 'config/desktop.json').read_text())
            events = Path(tmp) / 'events'
            wallpaper = Path(tmp) / 'wallpaper.png'; wallpaper.write_bytes(b'wallpaper-fixture')
            data['wallpaper'] = str(wallpaper)
            (source / 'config/desktop.json').write_text(json.dumps(data))
            for name in [*data['features'], 'appearance-mode']:
                script = source / 'bin' / name
                script.write_text('#!/usr/bin/env python3\nfrom pathlib import Path\n'
                                  f'with Path({str(events)!r}).open("a") as f: f.write({name!r} + "\\n")\n')
                script.chmod(0o755)
            config = home / '.config'; config.mkdir()
            worker = f'''
import sys, json
from pathlib import Path
sys.path.insert(0, {str(ROOT / 'bin')!r})
import mintbook_setup as s
s.ROOT = Path({str(source)!r})
s.HOME = Path({str(home)!r})
s.STATE = s.HOME / '.local/state/mintbook/setup.json'
s.STATE.parent.mkdir(parents=True)
s.STATE.write_text(json.dumps({{'pending_options': {{'dpi': 168, 'reset_defaults': False}}}}))
# Substitute only service/process controls; all XFCE/dconf I/O uses the
# private bus and temporary home. Never stop real user processes in this test.
from types import SimpleNamespace
real_run = s.subprocess.run
def isolated_run(command, **kwargs):
    if command[0] in ('systemctl', 'pgrep', 'pkill'):
        return SimpleNamespace(returncode=0, stdout='', stderr='')
    return real_run(command, **kwargs)
s.subprocess.run = isolated_run
xf = s.Xfconf()
xf.set('xfce4-desktop', '/backdrop/screen0/monitor0/workspace0/last-image', 's', '/old-wallpaper.png')
original = xf.snapshot()
backup = s.snapshot('test-original')
s.install_recipe()
actual = xf.snapshot()
assert actual['xsettings']['/Xft/DPI'] == ['i', '168'], actual['xsettings']
assert actual['xfce4-panel']['/panels'][0] == 'av'
for name in ('nm-applet.desktop', 'mintreport.desktop'):
    assert 'Hidden=true' in (s.HOME / '.config/autostart' / name).read_text()
assert {str(wallpaper)!r} in actual['xfce4-desktop']['/backdrop/screen0/monitor0/workspace0/last-image'][1]
assert {str(home)!r} in actual['xfce4-keyboard-shortcuts']['/commands/custom/<Shift><Super>numbersign'][1]
assert Path({str(events)!r}).read_text().splitlines() == {[*data['features'], 'appearance-mode']!r}
xf.set('xsettings', '/Gtk/FontName', 's', 'My Font 12')
xf.set('xfce4-desktop', '/backdrop/screen0/monitor0/workspace0/last-image', 's', '/my-wallpaper.png')
s.run('gsettings', 'set', 'net.launchpad.plank.dock.settings:' + s.DOCK_PATH, 'icon-size', '90')
recipe_path = s.ROOT / 'config/desktop.json'
recipe = json.loads(recipe_path.read_text())
recipe['settings']['xsettings']['/Net/ThemeName'] = ['s', 'WhiteSur-Dark']
recipe['settings']['xsettings']['/Gtk/FontName'] = ['s', 'Updated Default Font 10']
recipe_path.write_text(json.dumps(recipe))
s.install_recipe()
assert xf.snapshot()['xsettings']['/Net/ThemeName'][1] == "'WhiteSur-Dark'"
assert xf.snapshot()['xsettings']['/Gtk/FontName'][1] == "'My Font 12'"
assert xf.snapshot()['xfce4-desktop']['/backdrop/screen0/monitor0/workspace0/last-image'][1] == "'/my-wallpaper.png'"
assert s.run('gsettings', 'get', 'net.launchpad.plank.dock.settings:' + s.DOCK_PATH, 'icon-size').stdout.strip() == '90'
s.restore(backup)
assert not (s.HOME / '.config/rofi/config.rasi').exists()
assert not (s.HOME / '.config/autostart/nm-applet.desktop').exists()
assert not (s.HOME / '.config/autostart/mintreport.desktop').exists()
assert not (s.HOME / '.local/bin/control-install').exists()
assert xf.snapshot()['xsettings'].get('/Xft/DPI') == original['xsettings'].get('/Xft/DPI')
print('fresh setup, arrays, feature composition, preferences and restore passed')
'''
            env = dict(os.environ, HOME=str(home), XDG_CONFIG_HOME=str(config),
                       XDG_CACHE_HOME=str(home / '.cache'), XDG_DATA_HOME=str(home / '.local/share'))
            result = subprocess.run(['dbus-run-session', '--', sys.executable, '-c', worker],
                                    env=env, text=True, capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
