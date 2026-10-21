"""Vector panel sizing must track text DPI without changing geometry or actions."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('bar_scaling', ROOT / 'bin/mintbook_bar.py')
bar = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bar)


class ScalingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'original.svg'
        self.source.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="48" height="34" viewBox="0 0 48 34"><path d="M1 2L3 4"/></svg>')
        self.prefs = self.root / 'sizing.json'
        self.markup = f'<click>menu</click><img>{self.source}</img><tool>Status</tool>'

    def render(self, dpi):
        self.prefs.write_text('{"dpi":' + str(dpi) + '}')
        text = bar.scale_images('wifi', self.markup, self.root, self.prefs)
        return text, ET.parse(self.root / 'images/wifi.svg').getroot()

    def test_normal_and_retina_sizes_share_the_same_geometry(self):
        text, normal = self.render(96)
        self.assertEqual(normal.get('height'), '20')
        self.assertEqual(normal.get('width'), '28')
        _, retina = self.render(168)
        self.assertEqual(retina.get('height'), '35')
        self.assertEqual(retina.get('viewBox'), normal.get('viewBox'))
        self.assertIn('<click>menu</click>', text)
        self.assertIn('<tool>Status</tool>', text)

    def test_manual_dpi_edit_resizes_existing_asset(self):
        self.render(96)
        _, svg = self.render(120)
        self.assertEqual(svg.get('height'), '25')

    def test_unchanged_asset_does_not_rewrite_the_file(self):
        self.render(96)
        path = self.root / 'images/wifi.svg'
        before = path.stat().st_mtime_ns
        self.render(96)
        self.assertEqual(path.stat().st_mtime_ns, before)

    def test_bad_or_missing_asset_keeps_clickable_original(self):
        self.source.write_text('invalid SVG')
        self.prefs.write_text('{"dpi":96}')
        self.assertEqual(bar.scale_images('wifi', self.markup, self.root, self.prefs), self.markup)
        self.source.unlink()
        self.assertEqual(bar.scale_images('wifi', self.markup, self.root, self.prefs), self.markup)

    def test_extreme_values_cannot_make_unbounded_images(self):
        self.assertEqual(bar.canvas_height(10000), 64)
        self.assertEqual(bar.canvas_height(1), 16)
        for value in (-1, None, float('nan'), float('inf')):
            self.assertEqual(bar.canvas_height(value), 20)


if __name__ == '__main__':
    unittest.main()
