"""config/systemd/system-sleep/mintbook-brcmfmac — the s2idle recovery.

The hibernate unload is exercised on the machine (docs/hibernate.md, Tests
M-P). The s2idle wedge cannot be provoked without wedging the firmware, so the
recovery's decision is driven here instead: with a fake nmcli, modprobe and
systemd-run, it must reload only when the card was connected before sleep and
has not reconnected.
"""
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOOK = REPO / 'config/systemd/system-sleep/mintbook-brcmfmac'
FLAG = 'brcmfmac-was-connected'


class HookTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.bindir = self.root / 'bin'
        self.bindir.mkdir()
        self.state = self.root / 'state'
        self.modprobe_log = self.root / 'modprobe.log'
        self.run_log = self.root / 'systemd-run.log'
        self.modules = self.root / 'modules'
        self.modules.write_text('')
        # The hook checks /proc/modules after modprobe. Model that state as
        # well as the calls: CI must not require the host's Broadcom driver.
        self._fake('grep',
                   '#!/bin/sh\n'
                   'if [ "$#" = 3 ] && [ "$3" = /proc/modules ]; then\n'
                   '  exec /usr/bin/grep "$1" "$2" "$FAKE_MODULES"\n'
                   'fi\nexec /usr/bin/grep "$@"\n')
        self._fake('nmcli',
                   '#!/bin/sh\n'
                   'printf "%s\\n" "${FAKE_NMCLI_STATE:-wifi:disconnected}"\n')
        self._fake('modprobe',
                   '#!/bin/sh\nprintf "%s\\n" "$*" >> "$FAKE_MODPROBE_LOG"\n'
                   'if [ "$1" = -r ]; then\n'
                   '  sed -i "/^$2 /d" "$FAKE_MODULES"\n'
                   'else\n'
                   '  printf "%s 0 0 - Live 0x0\\n" "$1" >> "$FAKE_MODULES"\n'
                   'fi\n')
        self._fake('systemd-run',
                   '#!/bin/sh\nprintf "%s\\n" "$*" >> "$FAKE_SYSTEMD_RUN_LOG"\n')

    def tearDown(self):
        self._tmp.cleanup()

    def _fake(self, name, body):
        path = self.bindir / name
        path.write_text(body)
        path.chmod(path.stat().st_mode | stat.S_IEXEC)
        return path

    def _run(self, *args, state='connected', timeout='1'):
        env = dict(os.environ)
        env.update({
            'PATH': f'{self.bindir}:{os.environ["PATH"]}',
            'FAKE_NMCLI_STATE': f'wifi:{state}',
            'FAKE_MODPROBE_LOG': str(self.modprobe_log),
            'FAKE_MODULES': str(self.modules),
            'FAKE_SYSTEMD_RUN_LOG': str(self.run_log),
            'MINTBOOK_WIFI_STATE_DIR': str(self.state),
            'MINTBOOK_WIFI_RECOVER_TIMEOUT': timeout,
        })
        return subprocess.run(['sh', str(HOOK), *args], env=env, text=True,
                              capture_output=True, check=False)

    def _set_flag(self):
        self.state.mkdir(parents=True, exist_ok=True)
        (self.state / FLAG).write_text('')

    def _modprobe_lines(self):
        try:
            return self.modprobe_log.read_text().splitlines()
        except OSError:
            return []


class Recover(HookTestCase):
    def test_a_connected_card_needs_no_reload(self):
        result = self._run('--recover', state='connected')
        self.assertEqual(result.returncode, 0)
        self.assertIn('no reload needed', result.stdout)
        self.assertEqual(self._modprobe_lines(), [])

    def test_a_card_that_stays_down_is_reloaded(self):
        result = self._run('--recover', state='disconnected', timeout='1')
        self.assertEqual(result.returncode, 0)
        lines = self._modprobe_lines()
        # Both module calls and loaded-state probes use the fixture; the host
        # never needs to have a Broadcom driver loaded.
        self.assertIn('brcmfmac_wcc', lines)
        self.assertIn('brcmfmac', lines)
        self.assertIn('reloading brcmfmac', result.stderr)
        self.assertIn('brcmfmac reloaded', result.stdout)


class SuspendLegs(HookTestCase):
    def test_pre_suspend_flags_a_connected_card(self):
        self._run('pre', 'suspend', state='connected')
        self.assertTrue((self.state / FLAG).exists())

    def test_pre_suspend_clears_a_stale_flag(self):
        self._set_flag()
        self._run('pre', 'suspend', state='disconnected')
        self.assertFalse((self.state / FLAG).exists())

    def test_post_suspend_schedules_recovery_only_when_flagged(self):
        self._set_flag()
        self._run('post', 'suspend', state='disconnected')
        self.assertTrue(self.run_log.exists())
        logged = self.run_log.read_text()
        self.assertIn('--unit=mintbook-wifi-recover', logged)
        self.assertIn('--recover', logged)
        # The reload decision is the recovery unit's, not the hook's.
        self.assertEqual(self._modprobe_lines(), [])

    def test_post_suspend_does_nothing_when_nothing_was_connected(self):
        self._run('post', 'suspend', state='disconnected')
        self.assertFalse(self.run_log.exists())
        self.assertEqual(self._modprobe_lines(), [])


class HibernateLegs(HookTestCase):
    def test_post_hibernate_reloads_the_driver(self):
        self._run('post', 'hibernate', state='disconnected')
        lines = self._modprobe_lines()
        self.assertIn('brcmfmac_wcc', lines)
        self.assertIn('brcmfmac', lines)
        self.assertFalse(self.run_log.exists())


if __name__ == '__main__':
    unittest.main()
