"""Targeted helper installation uses temporary files and mocked system backends."""
import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def installer():
    loader = importlib.machinery.SourceFileLoader('safety_installer', str(ROOT / 'bin/safety-install'))
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(module)
    return module


class TargetedInstallation(unittest.TestCase):
    def exercise(self, snapshot=False, fail_snapshot=False):
        module = installer()
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            targets = {name: base / name for name in module.TARGETS}
            for path in targets.values():
                path.write_text('previous ' + path.name)
                path.chmod(0o640)
            backups = base / 'backups'
            calls = []

            def run(argv, **kwargs):
                calls.append(argv)
                if argv[0] == 'timeshift':
                    self.assertFalse(backups.exists())
                    for path in targets.values():
                        self.assertEqual(path.read_text(), 'previous ' + path.name)
                    if fail_snapshot:
                        raise subprocess.CalledProcessError(1, argv)
                return subprocess.CompletedProcess(argv, 0)

            args = ['safety-install'] + (['--snapshot'] if snapshot else [])
            with patch.multiple(module, TARGETS=targets, BACKUPS=backups), \
                 patch.object(module.os, 'geteuid', return_value=0), \
                 patch.dict(os.environ, {'PKEXEC_UID': '1000'}), \
                 patch.object(module.pwd, 'getpwuid', return_value=types.SimpleNamespace(pw_gid=os.getgid())), \
                 patch.object(module.subprocess, 'run', side_effect=run), \
                 patch.object(sys, 'argv', args), contextlib.redirect_stdout(io.StringIO()) as out:
                if fail_snapshot:
                    with self.assertRaises(subprocess.CalledProcessError): module.main()
                else:
                    module.main()
            if fail_snapshot:
                self.assertFalse(backups.exists())
                for path in targets.values():
                    self.assertEqual(path.read_text(), 'previous ' + path.name)
                return calls
            folders = list(backups.iterdir())
            self.assertEqual(len(folders), 1)
            backup = folders[0]
            self.assertEqual({p.name for p in backup.iterdir()}, set(targets) | {'manifest.json'})
            manifest = json.loads((backup / 'manifest.json').read_text())
            for name, path in targets.items():
                self.assertEqual((backup / name).read_text(), 'previous ' + name)
                self.assertTrue(manifest[name]['present'])
                self.assertEqual(manifest[name]['mode'], 0o640)
            for name in ('login-apply', 'power-apply'):
                self.assertEqual(targets[name].read_bytes(), (ROOT / 'bin' / name).read_bytes())
                self.assertEqual(targets[name].stat().st_mode & 0o777, 0o755)
            self.assertNotIn('@SESSION_GROUP@', targets['power.conf'].read_text())
            self.assertEqual(targets['power.conf'].stat().st_mode & 0o777, 0o644)
            self.assertIn('--revert ' + str(backup), out.getvalue())
            self.assertEqual(calls[-1], [str(targets['power-apply']), '--reassert'])
            return calls

    def test_default_has_exact_backups_and_no_full_snapshot(self):
        calls = self.exercise()
        self.assertFalse(any(c[0] in ('timeshift', 'rsync') for c in calls))

    def test_full_snapshot_requires_explicit_option(self):
        calls = self.exercise(snapshot=True)
        self.assertEqual(sum(c[0] == 'timeshift' for c in calls), 1)

    def test_requested_snapshot_failure_changes_nothing(self):
        self.exercise(snapshot=True, fail_snapshot=True)


if __name__ == '__main__':
    unittest.main()
