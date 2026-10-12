"""Release independence, rollback, bounded cached readings and lifecycle failures."""
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]


def load(name, file):
    loader = importlib.machinery.SourceFileLoader(name, str(ROOT / 'bin' / file))
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader(name, loader))
    loader.exec_module(module)
    return module


deploy = load('mintbook_deploy_tests', 'mintbook_deploy.py')
status = load('desktop_status_tests', 'desktop-status')
panel = load('panel_lifecycle_tests', 'panel-session')


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.source, self.home = base / 'checkout', base / 'home'
        (self.source / 'bin').mkdir(parents=True)
        for name in ('control-center', 'panel-session', *deploy.CORE):
            path = self.source / 'bin' / name
            path.write_text('#!/usr/bin/env python3\nprint("new release")\n')
            path.chmod(0o755)
        unit = self.source / 'config/systemd/mintbook-panel.service'
        unit.parent.mkdir(parents=True); unit.write_text('[Service]\nType=simple\n')
        installed = self.home / '.local/bin/control-center'
        installed.parent.mkdir(parents=True); installed.write_text('#!/usr/bin/env python3\nprint("old release")\n'); installed.chmod(0o755)
        self.deployment = deploy.Deployment(self.source, self.home)
        self.blobs = patch.object(self.deployment, 'known_blobs', return_value=set()).start()
        self.changed = patch.object(self.deployment, 'changed_paths', return_value={'bin/control-center'}).start()

    def tearDown(self):
        patch.stopall()
        self.temp.cleanup()

    def test_activation_survives_checkout_removal(self):
        release = self.deployment.build()
        self.deployment.activate(release)
        self.source.rename(self.source.with_name('removed-checkout'))
        result = subprocess.run([str(self.home / '.local/bin/control-center')], text=True, capture_output=True, check=True)
        self.assertEqual(result.stdout.strip(), 'new release')
        self.assertTrue((self.home / '.local/bin/control-center').resolve().is_relative_to(self.deployment.releases))

    def test_baseline_is_a_copy_of_actual_installed_code(self):
        data = self.deployment.snapshot()
        script = self.deployment.releases / data['baseline'] / 'bin/control-center'
        self.assertIn('old release', script.read_text())

    def test_same_release_does_not_destroy_previous_rollback_target(self):
        release = self.deployment.build()
        self.deployment.activate(release)
        before = json.loads(self.deployment.state.read_text())['previous']
        self.deployment.activate(release)
        self.assertEqual(json.loads(self.deployment.state.read_text())['previous'], before)

    def test_rollback_keeps_the_latest_manager_for_older_cache_protocols(self):
        new = self.deployment.build(); data = self.deployment.snapshot()
        old = self.deployment.releases / data['baseline']
        self.deployment.activate(new, data)
        self.deployment.activate(old, data, update_manager=False)
        self.assertEqual(self.deployment.current.resolve(), old)
        self.assertEqual(self.deployment.manager.resolve(), new)
        self.assertEqual((self.home / '.local/bin/desktop-install').resolve(), new / 'bin/desktop-install')

    def test_target_dotdot_escape_is_rejected(self):
        release = self.deployment.build(); path = release / 'manifest.json'
        path.chmod(0o644); manifest = json.loads(path.read_text())
        manifest['targets']['bin/control-center'] = str(self.home / '.local/bin/../../outside')
        path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, 'target leaves'):
            self.deployment.validate(release)

    def test_payload_mutation_is_detected(self):
        release = self.deployment.build()
        path = release / 'bin/control-center'; path.chmod(0o755); path.write_text('changed')
        with self.assertRaisesRegex(ValueError, 'changed'):
            self.deployment.validate(release)

    def test_release_cannot_capture_external_source_symlinks(self):
        outside = Path(self.temp.name) / 'private'; outside.write_text('private')
        (self.source / 'bin/external').symlink_to(outside)
        with self.assertRaisesRegex(ValueError, 'leaves its checkout'):
            self.deployment.build()

    def test_private_local_plugin_does_not_gain_other_user_read_permissions(self):
        path = self.home / '.local/share/mintbook/control-center/plugins/90-private'
        path.parent.mkdir(parents=True); path.write_text('#!/bin/sh\necho private\n'); path.chmod(0o700)
        release = self.deployment.build()
        self.assertEqual((release / 'control-center/plugins/90-private').stat().st_mode & 0o777, 0o500)

    def test_audio_watcher_dropin_uses_a_stable_installed_entry_point(self):
        helper = self.source / 'bin/mb81-jack-switch'; helper.write_text('#!/usr/bin/env python3\nprint("same helper")\n'); helper.chmod(0o755)
        dropin = self.home / '.config/systemd/user/mb81-jack-switch.service.d/override.conf'
        dropin.parent.mkdir(parents=True); dropin.write_text('[Service]\nExecStart=\nExecStart=/old/checkout/bin/mb81-jack-switch\n')
        release = self.deployment.build()
        path = release / 'config/systemd/user-overrides/mb81-jack-switch.service.d/override.conf'
        self.assertIn(str(self.home / '.local/bin/mb81-jack-switch'), path.read_text())
        self.assertIn('bin/mb81-jack-switch', self.deployment.destinations(release))

    def test_unknown_local_plugin_is_preserved(self):
        path = self.home / '.local/share/mintbook/control-center/plugins/90-custom'
        path.parent.mkdir(parents=True); path.write_text('#!/bin/sh\necho local\n'); path.chmod(0o755)
        release = self.deployment.build()
        self.assertEqual((release / 'control-center/plugins/90-custom').read_text(), path.read_text())

    def test_actual_widget_font_and_period_survive_cached_reader_conversion(self):
        path = self.home / '.config/xfce4/panel/genmon-99.rc'
        path.parent.mkdir(parents=True); path.write_text('Command=/home/a/.local/bin/panel-cpu\nFont=Personal 12\nUpdatePeriod=2000\n')
        release = self.deployment.build()
        text = (release / 'config/xfce4-panel/genmon-99.rc').read_text()
        self.assertIn('panel-read cpu', text); self.assertIn('Font=Personal 12', text); self.assertIn('UpdatePeriod=2000', text)

    def test_failed_activation_restores_previous_code_and_restarts_it(self):
        fake = NS(session_pid=Mock(return_value=12), stop=Mock(), start=Mock())
        with patch.object(deploy, 'load_panel', return_value=fake), \
                patch.object(deploy, 'run', return_value=NS(stdout='test', returncode=0)), \
                patch.object(self.deployment, 'verify', side_effect=RuntimeError('failed health')):
            with self.assertRaisesRegex(RuntimeError, 'failed health'):
                self.deployment.transaction()
        data = json.loads(self.deployment.state.read_text())
        self.assertEqual(self.deployment.current.resolve().name, data['baseline'])
        self.assertEqual(fake.start.call_count, 2)
        self.assertIn('old release', (self.home / '.local/bin/control-center').read_text())


