"""Popup lifecycle, real instance ownership, and shared brightness state."""
import ast
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'bin'))
import mintbook_backlight as bl
import mintbook_instance as instance


def load_updates_parts():
    tree = ast.parse((ROOT / 'bin/updates-menu').read_text())
    nodes = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))
             and n.name in ('Menu', 'update_id', 'version_line')]
    namespace = {'Gtk': Mock(), 'Gdk': Mock(), 'GLib': Mock(), 'time': time}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), '<updates>', 'exec'), namespace)
    return namespace


class UpdateLifetime(unittest.TestCase):
    def setUp(self):
        self.ns = load_updates_parts()
        self.menu = m = self.ns['Menu'].__new__(self.ns['Menu'])
        m.closing = m.hidden = m.checking = False
        m.busy = True; m.grab = Mock(); m.win = Mock(); m.area = Mock()
        m.cache_monitor = Mock(); m.rebuild = Mock()

    def test_escape_close_preserves_active_transaction(self):
        self.menu.close()
        self.assertTrue(self.menu.hidden)
        self.assertFalse(self.menu.closing)
        self.menu.win.hide.assert_called_once()
        self.ns['Gtk'].main_quit.assert_not_called()

    def test_dismissed_refresh_is_preserved_too(self):
        self.menu.busy = False; self.menu.checking = True
        self.menu.close()
        self.assertTrue(self.menu.hidden)
        self.ns['Gtk'].main_quit.assert_not_called()

    def test_reopening_same_worker_preserves_progress(self):
        self.menu.hidden = True; self.menu.progress = 37
        self.menu.win.get_visible.return_value = False
        self.menu.reposition = Mock(); self.menu.tick_spinner = Mock()
        self.menu.toggle()
        self.assertFalse(self.menu.hidden)
        self.assertEqual(self.menu.progress, 37)
        self.menu.win.present.assert_called_once()

    def test_idle_hidden_worker_exits_and_stops_monitor(self):
        self.menu.busy = False; self.menu.hidden = True
        self.menu.retire_if_idle()
        self.assertTrue(self.menu.closing)
        self.menu.cache_monitor.cancel.assert_called_once()
        self.ns['Gtk'].main_quit.assert_called_once()

    def test_stale_finished_transaction_cannot_complete_a_new_job(self):
        self.menu.trans = object(); self.menu.next_phase = Mock()
        self.menu.on_finished(object(), 'exit-success')
        self.menu.next_phase.assert_not_called()

    def test_same_named_user_and_system_updates_have_distinct_identity(self):
        row = {'name': 'App', 'source': 'org.test.App', 'flatpak': {'scope': 'user', 'ref': 'app/org.test.App/x86_64/stable'}}
        other = {**row, 'flatpak': {**row['flatpak'], 'scope': 'system'}}
        self.assertNotEqual(self.ns['update_id'](row), self.ns['update_id'](other))


