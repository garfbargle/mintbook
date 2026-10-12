"""The bar's hover: which samples it draws, what colour, and who it watches.

panel-cpu and cpu-hover are scripts, not modules; they are loaded here by path
the same way the panel loads them, which also proves neither does any work at
import — a file that opened an X connection or walked /proc on import would
hang or slow this suite down.
"""
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, mock_open

ROOT = Path(__file__).resolve().parents[1]


def load(name, filename=None):
    loader = importlib.machinery.SourceFileLoader(
        name, str(ROOT / 'bin' / (filename or f'{name}.py')))
    module = importlib.util.module_from_spec(
        importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(module)
    return module


bar = load('panel_cpu', 'panel-cpu')
hover = load('cpu_hover', 'cpu-hover')
cpu = load('mintbook_cpu')


def stack(rows):
    return ''.join(json.dumps(row) + '\n' for row in rows)


def sample(busy, procs, t=0):
    return {'t': t, 'b': busy, 'd': 6,
            'p': [{'i': pid, 'n': name, 's': share}
                  for pid, name, share in procs]}


class InkTests(unittest.TestCase):
    def test_white_ink_means_a_slate_bar(self):
        self.assertTrue(bar.bar_is_dark('#ffffff'))
        self.assertTrue(bar.bar_is_dark('#fff'))

    def test_dark_ink_means_a_pearl_bar(self):
        self.assertFalse(bar.bar_is_dark('#2d3036'))

    def test_a_colour_it_cannot_read_assumes_slate(self):
        self.assertTrue(bar.bar_is_dark('not a colour'))

    def test_a_band_is_a_closed_polygon(self):
        d = bar.band_path([0, 1, 2], [10, 10, 10], [4, 5, 6])
        self.assertTrue(d.startswith('M0.0 10.0'))
        self.assertTrue(d.endswith('Z'))
        self.assertEqual(d.count('L'), 5)


class WindowTests(unittest.TestCase):
    """What the bar draws while the pointer is on it."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, 'cpu.stack')
        self.addCleanup(self.dir.cleanup)

    def test_only_the_recent_samples_are_drawn(self):
        rows = [sample(10, [(1, 'Firefox', 5)], t=i) for i in range(40)]
        Path(self.path).write_text(stack(rows))
        samples, _names = cpu.bar_stack(span=16, path=self.path)
        self.assertEqual(len(samples), 16)
        self.assertEqual(samples[-1]['t'], 39)

    def test_a_process_that_dips_keeps_its_band(self):
        rows = [
            sample(30, [(1, 'Firefox', 20), (2, 'Xorg', 4)], t=0),
            sample(30, [(2, 'Xorg', 4)], t=6),
            sample(30, [(1, 'Firefox', 9), (2, 'Xorg', 4)], t=12),
        ]
        Path(self.path).write_text(stack(rows))
        _samples, names = cpu.bar_stack(path=self.path)
        self.assertIn('Firefox', names)

    def test_bands_are_ranked_over_the_window_not_the_last_sample(self):
        rows = [
            sample(40, [(1, 'steady', 20)], t=0),
            sample(40, [(1, 'steady', 20), (2, 'spike', 30)], t=6),
        ]
        Path(self.path).write_text(stack(rows))
        _samples, names = cpu.bar_stack(path=self.path)
        self.assertEqual(names[:2], ['steady', 'spike'])

    def test_no_history_is_not_a_crash(self):
        Path(self.path).write_text('')
        samples, names = cpu.bar_stack(path=self.path)
        self.assertEqual((samples, names), ([], []))

    def test_the_bar_carries_fewer_bands_than_the_menu(self):
        self.assertLess(cpu.BAND_N, cpu.CHART_N)


class WatcherTests(unittest.TestCase):
    def test_stop_checks_identity_and_ignores_the_panel_pid(self):
        files = {hover.PIDFILE: '10 11 12\n13\n',
                 '/proc/10/cmdline': b'\0'.join([b'/usr/bin/xdotool', b'behave', b'123', b'exec', hover.SELF.encode(), b'on']),
                 '/proc/11/cmdline': b'\0'.join([b'/usr/bin/xdotool', b'behave', b'123', b'exec', b'/another/task']),
                 '/proc/12/cmdline': b'/usr/bin/python3\0unrelated\0'}
        def opened(path, *args, **kwargs):
            return mock_open(read_data=files[path])(path, *args, **kwargs)
        with patch('builtins.open', side_effect=opened), \
                patch.object(hover.os, 'kill') as kill, \
                patch.object(hover.os, 'remove'):
            self.assertEqual(hover.stop(), 0)
        kill.assert_called_once_with(10, hover.signal.SIGTERM)

    def test_stop_tolerates_a_stale_pidfile(self):
        with patch('builtins.open', side_effect=FileNotFoundError), \
                patch.object(hover.os, 'kill') as kill, \
                patch.object(hover.os, 'remove', side_effect=FileNotFoundError):
            self.assertEqual(hover.stop(), 0)
        kill.assert_not_called()

    def test_the_plugin_is_found_by_its_command_not_a_number(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, 'genmon-17.rc').write_text('Command=/x/panel-temp\n')
            Path(d, 'genmon-19.rc').write_text('Command=/x/panel-cpu\n')
            Path(d, 'genmon-3.rc').write_text('Command=/x/panel-wifi\n')
            hover.PANEL_RC = d
            self.assertEqual(hover.plugin_id(), 19)

    def test_no_cpu_widget_is_zero_not_a_guess(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, 'genmon-17.rc').write_text('Command=/x/panel-temp\n')
            hover.PANEL_RC = d
            self.assertEqual(hover.plugin_id(), 0)

    def test_a_missing_panel_directory_is_survivable(self):
        hover.PANEL_RC = '/nonexistent/panel'
        self.assertEqual(hover.plugin_id(), 0)

    def test_the_flag_the_bar_reads_is_the_one_hover_writes(self):
        self.assertEqual(bar.HOVER, hover.HOVER)

    def test_the_nudge_names_the_plugin_not_its_id(self):
        """`plugin-19:refresh` was sent for months and reached nothing: the
        panel matches on the plugin name. Only `genmon:` does anything."""
        sent = []
        real, hover.run = hover.run, lambda args, **kw: sent.append(args) or ''
        self.addCleanup(setattr, hover, 'run', real)
        with patch.object(hover.socket, 'socket', side_effect=OSError):
            hover.nudge(19)
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0][0], 'xfce4-panel')
        self.assertIn('--plugin-event=genmon:refresh:bool:true', sent[0])
        self.assertNotIn('--plugin-event=plugin-19:refresh:bool:true', sent[0])

    def test_a_repaint_is_not_a_sample(self):
        # panel-cpu must treat a run that lands inside this window as a
        # repaint; genmon's own period is two seconds.
        self.assertLess(bar.MIN_TICK, 2.0)


if __name__ == '__main__':
    unittest.main()
