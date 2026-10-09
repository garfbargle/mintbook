"""Security regressions use temporary files; no root or real hardware writes."""
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'bin'))
import mintbook_drop as drop
import mintbook_quickshare as qs


class IncomingFiles(unittest.TestCase):
    def test_sender_selected_part_symlink_is_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp); inbox = base / 'inbox'; inbox.mkdir()
            victim = base / 'important'; victim.write_bytes(b'original')
            (inbox / 'report.txt.part').symlink_to(victim)
            entry = qs.Incoming(1, 'report.txt', 4)
            entry.open(str(inbox)); entry.write(0, b'data')
            landed = entry.finish()
            self.assertEqual(victim.read_bytes(), b'original')
            self.assertEqual(Path(landed).read_bytes(), b'data')

    def test_overlapping_receivers_have_distinct_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = qs.Incoming(1, 'same.txt', 4); b = qs.Incoming(2, 'same.txt', 4)
            a.open(tmp); b.open(tmp)
            a.write(0, b'AAAA'); first = a.finish()
            b.write(0, b'BBBB'); second = b.finish()
            self.assertNotEqual(first, second)
            self.assertEqual(Path(first).read_bytes(), b'AAAA')
            self.assertEqual(Path(second).read_bytes(), b'BBBB')
            self.assertFalse(list(Path(tmp).glob('.mintdrop-*')))

    def test_publication_does_not_overwrite_destination_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp); target = base / 'original'; target.write_text('keep')
            (base / 'incoming.txt').symlink_to(target)
            fd, partial = drop.incoming_temp(tmp); os.write(fd, b'new'); os.close(fd)
            final = drop.publish_file(partial, tmp, 'incoming.txt')
            self.assertNotEqual(final, str(base / 'incoming.txt'))
            self.assertEqual(target.read_text(), 'keep')

    def test_overlapping_or_gapped_offsets_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            entry = qs.Incoming(1, 'offset.bin', 8); entry.open(tmp)
            entry.write(0, b'AAAA')
            for offset in (-1, 0, 5):
                with self.assertRaises(qs.ProtocolError): entry.write(offset, b'BBBB')
            entry.abandon()
            self.assertFalse(list(Path(tmp).iterdir()))

    def test_unicode_names_fit_filesystem_byte_limit(self):
        name = drop.safe_name('界' * 200)
        self.assertLessEqual(len(name.encode()), 200)
        with tempfile.TemporaryDirectory() as tmp:
            fd, partial = drop.incoming_temp(tmp); os.close(fd)
            self.assertTrue(Path(drop.publish_file(partial, tmp, name)).exists())


class PrivilegedHelpers(unittest.TestCase):
    def test_wallpaper_metacharacters_are_literal_and_sections_survive(self):
        source = (ROOT / 'bin/login-apply').read_text()
        code = source.split('<<\'PY\'\nimport pathlib, sys\n', 1)[1].split('\nPY\n', 1)[0]
        code = 'import pathlib, sys\n' + code
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp); conf = base / 'greeter.conf'; result = base / 'result'
            conf.write_text('[Other]\nbackground=keep\n[Greeter]\n# comment\nbackground=old\n')
            hostile = str(base / 'wallpaper|;e printf COMMAND_EXECUTED #$(id)&.png')
            subprocess.run([sys.executable, '-I', '-c', code, str(conf), str(result),
                            hostile, '', '', '', ''], check=True)
            text = result.read_text()
            self.assertIn('background=' + hostile + '\n', text)
            self.assertIn('[Other]\nbackground=keep', text)
            self.assertIn('# comment', text)
            self.assertNotIn('sh -c', source)

    def test_cap_replacement_does_not_follow_symlink(self):
        source = (ROOT / 'bin/power-apply').read_text()
        function = source.split('record_cap() {', 1)[1].split('\n}', 1)[0]
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp); victim = base / 'victim'; victim.write_text('keep')
            cap = base / 'cap'; cap.symlink_to(victim)
            script = 'install() { mkdir -p "${@: -1}"; }; record_cap() {' + function + '\n}; record_cap 70'
            subprocess.run(['bash', '-c', script], env={**os.environ, 'POLICY': str(cap)}, check=True)
            self.assertEqual(victim.read_text(), 'keep')
            self.assertFalse(cap.is_symlink())
            self.assertEqual(cap.read_text(), '70\n')

    def test_request_reader_rejects_symlinks_and_fifos_without_blocking(self):
        source = (ROOT / 'bin/power-apply').read_text()
        code = source.split('<<\'PY\'\nimport os, stat, sys\n', 1)[1].split('\nPY\n', 1)[0]
        code = 'import os, stat, sys\n' + code
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp); regular = base / 'regular'; regular.write_text('balanced\n')
            link = base / 'link'; link.symlink_to(regular)
            fifo = base / 'fifo'; os.mkfifo(fifo)
            for path, expected in ((regular, 0), (link, 1), (fifo, 1)):
                result = subprocess.run([sys.executable, '-I', '-c', code, str(path)],
                                        capture_output=True, text=True, timeout=2)
                self.assertEqual(bool(result.returncode), bool(expected))

class FragmentedProtocol(unittest.TestCase):
    def test_fragmented_prefix_is_collected_and_replayed(self):
        class Fragmented:
            parts = [b'\0', b'\0', b'\0', b'\x20']
            timeouts = []
            def settimeout(self, value): self.timeouts.append(value)
            def recv(self, count): return self.parts.pop(0)
        sock = Fragmented()
        import time
        prefix = drop.read_exactly(sock, 4, deadline=time.monotonic() + 1)
        replay = drop.PrefixedSocket(sock, prefix)
        self.assertEqual(drop.read_exactly(replay, 4), b'\0\0\0\x20')
        self.assertEqual(len(sock.timeouts), 4)
        self.assertTrue(all(0 < t <= 1 for t in sock.timeouts))

    def test_silent_peer_has_a_deadline(self):
        import time
        class Silent:
            def settimeout(self, value): pass
            def recv(self, count): self.fail('expired deadline must not read')
        with self.assertRaises(drop.DropError):
            drop.read_exactly(Silent(), 4, deadline=time.monotonic() - 1)
