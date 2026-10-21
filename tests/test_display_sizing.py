"""Primary-display transitions, remembered preferences and failed writes."""
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
loader = importlib.machinery.SourceFileLoader('display_sizing', str(ROOT / 'bin/display-session'))
spec = importlib.util.spec_from_loader(loader.name, loader)
m = importlib.util.module_from_spec(spec)
loader.exec_module(m)
BASE = dict(dpi=168, cursor=40, panel=52, icons=36, margin=52)
LAPTOP = dict(key='internal:hidpi', name='Laptop', internal=True, density=188)
WIDE = dict(key='wide:standard', name='Ultrawide', internal=False, density=110)


class Backend:
    def __init__(self):
        self.settings = dict(BASE)
        self.writes = 0

    def read(self):
        return dict(self.settings)

    def apply(self, settings):
        self.writes += 1
        self.settings = dict(settings)


class DisplaySizingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'display-sizing.json'
        self.backend = Backend()
        self.sizing = m.Sizing(self.backend, self.path)

    def test_monitor_identity_survives_connector_changes(self):
        first = 'DP-1 connected primary\n\tEDID:\n\t\t' + 'ab' * 16 + '\n'
        second = first.replace('DP-1', 'DP-3')
        self.assertEqual(m.monitor_edid(first, 'DP-1'), m.monitor_edid(second, 'DP-3'))
        self.assertNotEqual(m.monitor_edid(first, 'DP-1'), m.monitor_edid(first.replace('ab', 'cd'), 'DP-1'))
        self.assertIsNone(m.monitor_edid(first, 'eDP-1'))

    def test_docking_and_unplug_restore_laptop_settings(self):
        self.sizing.apply(WIDE)
        self.assertEqual(self.backend.settings['dpi'], 96)
        self.assertEqual(self.backend.settings['panel'], self.backend.settings['margin'])
        self.sizing.apply(LAPTOP)
        self.assertEqual(self.backend.settings, BASE)

    def test_new_standard_and_hidpi_displays(self):
        for density in (0, 96, 110, 999):
            self.assertEqual(m.default_profile(BASE, dict(internal=False, density=density))['dpi'], 96)
        self.assertEqual(m.default_profile(BASE, dict(internal=False, density=220)), BASE)

    def test_repeated_events_do_not_write_or_erase_manual_edits(self):
        self.sizing.apply(WIDE)
        self.backend.settings['dpi'] = 108
        writes = self.backend.writes
        self.assertFalse(self.sizing.apply(WIDE))
        self.assertEqual(self.backend.writes, writes)
        self.sizing.apply(LAPTOP)
        self.sizing.apply(WIDE)
        self.assertEqual(self.backend.settings['dpi'], 108)

    def test_manual_preference_is_saved_before_service_restart(self):
        self.sizing.apply(WIDE)
        self.backend.settings['dpi'] = 120
        self.sizing.remember()
        fresh = m.Sizing(self.backend, self.path)
        self.backend.settings['dpi'] = 96
        fresh.apply(WIDE)
        self.assertEqual(self.backend.settings['dpi'], 120)
        metrics = json.loads(self.path.with_name('bar-sizing.json').read_text())
        self.assertEqual(metrics['canvas'], 25)

    def test_restart_preserves_retina_baseline(self):
        self.sizing.apply(WIDE)
        fresh = m.Sizing(self.backend, self.path)
        fresh.apply(LAPTOP)
        self.assertEqual(self.backend.settings, BASE)

    def test_no_primary_during_hotplug_does_not_change_settings(self):
        self.assertFalse(self.sizing.apply(None))
        self.assertEqual(self.backend.writes, 0)

    def test_failed_apply_does_not_publish_new_profile(self):
        before = self.path.read_text()
        self.backend.apply = Mock(side_effect=RuntimeError('locked property'))
        with self.assertRaises(RuntimeError):
            self.sizing.apply(WIDE)
        self.assertIsNone(self.sizing.active)
        self.assertEqual(self.path.read_text(), before)

    def test_failed_save_restores_settings(self):
        with patch.object(m, 'save', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.sizing.apply(WIDE)
        self.assertEqual(self.backend.settings, BASE)
        self.assertIsNone(self.sizing.active)

    def test_appearance_is_preserved_and_other_themes_are_untouched(self):
        self.assertEqual(m.theme_for('WhiteSur-Dark-hdpi', 96), 'WhiteSur-Dark')
        self.assertEqual(m.theme_for('WhiteSur-Light', 168), 'WhiteSur-Light-hdpi')
        self.assertEqual(m.theme_for('OtherTheme', 96), 'OtherTheme')


if __name__ == '__main__':
    unittest.main()
