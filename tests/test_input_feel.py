"""Undo must survive reruns, partial writes, and originally absent XFCE overrides."""
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'bin/input-feel'
loader = SourceFileLoader('input_feel', str(SCRIPT))
feel = module_from_spec(spec_from_loader(loader.name, loader))
loader.exec_module(feel)


class InputFeel(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.saved = Path(self.temp.name) / 'input-feel.json'
        self.autostart = Path(self.temp.name) / 'autostart/mintbook-input-feel.desktop'
        self.live_values = [15, 200, 40]
        self.props = {feel.SETTINGS[0]: 200, feel.SETTINGS[1]: 40}
        self.commands = []
        self.fail_on = None
        self.patches = [patch.object(feel, 'SAVED', self.saved),
                        patch.object(feel, 'AUTOSTART', self.autostart),
                        patch.object(feel, 'run', self.command)]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def command(self, *argv):
        self.commands.append(argv)
        if argv[:2] == ('xinput', 'list-props'):
            return f'\t{feel.SCROLL_ATOM} (341):\t{self.live_values[0]}\n'
        if argv == ('xset', 'q'):
            return f'auto repeat delay: {self.live_values[1]} repeat rate: {self.live_values[2]}\n'
        if argv[:2] == ('xinput', 'set-prop'):
            self.live_values[0] = int(argv[-1])
        elif argv[:3] == ('xset', 'r', 'rate'):
            self.live_values[1:] = [int(value) for value in argv[-2:]]
        elif argv[0] == 'xfconf-query':
            channel = argv[2]
            if '-l' in argv:
                return '\n'.join(prop for chan, prop in self.props if chan == channel)
            key = (channel, argv[4])
            if '-s' in argv:
                if key == self.fail_on:
                    raise subprocess.CalledProcessError(1, argv, stderr='simulated write failure')
                self.props[key] = int(argv[-1])
                index = feel.SETTINGS.index(key) + 1
                self.live_values[index] = int(argv[-1])
            elif '-r' in argv:
                self.props.pop(key, None)
                # X11 retains its current value when the override is removed.
            else:
                return str(self.props[key]) + '\n'
        return ''

    def test_rerun_retains_original_snapshot(self):
        feel.install([30, 600, 25])
        original = self.saved.read_bytes()
        feel.install([40, 700, 20])
        self.assertEqual(self.saved.read_bytes(), original)
        feel.restore()
        self.assertEqual(self.live_values, [15, 200, 40])
        self.assertEqual(self.props[feel.SETTINGS[0]], 200)
        self.assertEqual(self.props[feel.SETTINGS[1]], 40)
        self.assertFalse(self.saved.exists())
        self.assertFalse(self.autostart.exists())

    def test_partial_failure_can_be_reverted(self):
        self.fail_on = feel.SETTINGS[1]
        with self.assertRaises(subprocess.CalledProcessError):
            feel.install([30, 600, 25])
        self.assertTrue(self.saved.exists())
        self.assertEqual(self.live_values[1], 600)
        self.fail_on = None
        feel.restore()
        self.assertEqual(self.live_values, [15, 200, 40])

    def test_absent_keyboard_overrides_restore_live_values(self):
        self.props.clear()
        self.live_values = [15, 500, 20]
        feel.install([30, 600, 25])
        feel.restore()
        self.assertEqual(self.props, {})
        self.assertEqual(self.live_values, [15, 500, 20])

    def test_existing_scroll_override_is_restored(self):
        self.autostart.parent.mkdir()
        self.autostart.write_text('previous login setting\n')
        self.live_values[0] = 22
        feel.install([30, 600, 25])
        feel.restore()
        self.assertEqual(self.autostart.read_text(), 'previous login setting\n')
        self.assertEqual(self.live_values[0], 22)

    def test_login_setting_matches_live_scroll_distance(self):
        feel.install([40, 600, 25])
        self.assertIn(f'Exec=xinput set-prop "{feel.DEVICE}" "{feel.SCROLL_ATOM}" 40\n',
                      self.autostart.read_text())
        self.assertEqual(self.live_values[0], 40)
        self.assertFalse(any('pointers' in argv for argv in self.commands))

    def test_existing_autostart_symlink_is_restored(self):
        self.autostart.parent.mkdir()
        self.autostart.symlink_to('original.desktop')
        feel.install([30, 600, 25])
        self.assertFalse(self.autostart.is_symlink())
        feel.restore()
        self.assertTrue(self.autostart.is_symlink())
        self.assertEqual(self.autostart.readlink(), Path('original.desktop'))

    def test_failed_verification_retains_undo(self):
        with patch.object(feel, 'verify', side_effect=RuntimeError('not applied')):
            with self.assertRaises(RuntimeError):
                feel.install([30, 600, 25])
        self.assertTrue(self.saved.exists())

    def test_unavailable_session_does_not_create_snapshot(self):
        with patch.object(feel, 'live', side_effect=RuntimeError('no display')):
            with self.assertRaises(RuntimeError):
                feel.install([30, 600, 25])
        self.assertFalse(self.saved.exists())
        self.assertFalse(self.commands)

    def test_unavailable_session_leaves_revert_snapshot(self):
        feel.install([30, 600, 25])
        original = self.saved.read_bytes()
        self.commands.clear()
        with patch.object(feel, 'live', side_effect=RuntimeError('no display')):
            with self.assertRaises(RuntimeError):
                feel.restore()
        self.assertEqual(self.saved.read_bytes(), original)
        self.assertFalse(self.commands)

    def test_check_does_not_write(self):
        with patch.object(feel, 'preflight'), patch('sys.argv', [str(SCRIPT), '--check']):
            self.assertEqual(feel.main(), 0)
        self.assertFalse(self.saved.exists())
        self.assertFalse(any('-s' in argv or '-r' in argv for argv in self.commands))


if __name__ == '__main__':
    unittest.main()
