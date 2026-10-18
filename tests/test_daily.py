"""Focused regression tests for action dispatch, keyboard focus and write ordering."""
import ast
import importlib.machinery
import importlib.util
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
import tempfile
import json
import os
import subprocess
import time
from unittest.mock import patch
import gi
gi.require_version('Gdk', '3.0')
from gi.repository import Gdk

ROOT = Path(__file__).resolve().parents[1]

def load(name):
    loader = importlib.machinery.SourceFileLoader(name.replace('-', '_'), str(ROOT / 'bin' / name))
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(module)
    return module


def panel_class():
    tree = ast.parse((ROOT / 'bin/control-center').read_text())
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'Panel')
    namespace = dict(Gdk=Gdk)
    exec(compile(ast.Module(body=[cls], type_ignores=[]), '<Panel>', 'exec'), namespace)
    return namespace['Panel']

class DailyTests(unittest.TestCase):
    def test_overview_panel_widget_teaches_shortcut(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [str(ROOT / 'bin/panel-overview')],
                env={**os.environ, 'HOME': directory}, text=True,
                capture_output=True, check=True)
        self.assertIn(f'<click>{directory}/.local/bin/overview</click>', result.stdout)
        self.assertIn('<tool>Overview\nOpen with Super + Space</tool>', result.stdout)

    def test_control_center_tooltip_is_just_the_name(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [str(ROOT / 'bin/panel-control')],
                env={**os.environ, 'HOME': directory}, text=True,
                capture_output=True, check=True)
        self.assertIn('<tool>Control Center</tool>', result.stdout)

    def test_cpu_tooltip_is_name_and_percent(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / '.cache/mintbook').mkdir(parents=True)
            result = subprocess.run(
                [str(ROOT / 'bin/panel-cpu')],
                env={**os.environ, 'HOME': directory}, text=True,
                capture_output=True, check=True)
        self.assertRegex(result.stdout, r'<tool>CPU\n\d+%</tool>')
        self.assertNotIn('font_family', result.stdout)

    def test_rofi_custom_input_cannot_execute(self):
        actions = load('spotlight-actions')
        with patch.dict(actions.os.environ, {'ROFI_RETV': '2', 'ROFI_INFO': 'dark'}), patch.object(actions.subprocess, 'Popen') as spawn:
            actions.main()
            spawn.assert_not_called()

    def test_rofi_selection_is_fixed_argv(self):
        actions = load('spotlight-actions')
        with patch.dict(actions.os.environ, {'ROFI_RETV': '1', 'ROFI_INFO': 'dark'}), patch.object(actions.subprocess, 'Popen') as spawn:
            actions.main()
            self.assertEqual(spawn.call_args.args[0][-2:], ['--execute', 'dark'])
            self.assertNotIn('shell', spawn.call_args.kwargs)

    def test_overview_start_guard_allows_one_launch(self):
        overview = load('overview')
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / 'overview.start')
            first = overview.take_start_guard(path)
            self.assertIsNotNone(first)
            with self.assertRaises(overview.StartGuardBusy):
                overview.take_start_guard(path)
            os.close(first)
            second = overview.take_start_guard(path)
            self.assertIsNotNone(second)
            os.close(second)

    def test_overview_retries_a_busy_keyboard_grab(self):
        overview = load('overview')
        grabs, scheduled = [], []

        def grab():
            grabs.append(len(grabs))
            return len(grabs) > 1

        retry = overview.GrabRetry(grab, lambda delay, cb: scheduled.append((delay, cb)))
        retry.attempt()
        self.assertFalse(retry.done)
        self.assertEqual(scheduled[0][0], 25)
        retry.attempt()
        self.assertTrue(retry.done)
        retry.attempt()
        self.assertEqual(len(grabs), 2)
        self.assertEqual(len(scheduled), 1)

    def test_overview_stops_grab_retries_after_close_and_backs_off(self):
        overview = load('overview')
        delays = []
        retry = overview.GrabRetry(lambda: False, lambda delay, cb: delays.append(delay))
        for _ in range(40):
            retry.attempt()
        self.assertEqual(delays[38], 25)
        self.assertEqual(delays[39], 200)
        closed = overview.GrabRetry(lambda: self.fail('grabbed a closed popup'),
                                    lambda *_: self.fail('scheduled a closed popup'),
                                    closed=lambda: True)
        closed.attempt()

    def test_health_parse_ignores_noise(self):
        health = load('mintbook-health')
        rows = health.parse('noise\nok\twifi\tworking\nfail\tinput\treinstall hook\nsummary\t1\t0\t1\n')
        self.assertEqual([r['status'] for r in rows], ['ok', 'fail'])
        self.assertEqual(rows[1]['detail'], 'reinstall hook')

    def test_health_rows_carry_the_section_they_were_printed_under(self):
        health = load('mintbook-health')
        rows = health.parse('section\tKernel\t\nok\twifi\tworking\n'
                            'section\tAudio\t\nfail\tinput\treinstall hook\n')
        self.assertEqual([r['section'] for r in rows], ['Kernel', 'Audio'])
        self.assertEqual([r['status'] for r in rows], ['ok', 'fail'])

    def test_health_reads_the_repair_command_out_of_the_detail(self):
        health = load('mintbook-health')
        def fix(status, label, detail):
            return health.remedy(dict(status=status, label=label, detail=detail))
        self.assertEqual(fix('fail', 'live policy', 'reset; pkexec bin/power-install'),
                         'pkexec bin/power-install')
        self.assertEqual(fix('warn', 'trimmable services', 'cups — /home/a/bin/service-trim --check'),
                         '/home/a/bin/service-trim --check')
        self.assertEqual(fix('warn', 'firefox video prefs', 'run bin/firefox-video (see docs)'),
                         'bin/firefox-video')
        # A path that merely contains "bin" is not a command, and a passing
        # check is never offered a repair.
        self.assertEqual(fix('fail', 'apply script', '/usr/local/sbin/mintbook-power-apply'), '')
        self.assertEqual(fix('ok', 'live policy', 'pkexec bin/power-install'), '')

    def test_health_skips_unchanged_kernel_and_duplicate_failures(self):
        health = load('mintbook-health')
        with tempfile.TemporaryDirectory() as directory:
            health.STATE = Path(directory) / 'health.json'
            old = dict(kernel=os.uname().release, rows=[dict(status='fail', label='input', detail='old')])
            health.STATE.write_text(json.dumps(old))
            with patch.object(health.subprocess, 'run') as run:
                self.assertEqual(health.check(only_changed=True), old)
                run.assert_not_called()
            result = NS(returncode=1, stdout='fail\tinput\tnew detail\nsummary\t0\t0\t1\n')
            with patch.object(health.subprocess, 'run', return_value=result) as run:
                health.check(notify=True)
                self.assertEqual(run.call_count, 1)  # doctor only; no duplicate notification

    def test_health_rejects_partial_results(self):
        health = load('mintbook-health')
        with tempfile.TemporaryDirectory() as directory:
            health.STATE = Path(directory) / 'health.json'
            result = NS(returncode=1, stdout='ok\twifi\tworking\n')
            with patch.object(health.subprocess, 'run', return_value=result):
                with self.assertRaises(RuntimeError):
                    health.check()
            self.assertFalse(health.STATE.exists())

    def test_health_detail_filters_match_clicked_system_counts(self):
        health = load('mintbook-health')
        window = health.Window.__new__(health.Window)
        window.state = {'rows': [
            {'status': 'ok', 'label': 'a'},
            {'status': 'warn', 'label': 'b'},
            {'status': 'fail', 'label': 'c'},
        ]}
        window.filter = 'notes'
        self.assertEqual([row['label'] for row in window.shown], ['b'])
        window.filter = 'errors'
        self.assertEqual([row['label'] for row in window.shown], ['c'])

    def test_system_menu_reads_doctor_and_update_counts(self):
        system = load('system-menu')
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            health_path = base / 'health.json'
            health_path.write_text(json.dumps({'checked': 12, 'kernel': '7.0', 'rows': [
                {'status': 'ok'}, {'status': 'ok'}, {'status': 'warn'}, {'status': 'fail'}]}))
            updates_path = base / 'updates.state'
            updates_path.write_text('count = 4\nsecurity = 1\nflatpak = 2\nchecked = 10\nerror = \n')
            self.assertEqual(system.health_snapshot(health_path),
                             {'ok': 2, 'warn': 1, 'fail': 1, 'checked': 12.0, 'kernel': '7.0'})
            self.assertEqual(system.updates_snapshot(updates_path)['security'], 1)
            self.assertEqual(system.updates_snapshot(updates_path)['flatpak'], 2)

    def test_system_background_does_not_double_scale_child_controls(self):
        system = load('system-menu')
        surface = system.cairo.ImageSurface(system.cairo.FORMAT_ARGB32, 800, 900)
        context = system.cairo.Context(surface)
        menu = system.Menu.__new__(system.Menu)
        menu.colors = system.LIGHT
        menu.win = NS(get_allocation=lambda: NS(width=755, height=870))
        previous = system.SC
        system.SC = 1.75
        try:
            before = tuple(context.get_matrix())
            system.Menu.draw_background(menu, None, context)
            self.assertEqual(tuple(context.get_matrix()), before)
        finally:
            system.SC = previous

    def test_system_indicator_prioritizes_real_failures(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            cache = base / '.cache/mintbook'; cache.mkdir(parents=True)
            (base / '.config/mintbook').mkdir(parents=True)
            cache.joinpath('health.json').write_text(json.dumps({'rows': [
                {'status': 'warn'}, {'status': 'fail'}, {'status': 'ok'}]}))
            (base / '.config/mintbook/updates.conf').write_text('')
            cache.joinpath('updates.state').write_text(
                'count = 5\nsecurity = 2\nchecked = 10\nerror = \n')
            result = subprocess.run([str(ROOT / 'bin/panel-system')],
                                    env={**os.environ, 'HOME': directory}, text=True,
                                    capture_output=True, check=True)
            self.assertIn('system-alert.svg</img>', result.stdout)
            self.assertIn('<tool>System\n1 error · 5 updates</tool>', result.stdout)

    def test_awake_status_rejects_expired_and_reused_process_ids(self):
        awake = load('keep-awake')
        with tempfile.TemporaryDirectory() as directory:
            awake.STATE = Path(directory) / 'awake.json'
            pid = os.getpid()
            start = Path(f'/proc/{pid}/stat').read_text().split(') ', 1)[1].split()[19]
            state = dict(pid=pid, start=start, until=time.monotonic() + 61)
            awake.STATE.write_text(json.dumps(state))
            self.assertEqual(awake.status(), 2)
            state['start'] = 'stale'
            awake.STATE.write_text(json.dumps(state))
            self.assertEqual(awake.status(), 0)
            state.update(start=start, until=time.monotonic() - 1)
            awake.STATE.write_text(json.dumps(state))
            self.assertEqual(awake.status(), 0)

    def test_installer_extends_old_snapshot_for_new_files(self):
        installer = load('daily-install')
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            saved = base / '.config/mintbook/daily-install.json'
            saved.parent.mkdir(parents=True)
            saved.write_text(json.dumps(dict(files=[], keys={}, timer=False)))
            destination = base / '.local/bin/new-script'
            destination.parent.mkdir(parents=True)
            destination.write_text('user version')
            with (patch.object(installer, 'HOME', base),
                  patch.object(installer, 'SAVED', saved),
                  patch.object(installer, 'KEYS', {}),
                  patch.object(installer, 'SETTINGS', ()),
                  patch.object(installer, 'targets', return_value=[(base / 'source', destination)])):
                data = installer.snapshot()
            self.assertEqual(len(data['files']), 1)
            backup = Path(data['files'][0]['backup'])
            self.assertEqual(backup.read_text(), 'user version')
            # A second rerun keeps the first extension backup.
            with (patch.object(installer, 'HOME', base),
                  patch.object(installer, 'SAVED', saved),
                  patch.object(installer, 'KEYS', {}),
                  patch.object(installer, 'SETTINGS', ()),
                  patch.object(installer, 'targets', return_value=[(base / 'source', destination)])):
                again = installer.snapshot()
            self.assertEqual(again['files'], data['files'])

    def test_installer_extends_old_snapshot_for_new_settings(self):
        installer = load('daily-install')
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            saved = base / 'daily-install.json'
            saved.write_text(json.dumps(dict(files=[], keys={}, timer=False)))
            missing = NS(returncode=1, stdout='')
            setting = ('power', '/lid-on-ac', 'uint', '1')
            with (patch.object(installer, 'SAVED', saved),
                  patch.object(installer, 'SETTINGS', (setting,)),
                  patch.object(installer, 'targets', return_value=[]),
                  patch.object(installer, 'run', return_value=missing)):
                data = installer.snapshot()
            self.assertEqual(data['settings'], {'power\n/lid-on-ac': None})

    def test_writes_coalesce_until_previous_finishes(self):
        Panel = panel_class()
        panel = Panel.__new__(Panel)
        sent, updated = [], []
        panel.dismissing = False
        panel._send_value = lambda tile: sent.append(tile.requested_value)
        tile = NS(update=updated.append, pressing=True, pending=None)
        panel.set_value(tile, 5)
        panel.set_value(tile, 10)
        panel.set_value(tile, 15)
        self.assertEqual(sent, [5])
        panel._set_done(tile, 5, {'value': 5}, None)
        self.assertEqual(sent, [5, 15])
        self.assertEqual(updated, [])
        # While still pressing, intermediate completion does not overwrite visual state.
        panel._set_done(tile, 15, {'value': 15}, None)
        self.assertEqual(updated, [])
        tile.pressing = False
        panel.set_value(tile, 20)
        panel._set_done(tile, 20, {'value': 20}, None)
        self.assertEqual(updated, [{'value': 20}])
        self.assertFalse(tile.setting)

    def test_tab_visits_toggle_and_detail_without_activation(self):
        Panel = panel_class()
        panel = Panel.__new__(Panel)
        panel.menu = NS(get_visible=lambda: False)
        tile = NS(spec={'kind': 'toggle', 'detail': 'wifi-menu'})
        panel.tiles = [tile]
        panel.key_target = None
        panel.queue_tiles = lambda: None
        event = NS(keyval=Gdk.KEY_Tab, state=0)
        panel.on_key(None, event)
        self.assertEqual(panel.key_target, (tile, 'value'))
        panel.on_key(None, event)
        self.assertEqual(panel.key_target, (tile, 'detail'))
        self.assertEqual(tile.keyboard_part, 'detail')
        event.state = Gdk.ModifierType.SHIFT_MASK
        panel.on_key(None, event)
        self.assertEqual(panel.key_target, (tile, 'value'))

    def test_slider_keyboard_clamps(self):
        Panel = panel_class()
        panel = Panel.__new__(Panel)
        tile = NS(spec={'kind': 'slider', 'value': 99})
        tile.number = lambda: float(tile.spec['value'])
        panel.tiles = [tile]
        panel.key_target = (tile, 'value')
        panel.menu = NS(get_visible=lambda: False)
        panel.queue_tiles = lambda: None
        calls = []
        panel.set_value = lambda t, v: calls.append(v)
        panel.on_key(None, NS(keyval=Gdk.KEY_Right, state=0))
        panel.on_key(None, NS(keyval=Gdk.KEY_Home, state=0))
        self.assertEqual(calls, [100, 0])

    def test_menu_refresh_does_not_activate_different_device(self):
        keys = load('mintbook_keys.py')
        activated = []
        class DeviceRow:
            interactive=True; LINE=30; LEAD=20; h=60; hit=None
            visible=[{'path': 'speaker-one'}]
            def test(self,x,y): return 0
            def release(self,x,y): activated.append(self.visible[0]['path'])
        row = DeviceRow()
        panel = NS(rows=[row], area=NS(queue_draw=lambda: None))
        keys.key(panel, NS(keyval=Gdk.KEY_Tab,state=0), 350)
        row.visible = [{'path': 'speaker-two'}]
        keys.key(panel, NS(keyval=Gdk.KEY_Return,state=0), 350)
        self.assertEqual(activated, [])
        keys.key(panel, NS(keyval=Gdk.KEY_Return,state=0), 350)
        self.assertEqual(activated, ['speaker-two'])

    def test_spotlight_includes_mintdrop_night_light_and_input_feel(self):
        actions = load('spotlight-actions')
        self.assertEqual(actions.ACTIONS['mintdrop'][3], ['mintdrop-menu'])
        self.assertEqual(actions.ACTIONS['wallpaper'][3], ['login-settings'])
        self.assertEqual(actions.ACTIONS['cpu'][3], ['cpu-menu'])
        self.assertEqual(actions.ACTIONS['night-on'][3], ['night-apply', 'on'])
        self.assertEqual(actions.ACTIONS['night-auto'][3], ['night-apply', 'auto'])
        self.assertEqual(actions.ACTIONS['night-off'][3], ['night-apply', 'off'])
        self.assertEqual(actions.ACTIONS['input-feel'][3], ['input-feel'])

    def test_login_settings_imports_time_used_by_window_fade(self):
        ls = load('login-settings')
        self.assertTrue(hasattr(ls, 'time'))

    def test_login_settings_background_preserves_cairo_matrix_and_glides(self):
        import cairo
        ls = load('login-settings')
        ls.cairo = cairo
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 960, 700)
        context = cairo.Context(surface)
        win = ls.Window.__new__(ls.Window)
        win.colors = ls.LIGHT
        win.win = NS(get_allocation=lambda: NS(width=900, height=620))
        before = tuple(context.get_matrix())
        ls.Window.draw_background(win, None, context)
        self.assertEqual(tuple(context.get_matrix()), before)

    def test_daily_install_registers_full_placement_and_helpers(self):
        installer = load('daily-install')
        self.assertEqual(installer.KEYS.get('<Super>Up'), 'full')
        self.assertIn('input-feel', installer.SCRIPTS)
        self.assertIn('hud-notify', installer.SCRIPTS)
        self.assertIn('app-grid', installer.SCRIPTS)
        self.assertIn('login-settings', installer.SCRIPTS)
        self.assertIn('mintdrop-menu', installer.SCRIPTS)

    def test_window_place_full_preserves_original_geometry_for_restore(self):
        wp = load('window-place')
        calls = []
        props = {
            '_NET_WM_WINDOW_TYPE': '_NET_WM_WINDOW_TYPE_NORMAL',
            '_NET_WM_PID': '4242',
            'WM_CLASS': '"terminal"',
            '_NET_WM_STATE': '',
            '_NET_FRAME_EXTENTS': '0, 0, 0, 0',
        }
        foreign = NS(get_origin=lambda: (True, 200, 150),
                     get_width=lambda: 900, get_height=lambda: 600)
        work = NS(x=0, y=52, width=1920, height=1148)
        display = NS(get_monitor_at_window=lambda _w: NS(get_workarea=lambda: work))
        with tempfile.TemporaryDirectory() as tmp:
            wp.STATE = Path(tmp) / 'windows.json'
            with (patch.object(wp, 'run', side_effect=lambda *a: '101' if a == ('xdotool', 'getactivewindow') else calls.append(a) or ''),
                  patch.object(wp, 'prop', side_effect=lambda _w, k: props[k]),
                  patch('gi.repository.Gdk.Display.get_default', return_value=display),
                  patch('gi.repository.GdkX11.X11Window.foreign_new_for_display', return_value=foreign)):
                wp.place('left')
                wp.place('full')
                wp.place('restore')
        move_Half = ('wmctrl', '-ir', '101', '-e', '0,0,52,960,1148')
        move_Full = ('wmctrl', '-ir', '101', '-e', '0,0,52,1920,1148')
        move_Restore = ('wmctrl', '-ir', '101', '-e', '0,200,150,900,600')
        self.assertIn(move_Half, calls)
        self.assertIn(move_Full, calls)
        self.assertIn(move_Restore, calls)

    def test_hud_notify_parses_and_coalesces_over_datagram_socket(self):
        hud = load('hud-notify')
        self.assertEqual(hud.parse_args(['volume', 'Volume', '65']),
                         ('send', 'volume', 'Volume', 65))
        self.assertEqual(hud.parse_args(['mic-off', 'Mic muted']),
                         ('send', 'mic-off', 'Mic muted', None))
        self.assertEqual(hud.parse_args(['brightness', 'Brightness', '80']),
                         ('send', 'brightness', 'Brightness', 80))
        with tempfile.TemporaryDirectory() as tmp:
            hud.write_state('volume', 'Volume', 50, directory=tmp)
            self.assertEqual(hud.read_state(directory=tmp),
                             {'kind': 'volume', 'title': 'Volume', 'value': 50})
            _, sock_path = hud.state_paths(tmp)
            server = hud.socket.socket(hud.socket.AF_UNIX, hud.socket.SOCK_DGRAM)
            server.bind(str(sock_path))
            try:
                self.assertTrue(hud.notify_running(directory=tmp))
                self.assertEqual(server.recv(1024), b'update')
            finally:
                server.close()

    def test_all_gtk_surfaces_set_adwaita_and_popups_use_workarea(self):
        for name in ('control-center', 'system-menu', 'cpu-menu', 'battery-menu',
                     'wifi-menu', 'bt-menu', 'updates-menu', 'app-grid',
                     'login-settings', 'mintbook-health', 'battery-history',
                     'mintdrop-menu', 'mintdrop-accept', 'hud-notify',
                     'screenshot', 'screenshot-notify', 'overview'):
            source = (ROOT / 'bin' / name).read_text()
            self.assertIn('Adwaita', source, name)
        for popup in ('control-center', 'system-menu', 'cpu-menu', 'battery-menu',
                      'wifi-menu', 'bt-menu', 'updates-menu'):
            source = (ROOT / 'bin' / popup).read_text()
            self.assertIn('get_workarea()', source, popup)

    def test_cairo_overview_parses_filter_and_ranks_matches(self):
        ov = load('overview')
        self.assertEqual(ov.parse_args([]), '')
        self.assertEqual(ov.parse_args(['--filter', 'wall']), 'wall')
        with self.assertRaises(ValueError):
            ov.parse_args(['--unknown'])
        entries = [
            {'kind': 'app', 'title': 'Firefox', 'keywords': 'web browser'},
            {'kind': 'action', 'title': 'Choose Wallpaper', 'keywords': 'background desktop login picture'},
            {'kind': 'action', 'title': 'Open Control Center', 'keywords': 'settings brightness volume'},
        ]
        matched = ov.filter_entries(entries, 'wall')
        self.assertEqual([e['title'] for e in matched], ['Choose Wallpaper'])
        fuzzy = ov.filter_entries(entries, 'ffx')
        self.assertEqual([e['title'] for e in fuzzy], ['Firefox'])

    def test_screenshot_notify_prefers_glass_toast_and_falls_back_cleanly(self):
        sn = load('screenshot-notify')
        with tempfile.TemporaryDirectory() as tmp:
            img = Path(tmp) / 'shot.png'
            img.write_bytes(b'png')
            with (patch.object(sn, 'sys', NS(argv=['screenshot-notify', str(img)], stderr=sn.sys.stderr)),
                  patch.object(sn, 'show_toast', return_value=True) as toast,
                  patch.object(sn.subprocess, 'run') as notify_run):
                sn.main()
                toast.assert_called_once_with(img.resolve())
                notify_run.assert_not_called()

if __name__ == '__main__':
    unittest.main()
