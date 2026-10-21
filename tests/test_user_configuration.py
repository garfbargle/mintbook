"""Account-specific launchers and location setup must work outside the author's home."""
import importlib.machinery
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, mock_open
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    loader = importlib.machinery.SourceFileLoader(name.replace('-', '_') + '_config_test', str(ROOT / 'bin' / name))
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(module)
    return module


night = load('night-config')
drop = load('mintdrop-install')
apply = load('night-apply')


class UserConfigurationTests(unittest.TestCase):
    def test_dock_launcher_uses_each_account_and_encodes_spaces(self):
        template = ROOT / 'config/plank/07-mintdrop.dockitem'
        original = template.read_bytes()
        with tempfile.TemporaryDirectory() as tmp:
            for user in ('alice', 'bob smith'):
                home = Path(tmp) / user
                apps = home / '.local/share/applications'
                dest = home / '.config/plank/dock1/launchers/07-mintdrop.dockitem'
                dest.parent.mkdir(parents=True)
                # Replace an old checkout link without modifying its target.
                dest.symlink_to(template)
                with patch.object(drop, 'APPS', apps):
                    drop.install_file(template, dest)
                    drop.install_file(template, dest)
                self.assertFalse(dest.is_symlink())
                self.assertIn('Launcher=' + (apps / 'mintbook-mintdrop.desktop').as_uri(), dest.read_text())
        self.assertEqual(template.read_bytes(), original)

    def test_fresh_location_is_explicit_and_preflight_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, 'needs your location'):
                night.prepare(tmp)
            for invalid in ((91, 0), (0, -181), (float('nan'), 0), (0, float('inf'))):
                with self.assertRaises(ValueError):
                    night.prepare(tmp, invalid)
            target = night.prepare(tmp, (51.5, -0.12), check=True)
            self.assertFalse(target.exists())
            night.prepare(tmp, (51.5, -0.12))
            self.assertIn('lat=51.5\nlon=-0.12', target.read_text())
            self.assertNotIn('@', target.read_text())

    def test_rerun_retains_existing_location_and_preferences(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = night.prepare(tmp, (-33.86, 151.2))
            target.write_text(target.read_text().replace('3500', '4200'))
            original = target.read_bytes()
            night.prepare(tmp)
            with self.assertRaisesRegex(ValueError, 'already exists'):
                night.prepare(tmp, (9.93, -84.08))
            self.assertEqual(target.read_bytes(), original)

    def test_redshift_cleanup_ignores_other_users(self):
        with patch.object(apply.os, 'listdir', return_value=['10', '20']), \
                patch.object(apply.os, 'getuid', return_value=1000), \
                patch.object(apply.os, 'stat', side_effect=[SimpleNamespace(st_uid=1001), SimpleNamespace(st_uid=1000)]), \
                patch('builtins.open', mock_open(read_data=b'/usr/bin/redshift\0-c\0config\0')):
            self.assertEqual(apply.redshift_daemon_pids(), [20])

    def test_shipped_configuration_has_no_author_home_paths(self):
        for path in (ROOT / 'config').rglob('*'):
            if path.is_file():
                self.assertNotIn(b'/home/cobo', path.read_bytes(), str(path))


if __name__ == '__main__':
    unittest.main()
