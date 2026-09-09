"""Battery history must survive missing samples and changing cadence."""
import importlib.machinery
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


loader = importlib.machinery.SourceFileLoader('battery_history', str(Path(__file__).resolve().parents[1] / 'bin/battery-history'))
battery = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
loader.exec_module(battery)  # no display or GTK required


def row(ts, watts=5, dt=60, state='D', cores=1):
    return dict(ts=ts, pct=80, st=state, w=watts, dt=dt,
                total=4 * battery.CLK * dt, busy=cores * battery.CLK * dt,
                apps={'firefox-bin': cores * battery.CLK * dt})


def measured(rows, start, end):
    parts = battery.intervals(rows, start, end)
    total, _apps, cpu, _floor, seconds = battery.energy(parts, None, None)
    return parts, total, cpu, seconds


class BatteryHistoryTests(unittest.TestCase):
    def test_live_percentage_uses_present_full_capacity(self):
        with tempfile.TemporaryDirectory() as directory:
            bat = Path(directory) / 'BAT0'
            bat.mkdir()
            values = {
                'status': 'Discharging', 'capacity': '62',
                'charge_now': '3285000', 'charge_full': '4382000',
                'charge_full_design': '5297000', 'cycle_count': '158',
                'temp': '372', 'voltage_min_design': '7600000',
            }
            for name, value in values.items():
                (bat / name).write_text(value)
            with patch.object(battery, 'POWER_SUPPLY_ROOT', directory):
                facts = battery.battery_facts()
        self.assertEqual(facts['pct'], 75)
        self.assertEqual(facts['health'], 82)

    def test_full_state_is_one_hundred_percent(self):
        with tempfile.TemporaryDirectory() as directory:
            bat = Path(directory) / 'BAT0'
            bat.mkdir()
            values = {
                'status': 'Full', 'capacity': '81', 'charge_now': '4300000',
                'charge_full': '4382000', 'charge_full_design': '5297000',
            }
            for name, value in values.items():
                (bat / name).write_text(value)
            with patch.object(battery, 'POWER_SUPPLY_ROOT', directory):
                facts = battery.battery_facts()
        self.assertEqual(facts['pct'], 100)

    def test_raw_capacity_is_fallback_without_charge_counters(self):
        with tempfile.TemporaryDirectory() as directory:
            bat = Path(directory) / 'BAT0'
            bat.mkdir()
            (bat / 'status').write_text('Discharging')
            (bat / 'capacity').write_text('47')
            with patch.object(battery, 'POWER_SUPPLY_ROOT', directory):
                facts = battery.battery_facts()
        self.assertEqual(facts['pct'], 47)

    def test_constant_power_integrates_to_known_energy(self):
        rows = [row(t, 6) for t in range(0, 3601, 60)]
        parts, total, cpu, seconds = measured(rows, 0, 3600)
        self.assertAlmostEqual(total, 6)
        self.assertEqual(seconds, 3600)
        self.assertEqual(sum(r['dt'] for r in parts), 3600)
        self.assertEqual(cpu, {'firefox-bin': 3600})

    def test_selection_clips_both_energy_and_cpu(self):
        parts, total, cpu, _seconds = measured([row(0), row(60, 6)], 15, 45)
        self.assertAlmostEqual(total, .05)
        self.assertEqual(cpu, {'firefox-bin': 30})
        self.assertEqual(sum(r['dt'] for r in parts), 30)

    def test_transition_does_not_charge_ac_time_to_battery(self):
        rows = [row(0, state='C'), row(60), row(120)]
        parts, _total, _cpu, seconds = measured(rows, 0, 120)
        self.assertEqual(seconds, 60)
        self.assertEqual(sum(r['dt'] for r in parts), 60)

    def test_long_suspend_with_nonzero_dt_is_unknown(self):
        rows = [row(0), row(60), row(1860, dt=1800), row(1920)]
        parts, _total, _cpu, seconds = measured(rows, 0, 1920)
        self.assertEqual(seconds, 120)
        self.assertEqual(sum(r['dt'] for r in parts), 120)

    def test_restart_zero_dt_and_missing_line_are_unknown(self):
        for last in (row(120, dt=0), row(120, dt=60)):
            self.assertEqual(battery.intervals([row(0), last], 0, 120), [])

    def test_zero_power_discharge_and_unknown_state_are_not_observations(self):
        for rows in ([row(0), row(60, 0)], [row(0, state='U'), row(60, state='U')]):
            self.assertEqual(battery.intervals(rows, 0, 60), [])

    def test_samples_do_not_imply_coverage_before_or_after_log(self):
        parts = battery.intervals([row(60), row(120)], 0, 180)
        self.assertEqual(sum(r['dt'] for r in parts), 60)

    def test_weighting_does_not_reward_faster_sampling(self):
        slow = [row(t, 9 if t <= 1200 else 3) for t in range(0, 3601, 60)]
        fast = [row(t, 9, dt=10) for t in range(0, 1201, 10)]
        fast += [row(t, 3) for t in range(1260, 3601, 60)]
        a = measured(slow, 0, 3600)
        b = measured(fast, 0, 3600)
        self.assertAlmostEqual(a[1], b[1])
        self.assertAlmostEqual(a[3], b[3])

    def test_empty_history_is_honest(self):
        self.assertEqual(battery.intervals([], 0, 3600), [])
        self.assertEqual(battery.energy([], None, None), (0.0, {}, {}, 0.0, 0.0))

    def test_fit_requires_time_as_well_as_sample_count(self):
        rows = [row(t, 3 + i % 3, dt=10, cores=i % 3) for i, t in enumerate(range(10, 301, 10))]
        self.assertIsNone(battery.fit(rows)[0])

    def test_fit_recovers_known_relationship_and_rejects_flat_cpu(self):
        rows = [row(i * 60, 3 + 2 * (i % 3), cores=i % 3) for i in range(30)]
        base, slope, _ = battery.fit(rows)
        self.assertAlmostEqual(base, 3)
        self.assertAlmostEqual(slope, 2)
        self.assertIsNone(battery.fit([row(i * 60) for i in range(30)])[0])

    def test_weak_positive_relationship_is_not_attributed(self):
        rows = [row(i * 60, 10 + .01 * (i % 3) + (i % 2) * 8,
                    cores=i % 3) for i in range(60)]
        self.assertIsNone(battery.fit(rows)[0])

    def test_parser_rejects_corruption_and_duplicate_or_backward_timestamps(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'history'
            path.write_text('100 80 D 6000 0 0 0\n'
                            '160 79 D 6000 60 24000 6000 firefox-bin:6000\n'
                            '160 79 D 6000 60 24000 6000\n'
                            '150 79 D 6000 60 24000 6000\n'
                            '180 101 D 6000 60 24000 6000\n'
                            '200 79 D -1 60 24000 6000\n'
                            '210 79 D 6000 60 24000 6000 app:-1\n'
                            '220 79 D 6000 60 24000 6000 app:nope\n'
                            '230 79 D 6000 60 24000 6000 app:1 app:2\n'
                            'partial line\n')
            with patch.object(battery, 'LOG', str(path)), patch.object(battery.time, 'time', return_value=300):
                rows = battery.load(300)
        self.assertEqual([r['ts'] for r in rows], [100, 160, 230])
        self.assertEqual(rows[-1]['apps'], {'app': 3})


if __name__ == '__main__':
    unittest.main()