class CachedReaderTests(unittest.TestCase):
    def run_reader(self, name, heartbeat=None, valid=None, text='<txt>live</txt>\n'):
        with tempfile.TemporaryDirectory() as d:
            cache = Path(d) / '.cache/mintbook/status'; cache.mkdir(parents=True)
            if heartbeat is not None: (cache / 'heartbeat').write_text('v2 ' + str(heartbeat))
            if valid is not None: (cache / (name + '.xml')).write_text('v2 ' + str(valid) + '\n' + text)
            return subprocess.run([str(ROOT / 'bin/panel-read'), name], env={**os.environ, 'HOME': d},
                                  capture_output=True, text=True, check=True).stdout

    def test_fresh_status_is_displayed(self):
        now = int(time.clock_gettime(time.CLOCK_BOOTTIME))
        self.assertEqual(self.run_reader('cpu', now + 8, now + 8), '<txt>live</txt>\n')

    def test_dead_collector_never_presents_cached_reading_as_live(self):
        now = int(time.clock_gettime(time.CLOCK_BOOTTIME))
        text = self.run_reader('cpu', now - 1, now + 100)
        self.assertIn('Status unavailable', text); self.assertNotIn('live', text)
        self.assertIn('cpu-menu"</click>', text)

    def test_stale_backend_with_healthy_collector_is_explicitly_unavailable(self):
        now = int(time.clock_gettime(time.CLOCK_BOOTTIME))
        self.assertIn('Status unavailable', self.run_reader('wifi', now + 8, now - 1))

    def test_malformed_cache_does_not_crash_or_lose_the_action(self):
        self.assertIn('system-menu"</click>', self.run_reader('system', 'bad', 'bad'))

    def test_invalid_component_cannot_read_an_arbitrary_cache_path(self):
        result = subprocess.run([str(ROOT / 'bin/panel-read'), '../private'], capture_output=True)
        self.assertEqual(result.returncode, 2)


