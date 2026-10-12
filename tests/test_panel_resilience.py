"""Recovery boundaries: desktop lifetime, real identity, and partial failures."""
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch, mock_open

ROOT = Path(__file__).resolve().parents[1]


def load(name, file):
    loader = importlib.machinery.SourceFileLoader(name, str(ROOT / 'bin' / file))
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader(name, loader))
    loader.exec_module(module)
    return module


session = load('panel_session', 'panel-session')
bar = load('panel_cpu_resilience', 'panel-cpu')
hover = load('cpu_hover_resilience', 'cpu-hover')
installer = load('panel_installer', 'panel-install')


class RecoveryTests(unittest.TestCase):
    def test_x_screen_suffix_is_not_another_session(self):
        self.assertEqual(session.display_id(':0'), session.display_id(':0.0'))
        self.assertNotEqual(session.display_id(':0'), session.display_id(':1'))
        self.assertEqual(session.display_id('host.example:0.0'), 'host.example:0')

    def test_no_desktop_means_no_launch_or_restart(self):
        with patch.object(session, 'session_pid', return_value=None), \
                patch.object(session.subprocess, 'Popen') as spawn:
            self.assertEqual(session.supervise(), 0)
        spawn.assert_not_called()

    def test_responding_bar_with_all_plugins_is_healthy(self):
        with patch.object(session, 'ping', return_value=True), \
                patch.object(session, 'expected_wrappers', return_value={8, 19}), \
                patch.object(session, 'present_wrappers', return_value={8, 19}):
            self.assertIsNone(session.unhealthy(123))

    def test_one_dead_plugin_does_not_count_as_a_healthy_bar(self):
        with patch.object(session, 'ping', return_value=True), \
                patch.object(session, 'expected_wrappers', return_value={8, 19}), \
                patch.object(session, 'present_wrappers', return_value={19}):
            self.assertEqual(session.unhealthy(123), 'missing plugins: 8')

    def test_freeze_is_detected_without_looking_at_cpu_usage(self):
        with patch.object(session, 'ping', return_value=False):
            self.assertEqual(session.unhealthy(123), 'panel did not answer D-Bus')

    def test_panel_identity_rejects_an_unrelated_live_process(self):
        with self.assertRaises(ValueError):
            session.panel_fd(os.getpid())

    def test_daemon_query_has_a_deadline(self):
        with patch.object(session.subprocess, 'run', side_effect=subprocess.TimeoutExpired('busctl', 2)) as run:
            self.assertIsNone(session.bus_owner())
        self.assertEqual(run.call_args.kwargs['timeout'], 2)

    def test_malformed_owner_reply_is_not_a_pid(self):
        for reply in ('u nope', 'u', '', None):
            with patch.object(session, 'run', return_value=reply):
                self.assertIsNone(session.bus_owner())

    def test_closing_uses_held_identity_and_escalates_a_hang(self):
        with patch.object(session.signal, 'pidfd_send_signal') as send, \
                patch.object(session.selectors, 'DefaultSelector') as selector:
            selector.return_value.__enter__.return_value.select.return_value = []
            session.close_panel(99)
        self.assertEqual([c.args for c in send.call_args_list], [
            (99, session.signal.SIGCONT), (99, session.signal.SIGTERM),
            (99, session.signal.SIGKILL)])

    def test_heartbeat_calls_the_ui_thread_without_refreshing_widgets(self):
        with patch.object(session, 'run', return_value='b false') as run:
            self.assertTrue(session.ping())
        args = run.call_args.args[0]
        self.assertIn('PluginEvent', args)
        self.assertEqual(args[-4:], ['mintbook-health', 'ping', 'b', 'false'])

    def test_panel_close_preserves_its_launched_application(self):
        parent = subprocess.Popen(['sh', '-c', 'sleep 30 & echo $!; wait'],
                                  stdout=subprocess.PIPE, text=True, start_new_session=True)
        child_pid = int(parent.stdout.readline())
        child_fd = os.pidfd_open(child_pid)
        parent_fd = os.pidfd_open(parent.pid)
        try:
            session.close_panel(parent_fd)
            parent.wait(timeout=5)
            # A panel-launched app in the same process group remains alive.
            os.kill(child_pid, 0)
        finally:
            session.signal.pidfd_send_signal(child_fd, session.signal.SIGTERM)
            os.close(child_fd)
            os.close(parent_fd)
            parent.stdout.close()
            if parent.poll() is None:
                parent.terminate(); parent.wait(timeout=5)

    def test_a_gone_panel_needs_no_further_signal(self):
        with patch.object(session.signal, 'pidfd_send_signal', side_effect=ProcessLookupError):
            session.close_panel(99)

    def test_inherited_tray_plugin_is_monitored(self):
        responses = ["/plugins/plugin-8  systray\n/plugins/plugin-13  clock", "1", "8\n13"]
        def read(conf, _path):
            conf.read_dict({'Xfce Panel': {'X-XFCE-Internal': 'false'}})
        with patch.object(session, 'run', side_effect=responses), \
                patch.object(session.configparser.ConfigParser, 'read', read):
            self.assertEqual(session.expected_wrappers(), {8, 13})

    def test_unavailable_configuration_does_not_crash_supervision(self):
        with patch.object(session, 'run', return_value=None):
            self.assertEqual(session.expected_wrappers(), set())


