"""The application grid keeps daily apps visible and tidies away control panels."""
import importlib.machinery
import importlib.util
from pathlib import Path
import unittest


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


if __name__ == '__main__':
    unittest.main()