class CollectorTests(unittest.TestCase):
    def test_backend_timeout_retains_a_clickable_unavailable_state(self):
        with patch.object(status.subprocess, 'run', side_effect=subprocess.TimeoutExpired('read', 10)):
            text, error = status.read_backend('wifi')
        self.assertIn('Status unavailable', text); self.assertIn('wifi-menu', text); self.assertTrue(error)

    def test_battery_event_is_a_repaint_not_an_extra_history_tick(self):
        with patch.object(status.subprocess, 'run', return_value=NS(returncode=0, stdout='valid', stderr='')) as run:
            status.read_backend('battery', render_only=True)
        self.assertEqual(run.call_args.args[0][-1], '--render')

    def test_resume_discards_old_sampling_baselines_and_refreshes_status(self):
        with tempfile.TemporaryDirectory() as d:
            paths = [Path(d) / name for name in ('cpu.state', 'cpu.procs', 'cpu.io')]
            for path in paths: path.write_text('old')
            collector = status.Collector.__new__(status.Collector)
            collector.cpu = NS(STATE=paths[0], PROCS=paths[1])
            collector.cpu_tick = Mock(); collector.schedule = Mock()
            with patch.object(status, 'CACHE', Path(d) / 'status'):
                collector.sleep_event(None, None, None, None, None, NS(unpack=lambda: (False,)), None)
            self.assertTrue(all(not path.exists() for path in paths))
            collector.cpu_tick.assert_called_once(); collector.schedule.assert_called_once()

    def test_event_storm_is_debounced_to_one_refresh_per_component(self):
        collector = status.Collector.__new__(status.Collector)
        collector.events = set(); collector.GLib = NS(timeout_add=Mock(return_value=10)); collector.request = Mock()
        collector.schedule({'wifi'}); collector.schedule({'wifi', 'bt'}); collector.flush_events()
        self.assertEqual(collector.GLib.timeout_add.call_count, 1)
        self.assertEqual({call.args[0] for call in collector.request.call_args_list}, {'wifi', 'bt'})
        self.assertEqual(collector.request.call_count, 2)

    def test_network_byte_counters_do_not_trigger_status_reads(self):
        collector = status.Collector.__new__(status.Collector); collector.schedule = Mock()
        collector.bus_event(None, None, None, None, None,
                            NS(unpack=lambda: ('Device.Statistics', {'RxBytes': 10}, [])), {'wifi'})
        collector.schedule.assert_not_called()
        collector.bus_event(None, None, None, None, None,
                            NS(unpack=lambda: ('Device.Wireless', {'Strength': 80}, [])), {'wifi'})
        collector.schedule.assert_called_once_with({'wifi'})

    def test_inflight_updates_keep_one_pending_sample(self):
        collector = status.Collector.__new__(status.Collector)
        collector.closed = False; collector.inflight = {'battery'}; collector.pending = {}
        collector.request('battery', True); collector.request('battery', False); collector.request('battery', True)
        self.assertFalse(collector.pending['battery'])

    def test_old_gui_collector_session_exits_without_waiting_for_a_timer(self):
        collector = status.Collector.__new__(status.Collector)
        collector.stop = Mock()
        self.assertFalse(collector.session_ended(None, None))
        collector.stop.assert_called_once()


class LifecycleTests(unittest.TestCase):
    def test_failed_maintenance_restores_a_running_bar(self):
        with patch.object(panel, 'bus_owner', return_value=20), patch.object(panel, 'stop') as stop, \
                patch.object(panel, 'start') as start, \
                patch.object(panel.subprocess, 'run', return_value=NS(returncode=7)) as run:
            self.assertEqual(panel.maintenance(['--', '/a/installer']), 7)
        stop.assert_called_once(); start.assert_called_once()
        self.assertEqual(run.call_args.kwargs['env']['MINTBOOK_PANEL_MAINTENANCE'], '1')

    def test_interrupted_maintenance_still_restores_the_bar(self):
        with patch.object(panel, 'bus_owner', return_value=20), patch.object(panel, 'stop'), \
                patch.object(panel, 'start') as start, \
                patch.object(panel.subprocess, 'run', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt): panel.maintenance(['/a/installer'])
        start.assert_called_once()

    def test_start_is_deferred_during_maintenance(self):
        with patch.dict(os.environ, {'MINTBOOK_PANEL_MAINTENANCE': '1'}), \
                patch.object(panel, 'session_pid') as session:
            self.assertEqual(panel.start(), 0)
        session.assert_not_called()


if __name__ == '__main__':
    unittest.main()