class StaleWatcherTests(unittest.TestCase):
    def test_reused_pid_is_not_a_watcher(self):
        with patch('builtins.open', mock_open(read_data=b'/usr/bin/python3\0another-task\0')):
            self.assertFalse(bar.watcher_matches(123))

    def test_verified_hover_watcher_is_recognised(self):
        args = b'\0'.join([b'/usr/bin/xdotool', b'behave', b'123', b'exec',
                            bar.WATCHER.encode(), b'on'])
        with patch('builtins.open', mock_open(read_data=args)):
            self.assertTrue(bar.watcher_matches(123))

    def test_stale_pidfile_cannot_signal_a_reused_pid(self):
        files = {bar.WATCH_PID: '123\n456\n', '/proc/123/cmdline': b'/usr/bin/python3\0other\0'}
        def opened(path, *args, **kwargs):
            return mock_open(read_data=files[path])(path, *args, **kwargs)
        with patch.dict(bar.os.environ, {'DISPLAY': ':test'}), \
                patch('builtins.open', side_effect=opened), \
                patch.object(bar.os, 'stat') as stat, \
                patch.object(bar.os, 'access', return_value=True), \
                patch.object(bar.os, 'kill') as kill:
            stat.return_value.st_mtime = bar.time.time()
            bar.ensure_watcher()
        kill.assert_not_called()

    def test_failed_empty_pidfile_obeys_retry_backoff(self):
        with patch.dict(bar.os.environ, {'DISPLAY': ':test'}), \
                patch('builtins.open', mock_open(read_data='')), \
                patch.object(bar.os, 'stat') as stat, \
                patch.object(bar.os, 'access', return_value=True), \
                patch.object(bar.subprocess, 'Popen') as spawn:
            stat.return_value.st_mtime = bar.time.time()
            bar.ensure_watcher()
        spawn.assert_not_called()

    def test_negative_pid_never_signals_a_process_group(self):
        self.assertFalse(bar.watcher_matches(-1))
        with patch('builtins.open', mock_open(read_data='-1 0 1\n')), \
                patch.object(hover.os, 'kill') as kill, patch.object(hover.os, 'remove'):
            hover.stop()
        kill.assert_not_called()


class CacheTests(unittest.TestCase):
    def test_malformed_health_cache_keeps_a_system_icon(self):
        with tempfile.TemporaryDirectory() as d:
            cache = Path(d) / '.cache/mintbook'
            cache.mkdir(parents=True)
            (cache / 'health.json').write_text('{"rows":[null,"bad row",3]}')
            with patch.object(Path, 'home', return_value=Path(d)), patch('builtins.print') as printed:
                load('panel_system_bad_cache', 'panel-system')
            self.assertTrue(any('system.svg' in str(call) for call in printed.call_args_list))

    def test_busy_cpu_writer_does_not_render_or_write(self):
        with tempfile.TemporaryDirectory() as d, \
                patch.object(bar, 'STATE', str(Path(d) / 'cpu.state')), \
                patch.object(bar.fcntl, 'flock', side_effect=BlockingIOError), \
                patch.object(bar, 'emit') as emit, \
                patch.object(bar, 'sample_and_render') as render:
            bar.main()
        render.assert_not_called()
        emit.assert_called_once_with(0.0)

    def test_second_install_retains_original_file_snapshot(self):
        with tempfile.TemporaryDirectory() as d:
            state = Path(d) / 'state/panel-before.json'
            source, target = Path(d) / 'source', Path(d) / 'installed'
            source.write_text('new'); target.write_text('original')
            with patch.object(installer, 'STATE', state), \
                    patch.object(installer, 'targets', return_value=[(source, target)]):
                before = installer.snapshot()
                target.write_text('installed')
                self.assertEqual(installer.snapshot(), before)
                self.assertEqual(Path(before[0]['backup']).read_text(), 'original')


if __name__ == '__main__':
    unittest.main()
