"""CPU stack history must survive odd names, missing I/O, and a short window."""
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load():
    loader = importlib.machinery.SourceFileLoader(
        'mintbook_cpu', str(ROOT / 'bin' / 'mintbook_cpu.py'))
    module = importlib.util.module_from_spec(
        importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(module)
    return module


cpu = load()


def sample(busy, procs, t=0, dt=6):
    return {'t': t, 'b': busy, 'd': dt, 'p': procs}


def proc(pid, name, share, rss=0, read=0, write=0):
    return {'i': pid, 'n': name, 's': share, 'm': rss, 'r': read, 'w': write}


class CpuHistoryTests(unittest.TestCase):
    def test_kworker_colon_survives_roundtrip(self):
        row = sample(12.5, [proc(1, 'kworker/0:1', 4.2)])
        parsed = cpu.parse_stack(cpu.encode_sample(row))
        self.assertEqual(parsed[0]['p'][0]['n'], 'kworker/0:1')
        self.assertEqual(parsed[0]['p'][0]['s'], 4.2)

    def test_garbage_and_comments_are_dropped(self):
        text = '# mintbook\nnot json\n' + cpu.encode_sample(sample(8, [proc(2, 'Xorg', 3)]))
        rows = cpu.parse_stack(text)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['b'], 8)

    def test_series_pinches_when_a_pid_leaves(self):
        rows = [
            sample(20, [proc(10, 'firefox', 12), proc(11, 'Xorg', 4)], t=0),
            sample(10, [proc(11, 'Xorg', 4)], t=6),
        ]
        series, other, busy = cpu.series_for(rows, ['firefox', 'Xorg'])
        self.assertEqual(series['firefox'], [12, 0])
        self.assertEqual(series['Xorg'], [4, 4])
        self.assertEqual(other, [4, 6])
        self.assertEqual(busy, [20, 10])

    def test_collapse_sums_helpers_of_the_same_app(self):
        rows = [proc(1, 'cursor', 10, rss=100, read=8),
                proc(2, 'cursor', 5, rss=50, write=3),
                proc(3, 'Xorg', 2, rss=10)]
        grouped = cpu.collapse_procs(rows + [proc(4, 'firefox', 4), proc(5, 'Web Content', 3)])
        by_name = {row['n']: row for row in grouped}
        self.assertEqual(by_name['Firefox']['s'], 7)
        self.assertEqual(by_name['Firefox']['count'], 2)
        self.assertEqual(by_name['Cursor']['s'], 15)
        self.assertEqual(by_name['Cursor']['m'], 150)
        self.assertEqual(by_name['Cursor']['count'], 2)
        self.assertEqual(by_name['Cursor']['i'], 1)
        self.assertEqual(by_name['X server']['s'], 2)

    def test_legend_prefers_whatever_is_on_screen_now(self):
        rows = [
            sample(30, [proc(1, 'old', 20), proc(2, 'quiet', 1)], t=0),
            sample(12, [proc(3, 'new', 10), proc(2, 'quiet', 1)], t=6),
        ]
        legend = cpu.legend_pids(rows, limit=2)
        self.assertEqual([pid for pid, _name in legend], [3, 2])

    def test_pretty_names_electron_roles_and_scripts(self):
        self.assertEqual(cpu.pretty('firefox-bin'), 'Firefox')
        self.assertEqual(cpu.pretty('cursor', '/opt/cursor/cursor --type=renderer'),
                         'Cursor · Renderer')
        self.assertEqual(cpu.pretty('python3', '/usr/bin/python3 /home/a/bin/panel-cpu'),
                         'panel-cpu')
        self.assertEqual(cpu.pretty('kworker/0:1'), 'Kernel worker')

    def test_io_story_distinguishes_cache_from_disk(self):
        disk = cpu.io_story({'read_s': 2_000_000, 'rchar_s': 2_000_000, 'write_s': 0})
        cache = cpu.io_story({'read_s': 1000, 'rchar_s': 8_000_000, 'write_s': 0})
        self.assertIn('disk', disk)
        self.assertIn('cache', cache)
        self.assertEqual(cpu.io_story({'read_s': 0, 'rchar_s': 0, 'write_s': 0}), '')

    def test_human_units(self):
        self.assertEqual(cpu.human(0), '0 B')
        self.assertEqual(cpu.human(12_500, True), '12 KB/s')
        self.assertEqual(cpu.human(8_500, True), '8.5 KB/s')
        self.assertAlmostEqual(cpu.cores(25, ncpu=4), 1.0)

    def test_state_top_rows_accept_old_and_new(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'cpu.state'
            path.write_text('1\n2\n3.0,4.0\n9\n12.5\x1ffirefox\n')
            old = cpu.read_state(str(path))
            self.assertEqual(old['top'][0][:2], (12.5, 'firefox'))
            path.write_text('1\n2\n3.0\n9\n12.5\x1ffirefox\x1f440\n')
            new = cpu.read_state(str(path))
            self.assertEqual(new['top'][0], (12.5, 'firefox', 440))

    def test_inspect_reads_a_fake_proc(self):
        with tempfile.TemporaryDirectory() as directory:
            proc = Path(directory)
            pid = proc / '9'
            fd = pid / 'fd'
            fd.mkdir(parents=True)
            # 9 0 1 2 3 4 5 6 7 8 9 10 11=utime 12=stime ... 20=vsize 21=rss
            rest = ['S', '1'] + ['0'] * 9 + ['100', '50'] + ['0'] * 4 + ['0', '4', '0', '0', '99999', '20']
            (pid / 'stat').write_text(f'9 (firefox) {" ".join(rest)}\n')
            (pid / 'status').write_text('Name:\tfirefox\nThreads:\t4\nVmRSS:\t4096 kB\n')
            (pid / 'cmdline').write_bytes(b'/usr/lib/firefox/firefox\x00')
            (pid / 'io').write_text('rchar: 8000\nwchar: 10\nread_bytes: 1000\nwrite_bytes: 200\n')
            os.symlink(str(proc / 'home-file'), fd / '3')
            (proc / 'home-file').write_text('x')
            os.symlink('socket:[12]', fd / '4')
            first = cpu.inspect(9, proc=str(proc))
            self.assertEqual(first['comm'], 'firefox')
            self.assertEqual(first['name'], 'Firefox')
            self.assertEqual(first['fd']['socket'], 1)
            self.assertTrue(any('home-file' in path for path in first['files']))
            second = cpu.inspect(9, proc=str(proc), prev=first, now=first['at'] + 1)
            self.assertGreaterEqual(second['cores'], 0)

    def test_stack_write_keeps_a_bounded_window(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'cpu.stack'
            rows = [sample(i, [proc(1, 'Xorg', 1)], t=i) for i in range(80)]
            cpu.write_stack(rows, path=str(path), keep=60)
            kept = cpu.read_stack(str(path))
            self.assertEqual(len(kept), 60)
            self.assertEqual(kept[0]['t'], 20)

    def test_span_label(self):
        self.assertEqual(cpu.span_label([]), 'collecting…')
        self.assertEqual(cpu.span_label([sample(1, [], t=0), sample(1, [], t=30)]),
                         'last 30s')


class ReadingTests(unittest.TestCase):
    """The number on a process row is the thing people actually read."""

    def test_a_busy_process_is_a_whole_percent(self):
        self.assertEqual(cpu.pct_label(26.4), '26%')
        self.assertEqual(cpu.pct_label(9.96), '10%')

    def test_a_quiet_one_keeps_a_tenth(self):
        self.assertEqual(cpu.pct_label(1.04), '1.0%')
        self.assertEqual(cpu.pct_label(0.41), '0.4%')

    def test_nothing_is_nothing(self):
        self.assertEqual(cpu.pct_label(0), '0%')
        self.assertEqual(cpu.pct_label(-3), '0%')


if __name__ == '__main__':
    unittest.main()
