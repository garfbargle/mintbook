"""Sleep-cycle measurements and verdicts from synthetic resume records."""
import importlib.machinery
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
loader = importlib.machinery.SourceFileLoader('sleep_report', str(ROOT / 'bin/sleep-report'))
sleep = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
loader.exec_module(sleep)


def snap(status='Discharging', percent=80, wh=30):
    return {'timestamp': 1000.0,
            'battery': {'status': status, 'percent': percent, 'wh': wh,
                        'temperature_c': 35},
            'input': {'keyboard': True, 'touchpad': True},
            'wifi': 'connected', 'bluetooth': 'powered',
            'audio_sink': 'input.MacBook_Speaker'}


def recovered(keyboard=True, touchpad=True, wifi='connected'):
    return {'input': {'keyboard': keyboard, 'touchpad': touchpad},
            'wifi': wifi, 'bluetooth': 'powered',
            'audio_sink': 'input.MacBook_Speaker',
            'first': {'wifi': 1.25, 'audio': 0.2}}


def event(timestamp, message, priority=6):
    return {'timestamp': timestamp, 'priority': priority,
            'identifier': 'kernel', 'message': message}


class SleepReportTests(unittest.TestCase):
    def test_arm_is_idempotent_for_spotlight(self):
        with (patch.object(sleep, 'unit_active', return_value=True),
              patch.object(sleep, 'load_json', return_value={'armed_at': 1000}),
              patch.object(sleep, 'notify') as notify,
              patch('builtins.print')):
            self.assertEqual(sleep.arm(), 0)
        notify.assert_called_once()

    def test_battery_drain_uses_sleep_duration(self):
        before = snap()['battery']
        after = dict(before, percent=78, wh=29.4)
        result = sleep.battery_change(before, after, 7200)
        self.assertTrue(result['measurable'])
        self.assertEqual(result['percent_points'], 2)
        self.assertAlmostEqual(result['wh'], .6)
        self.assertAlmostEqual(result['average_watts'], .3)

    def test_battery_source_change_is_not_called_drain(self):
        before = snap()['battery']
        after = dict(before, status='Charging', wh=31)
        result = sleep.battery_change(before, after, 3600)
        self.assertFalse(result['measurable'])
        self.assertIn('power source changed', result['reason'])

    def test_gauge_increase_is_not_negative_drain(self):
        before = snap()['battery']
        after = dict(before, wh=30.2)
        result = sleep.battery_change(before, after, 3600)
        self.assertFalse(result['measurable'])
        self.assertIn('gauge rose', result['reason'])

    def test_clean_resume_passes_with_kernel_timing(self):
        before = snap()
        after = dict(before['battery'], percent=79, wh=29.8)
        rows = [event(1000, 'PM: suspend entry (deep)'),
                event(4599.2, 'ACPI: PM: Waking up from system sleep state S3'),
                event(4600, 'PM: suspend exit'),
                event(4603, 'rebind ok on attempt 1 — touchpad is back')]
        with patch.object(sleep, 'boot_id', return_value='boot'):
            report = sleep.analyze(before, after, recovered(), 3600, 4600, rows)
        self.assertEqual(report['verdict'], 'pass')
        self.assertAlmostEqual(report['kernel_resume_seconds'], .8)
        self.assertEqual(report['spi_timeouts'], 0)
        self.assertEqual(report['concerns'], [])

    def test_missing_input_and_timeouts_fail(self):
        before = snap()
        rows = [event(1000, 'PM: suspend entry (deep)'),
                event(4599, 'SPI transfer timed out'),
                event(4600, 'rebind FAILED after 3 attempts')]
        report = sleep.analyze(before, before['battery'],
                               recovered(touchpad=False), 3600, 4600, rows)
        self.assertEqual(report['verdict'], 'fail')
        self.assertEqual(report['spi_timeouts'], 1)
        self.assertTrue(any('input is missing' in item for item in report['concerns']))

    def test_absent_rebind_and_suspend_marker_are_notes(self):
        before = snap()
        report = sleep.analyze(before, before['battery'], recovered(),
                               60, 1060, [])
        self.assertEqual(report['verdict'], 'note')
        self.assertEqual(len(report['notes']), 2)

    def test_journal_keeps_resume_markers_and_errors(self):
        source = '\n'.join(json.dumps(item) for item in (
            {'__REALTIME_TIMESTAMP': '1000000', 'PRIORITY': '6',
             'SYSLOG_IDENTIFIER': 'kernel', 'MESSAGE': 'PM: suspend entry (deep)'},
            {'__REALTIME_TIMESTAMP': '2000000', 'PRIORITY': '6',
             'MESSAGE': 'ordinary chatter'},
            {'__REALTIME_TIMESTAMP': '3000000', 'PRIORITY': '3',
             'MESSAGE': 'device error'}))
        with patch.object(sleep, 'run', return_value=source):
            rows = sleep.journal(0, 4)
        self.assertEqual([row['message'] for row in rows],
                         ['PM: suspend entry (deep)', 'device error'])

    def test_format_report_labels_the_measurement_as_average(self):
        before = snap()
        rows = [event(1000, 'PM: suspend entry (deep)'),
                event(4600, 'rebind ok on attempt 1')]
        report = sleep.analyze(before, dict(before['battery'], wh=29.5),
                               recovered(), 3600, 4600, rows)
        output = sleep.format_report(report)
        self.assertIn('0.50 W average', output)
        self.assertIn('keyboard + trackpad present', output)


if __name__ == '__main__':
    unittest.main()
