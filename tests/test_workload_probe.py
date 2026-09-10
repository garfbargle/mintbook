"""Interrupting a profile experiment must restore the user's power service."""
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

loader = importlib.machinery.SourceFileLoader('workload_probe', str(Path(__file__).parents[1] / 'bin/workload-probe'))
probe = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
loader.exec_module(probe)


class CleanupTests(unittest.TestCase):
    def setUp(self):
        sensor = patch.object(probe, 'package_sensor', return_value=Path('/unused'))
        cap = patch.object(probe, 'CAP', Mock(read_text=Mock(return_value='100')))
        sensor.start()
        cap.start()
        self.addCleanup(sensor.stop)
        self.addCleanup(cap.stop)

    def test_interrupted_work_restores_profile_and_previously_active_service(self):
        with tempfile.TemporaryDirectory() as d:
            output = Path(d) / 'result.json'
            with patch('sys.argv', ['workload-probe', str(output)]), \
                    patch.object(probe, 'sources', return_value=[('x', b'pass')]), \
                    patch.object(probe, 'command', return_value='balanced') as command, \
                    patch.object(probe.subprocess, 'run', return_value=Mock(returncode=0)), \
                    patch.object(probe, 'profile') as profile, \
                    patch.object(probe, 'sample', return_value={}), \
                    patch.object(probe, 'compile_all', side_effect=KeyboardInterrupt), \
                    patch.object(probe.time, 'sleep'), \
                    patch.object(probe.signal, 'signal'):
                with self.assertRaises(KeyboardInterrupt):
                    probe.main()
            self.assertEqual(profile.call_args_list[-1].args, ('balanced',))
            self.assertIn(('systemctl', '--user', 'start', probe.TURBO), [c.args for c in command.call_args_list])
            self.assertTrue(json.loads(output.read_text())['turbo_active_after'])

    def test_power_restore_error_still_restarts_turbo_service(self):
        with tempfile.TemporaryDirectory() as d:
            with patch('sys.argv', ['workload-probe', str(Path(d) / 'result.json')]), \
                    patch.object(probe, 'sources', return_value=[('x', b'pass')]), \
                    patch.object(probe, 'command', return_value='balanced') as command, \
                    patch.object(probe.subprocess, 'run', return_value=Mock(returncode=0)), \
                    patch.object(probe, 'profile', side_effect=[KeyboardInterrupt, RuntimeError('channel unavailable')]), \
                    patch.object(probe.signal, 'signal'):
                with self.assertRaisesRegex(RuntimeError, 'channel unavailable'):
                    probe.main()
            self.assertIn(('systemctl', '--user', 'start', probe.TURBO), [c.args for c in command.call_args_list])
