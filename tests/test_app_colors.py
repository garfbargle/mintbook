"""An app's colour comes from its icon — the parts of that walk that are pure.

Gtk is not imported here: `dominant_pixels` takes the bytes a pixbuf would
have handed it, so the sampler can be tested without a display.
"""
import colorsys
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    loader = importlib.machinery.SourceFileLoader(
        name, str(ROOT / 'bin' / f'{name}.py'))
    module = importlib.util.module_from_spec(
        importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(module)
    return module


ac = load('mintbook_appcolor')

ENTRY = """[Desktop Entry]
Name=Cursor
Exec=/usr/share/cursor/cursor %F
Icon=co.anysphere.cursor
StartupWMClass=Cursor

[Desktop Action new-window]
Name=New Empty Window
Exec=/usr/share/cursor/cursor --new-window %F
Icon=wrong-icon
"""


def pixels(colors, alpha=255):
    """RGBA bytes for a 1-row image of `colors`."""
    data = bytearray()
    for r, g, b in colors:
        data += bytes((r, g, b, alpha))
    return bytes(data), len(colors)


class DesktopTests(unittest.TestCase):
    def test_only_the_entry_group_is_read(self):
        icon, keys = ac.parse_desktop(ENTRY)
        self.assertEqual(icon, 'co.anysphere.cursor')
        self.assertIn('cursor', keys)
        self.assertNotIn('new empty window', keys)

    def test_exec_keeps_the_binary_and_drops_the_field_codes(self):
        _icon, keys = ac.parse_desktop(
            '[Desktop Entry]\nIcon=x\nExec=env FOO=1 /usr/bin/firefox %u\n')
        self.assertIn('firefox', keys)
        self.assertNotIn('%u', keys)

    def test_an_entry_without_an_icon_is_not_indexed(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, 'a.desktop').write_text('[Desktop Entry]\nName=A\nExec=a\n')
            Path(d, 'b.desktop').write_text(ENTRY)
            index = ac.desktop_index([d])
        self.assertNotIn('a', index)
        self.assertEqual(index['cursor'], 'co.anysphere.cursor')

    def test_earlier_directories_win(self):
        with tempfile.TemporaryDirectory() as first, \
                tempfile.TemporaryDirectory() as second:
            Path(first, 'x.desktop').write_text('[Desktop Entry]\nName=X\nIcon=mine\n')
            Path(second, 'x.desktop').write_text('[Desktop Entry]\nName=X\nIcon=theirs\n')
            index = ac.desktop_index([first, second])
        self.assertEqual(index['x'], 'mine')


class CandidateTests(unittest.TestCase):
    def test_exe_comes_first_and_bin_is_stripped(self):
        got = ac.candidates(comm='Web Content', name='Firefox',
                            exe='/usr/lib/firefox/firefox-bin',
                            index={'firefox': 'firefox-icon'})
        self.assertEqual(got[0], 'firefox-bin')
        self.assertEqual(got[1], 'firefox-icon')

    def test_interpreters_are_not_looked_up(self):
        self.assertEqual(ac.candidates(comm='python3', name='python3'), [])

    def test_the_desktop_icon_beats_the_bare_name(self):
        got = ac.candidates(comm='claude-desktop', name='Claude',
                            index={'claude-desktop': 'claude-icon'})
        self.assertEqual(got[0], 'claude-icon')


class SamplerTests(unittest.TestCase):
    def test_a_solid_orange_reports_its_own_hue(self):
        data, width = pixels([(230, 120, 30)] * 40)
        hue, sat = ac.dominant_pixels(data, width, 1, width * 4, 4)
        self.assertAlmostEqual(hue, colorsys.rgb_to_hsv(230 / 255, 120 / 255, 30 / 255)[0],
                               places=2)
        self.assertGreater(sat, 0.8)

    def test_a_black_and_white_mark_has_no_colour(self):
        data, width = pixels([(0, 0, 0)] * 20 + [(255, 255, 255)] * 20)
        self.assertIsNone(ac.dominant_pixels(data, width, 1, width * 4, 4))

    def test_a_few_stray_pixels_do_not_make_a_colour(self):
        data, width = pixels([(20, 20, 20)] * 99 + [(255, 0, 0)])
        self.assertIsNone(ac.dominant_pixels(data, width, 1, width * 4, 4))

    def test_transparent_pixels_are_not_counted(self):
        opaque = bytes((240, 40, 40, 255)) * 10
        clear = bytes((0, 200, 0, 0)) * 90
        got = ac.dominant_pixels(opaque + clear, 100, 1, 400, 4)
        self.assertIsNotNone(got)
        self.assertLess(min(got[0], 1 - got[0]), 0.06)   # red, not the green

    def test_the_majority_colour_wins(self):
        data, width = pixels([(20, 90, 220)] * 30 + [(240, 60, 60)] * 6)
        hue, _sat = ac.dominant_pixels(data, width, 1, width * 4, 4)
        self.assertAlmostEqual(hue, 0.6, delta=0.04)


class TintTests(unittest.TestCase):
    def test_no_base_is_no_colour(self):
        self.assertIsNone(ac.tint(None))

    def test_each_appearance_gets_ink_it_can_carry(self):
        light = ac.tint((0.08, 0.7))
        dark = ac.tint((0.08, 0.7), dark=True)
        self.assertLess(sum(light), sum(dark))

    def test_a_shared_hue_moves_a_shade(self):
        first = ac.tint((0.04, 0.6))
        second = ac.tint((0.04, 0.6), step=1)
        self.assertNotEqual(first, second)
        self.assertLess(sum(second), sum(first))       # darker on pearl
        self.assertGreater(sum(ac.tint((0.04, 0.6), True, 1)),
                           sum(ac.tint((0.04, 0.6), True)))   # lighter on slate


class CacheTests(unittest.TestCase):
    def test_round_trip_keeps_hits_and_misses(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'c.json')
            ac.write_cache({'Firefox': (0.1, 0.8), 'ChatGPT': None}, path, 'sig')
            back = ac.read_cache(path, 'sig')
        self.assertEqual(back['Firefox'], (0.1, 0.8))
        self.assertIsNone(back['ChatGPT'])

    def test_a_new_signature_drops_the_cache(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'c.json')
            ac.write_cache({'ChatGPT': None}, path, 'before')
            self.assertEqual(ac.read_cache(path, 'after'), {})

    def test_a_missing_file_is_not_an_error(self):
        self.assertEqual(ac.read_cache('/nonexistent/c.json', 'x'), {})

    def test_the_signature_moves_when_an_app_is_installed(self):
        with tempfile.TemporaryDirectory() as d:
            first = ac.signature([d], 'theme')
            os.utime(d, (0, 0))
            self.assertNotEqual(first, ac.signature([d], 'theme'))
            self.assertNotEqual(ac.signature([d], 'theme'),
                                ac.signature([d], 'other-theme'))


class ResolveTests(unittest.TestCase):
    def test_cached_names_are_not_looked_at_again(self):
        cache = {'Firefox': (0.1, 0.8)}
        bases, found = ac.resolve([('Firefox', 'firefox', 'Firefox', '')], cache)
        self.assertEqual(found, 0)
        self.assertEqual(bases, cache)

    def test_a_name_with_no_icon_is_remembered_as_a_miss(self):
        bases, found = ac.resolve([('Nope', 'nope-xyzzy', 'Nope', '')], {}, index={})
        self.assertEqual(found, 1)
        self.assertIn('Nope', bases)
        self.assertIsNone(bases['Nope'])


if __name__ == '__main__':
    unittest.main()
