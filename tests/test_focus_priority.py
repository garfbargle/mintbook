"""Scheduling policy must follow helpers, survive PID reuse and undo cleanly."""
import importlib.machinery
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

loader = importlib.machinery.SourceFileLoader('focus_priority', str(Path(__file__).parents[1] / 'bin/focus-priority'))
focus = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
loader.exec_module(focus)


def process(parent=1):
    return {'parent': parent}


def thread(pid, nice=0, start=10):
    return {'pid': pid, 'nice': nice, 'start': start}


class FocusPolicyTests(unittest.TestCase):
    def test_helpers_follow_ancestry_regardless_of_cgroup(self):
        procs = {10: process(), 11: process(10), 12: process(11), 20: process()}
        tasks = {10: thread(10, -5), 11: thread(11), 12: thread(12), 20: thread(20)}
        changes, state = focus.policy(procs, tasks, {10, 20}, 20, {})
        self.assertEqual({tid: row['applied'] for tid, row in state.items()},
                         {'10': 5, '11': 5, '12': 5, '20': 0})
        self.assertIn((10, 10, 5), changes)

    def test_focus_restores_background_and_preserves_deliberate_low_priority(self):
        procs = {10: process(), 20: process()}
        _, before = focus.policy(procs, {10: thread(10), 20: thread(20, 7)}, {10, 20}, 20, {})
        changes, after = focus.policy(procs, {10: thread(10, 5), 20: thread(20, 7)}, {10, 20}, 10, before)
        self.assertIn((10, 10, 0), changes)
        self.assertEqual(after['20']['applied'], 12)
        self.assertEqual(after['20']['restore'], 7)

    def test_new_background_child_recovers_original_baseline(self):
        procs = {10: process(), 20: process()}
        _, before = focus.policy(procs, {10: thread(10), 20: thread(20)}, {10, 20}, 20, {})
        procs[11] = process(10)
        changes, after = focus.policy(procs, {10: thread(10, 5), 11: thread(11, 5), 20: thread(20)}, {10, 20}, 10, before)
        self.assertIn((11, 10, 0), changes)
        self.assertEqual(after['11']['restore'], 0)

    def test_new_thread_of_background_process_recovers_baseline(self):
        procs = {10: process(), 20: process()}
        _, before = focus.policy(procs, {10: thread(10), 20: thread(20)}, {10, 20}, 20, {})
        _, after = focus.policy(procs, {10: thread(10, 5), 99: thread(10, 5), 20: thread(20)}, {10, 20}, 10, before)
        self.assertEqual(after['99']['applied'], 0)

    def test_reused_pid_does_not_inherit_old_restore_value(self):
        procs = {10: process()}
        old = {'10': {'start': 1, 'base': 0, 'restore': -5, 'applied': 5}}
        _, state = focus.policy(procs, {10: thread(10, 8, start=2)}, {10}, 10, old)
        self.assertEqual(state['10']['restore'], 8)

    def test_external_priority_change_is_left_alone(self):
        procs = {10: process()}
        old = {'10': {'start': 10, 'base': 0, 'restore': 0, 'applied': 5}}
        changes, state = focus.policy(procs, {10: thread(10, 12)}, {10}, 10, old)
        self.assertEqual(changes, [])
        self.assertTrue(state['10']['external'])

    def test_closed_window_restores_owned_threads(self):
        old = {'10': {'start': 10, 'base': 0, 'restore': -5, 'applied': 5}}
        changes, state = focus.policy({10: process()}, {10: thread(10, 5)}, set(), None, old)
        self.assertEqual(changes, [(10, 10, -5)])
        self.assertFalse(state)

    def test_unknown_focus_is_neutral_and_audio_priority_is_preserved(self):
        _, state = focus.policy({10: process(), 20: process()}, {10: thread(10), 20: thread(20, -11)}, {10, 20}, None, {})
        self.assertEqual(state['10']['applied'], 0)
        self.assertNotIn('20', state)

    def test_nested_window_uses_outer_application(self):
        self.assertEqual(focus.owner(11, {10, 11}, {10: process(), 11: process(10)}), 10)
        self.assertIsNone(focus.owner(10, set(), {10: process(11), 11: process(10)}))


class RecoveryTests(unittest.TestCase):
    def test_interrupted_batch_restores_both_written_and_unwritten_threads(self):
        before = {str(t): {'start': 10, 'base': 0, 'restore': 0, 'applied': 5}
                  for t in (10, 11, 12)}
        after = {t: {**row, 'applied': 0} for t, row in before.items()}
        pending = focus.recovery_records(before, after, {t: thread(t, 5) for t in (10, 11, 12)})
        # One write landed, one did not; the third was changed externally.
        with patch.object(focus, 'load', return_value=pending), \
                patch.object(focus.os, 'getpriority', side_effect=[0, 5, 9]), \
                patch.object(focus, 'change', return_value=True) as change, \
                patch.object(focus, 'STATE'):
            self.assertEqual(focus.restore(), 0)
        self.assertEqual([c.args for c in change.call_args_list], [(10, 10, 0), (11, 10, 0)])
        self.assertNotIn('before', before['10'])


if __name__ == '__main__':
    unittest.main()
