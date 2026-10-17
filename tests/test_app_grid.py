"""The application grid keeps daily apps visible and tidies away control panels."""
import importlib.machinery
import importlib.util
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
loader = importlib.machinery.SourceFileLoader('app_grid', str(ROOT / 'bin' / 'app-grid'))
spec = importlib.util.spec_from_loader(loader.name, loader)
app_grid = importlib.util.module_from_spec(spec)
loader.exec_module(app_grid)


class App:
    def __init__(self, app_id, categories='', name=None):
        self.app_id = app_id
        self.categories = categories
        self.name = name or app_id

    def get_id(self):
        return self.app_id

    def get_categories(self):
        return self.categories

    def get_display_name(self):
        return self.name


class GroupingTests(unittest.TestCase):
    def test_desktop_control_panels_go_in_settings(self):
        app = App('display.desktop', 'XFCE;Settings;HardwareSettings;')
        self.assertEqual(app_grid.AppGrid.group_for_app(app), 'settings')

    def test_important_software_tools_stay_in_the_main_grid(self):
        app = App('mintupdate.desktop', 'System;Settings;')
        self.assertIsNone(app_grid.AppGrid.group_for_app(app))

    def test_known_advanced_utilities_go_in_system_tools(self):
        app = App('xfce4-taskmanager.desktop', 'System;Utility;')
        self.assertEqual(app_grid.AppGrid.group_for_app(app), 'system')

    def test_regular_apps_stay_in_the_main_grid(self):
        app = App('firefox.desktop', 'Network;WebBrowser;')
        self.assertIsNone(app_grid.AppGrid.group_for_app(app))

    def test_every_app_appears_in_exactly_one_group(self):
        apps = [
            App('firefox.desktop', 'Network;', 'Firefox'),
            App('display.desktop', 'Settings;', 'Display'),
            App('btop.desktop', 'System;', 'btop++'),
        ]
        grouped = app_grid.AppGrid.group_applications(apps)
        self.assertEqual(sum(map(len, grouped.values())), len(apps))
        self.assertEqual(grouped[None], [apps[0]])
        self.assertEqual(grouped['settings'], [apps[1]])
        self.assertEqual(grouped['system'], [apps[2]])

    def test_folder_preview_caps_at_four_apps(self):
        apps = [App(f'app-{i}.desktop') for i in range(6)]
        self.assertEqual(app_grid.AppGrid.folder_preview_apps(apps), apps[:4])

    def test_preview_appearance_override_selects_requested_mode(self):
        with patch.dict(app_grid.os.environ, {'MINTBOOK_PREVIEW_APPEARANCE': 'dark'}):
            self.assertEqual(app_grid.read_mode(), 'dark')
        with patch.dict(app_grid.os.environ, {'MINTBOOK_PREVIEW_APPEARANCE': 'light'}):
            self.assertEqual(app_grid.read_mode(), 'light')

    def test_inline_session_confirmation_requires_second_confirm_and_cancels_on_escape(self):
        grid = app_grid.AppGrid.__new__(app_grid.AppGrid)
        grid.pending_action = None
        grid.current_group = None
        grid.handing_off = False
        ran = []
        grid.run_session_command = ran.append
        grid.session_action(None, 'Log Out', ['xfce4-session-logout', '--logout'], True)
        self.assertEqual(grid.pending_action, ('Log Out', ['xfce4-session-logout', '--logout']))
        self.assertEqual(ran, [])

        # Escape cancels the pending confirmation before closing the window
        destroyed = []
        grid.win = NS(destroy=lambda: destroyed.append(True))
        handled = grid.on_key(None, NS(keyval=app_grid.Gdk.KEY_Escape, state=0))
        self.assertTrue(handled)
        self.assertIsNone(grid.pending_action)
        self.assertEqual(destroyed, [])

        # Confirming runs the command once
        grid.session_action(None, 'Restart', ['xfce4-session-logout', '--reboot'], True)
        grid.execute_pending_action()
        self.assertEqual(ran, [['xfce4-session-logout', '--reboot']])
        self.assertIsNone(grid.pending_action)


if __name__ == '__main__':
    unittest.main()