class Brightness(unittest.TestCase):
    def test_stale_saved_percent_does_not_override_hardware(self):
        self.assertEqual(bl.level(40, 100, {'hw': '89', 'req_pct': '89'}), 40)
        self.assertEqual(bl.level(12, 100, {'hw': '12', 'req_pct': '5'}), 5)
        self.assertEqual(bl.level(12, 100, {'hw': '12', 'req_pct': 'bad'}), 12)

    def test_curve_is_monotonic_and_never_blacks_out_panel(self):
        values = [bl.curve(i, 100, {}) for i in range(101)]
        self.assertTrue(all(a[0] <= b[0] and a[1] <= b[1] for a, b in zip(values, values[1:])))
        self.assertEqual(values[0], (12, .35)); self.assertEqual(values[-1], (100, 1))
        with self.assertRaises(ValueError): bl.curve(50, 100, {'BACKLIGHT_CURVE_GAMMA': 'nan'})

    def test_both_temperature_modes_keep_identical_software_brightness(self):
        with tempfile.TemporaryDirectory() as tmp:
            conf = Path(tmp) / 'redshift.conf'
            conf.write_text('[redshift]\ntemp-night=3500\n')
            for mode, temperature in [('auto', None), ('on', '3500:3500'), ('off', '6500:6500')]:
                args = bl.redshift_args(conf, '.8832', mode)
                self.assertEqual(args[args.index('-b') + 1], '0.8832:0.8832')
                self.assertEqual(args[args.index('-c') + 1], str(conf))
                self.assertIn('-r', args)
                if temperature: self.assertEqual(args[args.index('-t') + 1], temperature)
            self.assertEqual(conf.read_text(), '[redshift]\ntemp-night=3500\n')

    def test_failed_hardware_write_does_not_save_optimistic_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp); hardware = base / 'acpi_video0'; hardware.mkdir()
            (hardware / 'max_brightness').write_text('100'); (hardware / 'brightness').write_text('40')
            state = base / 'state'; state.write_text('hw=40\nreq_pct=40\n')
            with patch.multiple(bl, BL=hardware, LOCK=base/'lock', STATE_DIR=base, STATE=state, SOFT=base/'soft'), \
                 patch.object(bl, 'read_state', side_effect=lambda path=None: {'hw':'40','req_pct':'40'} if path is None else {}), \
                 patch.object(bl.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, 'busctl')):
                with self.assertRaises(subprocess.CalledProcessError): bl.apply(percent=70)
            self.assertEqual(state.read_text(), 'hw=40\nreq_pct=40\n')


class InstanceOwnership(unittest.TestCase):
    def test_stale_pidfile_cannot_signal_an_unrelated_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            process = subprocess.Popen(['sleep', '30'])
            try:
                pidfile = Path(tmp) / 'menu.pid'; pidfile.write_text(str(process.pid))
                self.assertTrue(instance.claim(pidfile, 'updates-menu'))
                self.assertIsNone(process.poll())
                self.assertEqual(pidfile.read_text(), str(os.getpid()))
            finally:
                process.terminate(); process.wait()

    def test_second_launch_toggles_one_running_owner(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp); script = base / 'updates-menu'; pidfile = base / 'menu.pid'; hit = base/'hit'
            script.write_text('import sys, signal, time\nfrom pathlib import Path\nsys.path.insert(0, '+repr(str(ROOT/'bin'))+')\nfrom mintbook_instance import claim\nsignal.signal(signal.SIGUSR1, lambda *args: Path(sys.argv[2]).write_text("toggle"))\nif not claim(sys.argv[1], "updates-menu", signal.SIGUSR1): sys.exit()\nprint("ready", flush=True)\ntime.sleep(20)\n')
            owner = subprocess.Popen([sys.executable, str(script), str(pidfile), str(hit)], stdout=subprocess.PIPE, text=True)
            try:
                self.assertEqual(owner.stdout.readline().strip(), 'ready')
                second = subprocess.run([sys.executable, str(script), str(pidfile), str(hit)], timeout=3)
                self.assertEqual(second.returncode, 0)
                until = time.monotonic()+1
                while not hit.exists() and time.monotonic()<until: time.sleep(.01)
                self.assertTrue(hit.exists()); self.assertIsNone(owner.poll())
            finally:
                owner.terminate(); owner.wait(); owner.stdout.close()

class PendingControls(unittest.TestCase):
    def test_dismissal_keeps_the_latest_coalesced_setting(self):
        tree = ast.parse((ROOT / 'bin/control-center').read_text())
        node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'Panel')
        ns = {'Gdk': Mock(), 'Gtk': Mock()}
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<control-center>', 'exec'), ns)
        panel = ns['Panel'].__new__(ns['Panel'])
        tile = types.SimpleNamespace(setting=True, requested_value=70, update=Mock())
        panel.tiles = [tile]; panel.closing = panel.dismissing = False
        panel.win = Mock(); panel.pool = Mock(); panel._send_value = Mock()
        panel.close()
        self.assertTrue(panel.dismissing); self.assertFalse(panel.closing)
        panel._set_done(tile, 30, {}, None)
        panel._send_value.assert_called_once_with(tile)
        self.assertFalse(panel.closing)
        panel._set_done(tile, 70, {'value':70}, None)
        tile.update.assert_called_once_with({'value':70})
        self.assertTrue(panel.closing)
        ns['Gtk'].main_quit.assert_called_once()

    def test_system_workers_settle_after_a_timeout(self):
        tree = ast.parse((ROOT / 'bin/system-menu').read_text())
        node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'Menu')
        threads = Mock()
        threads.Thread.side_effect = lambda **kw: types.SimpleNamespace(start=kw['target'])
        ns = {'threading': threads, 'subprocess': subprocess, 'GLib': Mock(),
              'os': os, 'HEALTH_APP': ROOT/'bin/mintbook-health', 'AWAKE_APP': ROOT/'bin/keep-awake'}
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<system-menu>', 'exec'), ns)
        menu = ns['Menu'].__new__(ns['Menu'])
        menu.doctor_running = menu.awake_running = False; menu.area = Mock()
        with patch.object(subprocess, 'run', side_effect=subprocess.TimeoutExpired('backend', 1)):
            menu.run_doctor(); menu.set_awake('off')
        self.assertEqual(ns['GLib'].idle_add.call_args_list[0].args[0], menu.doctor_done)
        self.assertEqual(ns['GLib'].idle_add.call_args_list[1].args[0], menu.awake_done)

    def test_failed_gamma_restart_keeps_state_retryable(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp); hw = base/'hw'; hw.mkdir()
            (hw/'brightness').write_text('40'); (hw/'max_brightness').write_text('100')
            state=base/'state'; state.write_text('hw=40\nreq_pct=40\n')
            soft=base/'soft'; soft.write_text('.5\n')
            with patch.multiple(bl, BL=hw, LOCK=base/'lock', STATE_DIR=base, STATE=state, SOFT=soft), \
                 patch.object(bl,'read_state',side_effect=lambda path=None: {'hw':'40','req_pct':'40'} if path is None else {}), \
                 patch.object(subprocess,'run',side_effect=subprocess.CalledProcessError(1,'systemctl')):
                with self.assertRaises(subprocess.CalledProcessError): bl.apply(percent=40)
            self.assertEqual(state.read_text(), 'hw=40\nreq_pct=40\n')
            self.assertEqual(soft.read_text(), '.5\n')

    def test_shortcuts_bind_before_power_manager_reacquires_keys(self):
        loader = importlib.machinery.SourceFileLoader('brightness_installer', str(ROOT/'bin/brightness-install'))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        installer = importlib.util.module_from_spec(spec); loader.exec_module(installer)
        events = []
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp); saved = home/'.config/mintbook/brightness-install.json'
            saved.parent.mkdir(parents=True)
            saved.write_text('{}')
            prefs = saved.parent/'backlight-curve.env'; prefs.write_text('existing')
            conf = home/'.config/redshift.conf'; conf.write_text('[redshift]\n')
            def run(*args, **kw):
                events.append(args)
                return types.SimpleNamespace(returncode=0, stdout='')
            with patch.multiple(installer, HOME=home, SAVED=saved), \
                 patch.object(installer,'targets',return_value=[]), \
                 patch.object(installer,'run',side_effect=run), \
                 patch.object(installer,'set_property',side_effect=lambda *a: events.append(('property',)+a)), \
                 patch.object(installer.time,'sleep'), patch.object(sys,'argv',['brightness-install']), \
                 patch.dict(os.environ, {'DISPLAY':':test'}):
                installer.main()
            quit_at = events.index(('xfce4-power-manager','--quit'))
            start_at = events.index(('xfce4-power-manager','--daemon'))
            binds = [i for i,e in enumerate(events) if e[0]=='property' and e[1]=='xfce4-keyboard-shortcuts']
            self.assertTrue(binds)
            self.assertTrue(all(quit_at<i<start_at for i in binds))
            self.assertEqual(prefs.read_text(), 'existing')
