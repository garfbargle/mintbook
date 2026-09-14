"""mintdrop must not be talked into writing outside Downloads, and must move
a file byte for byte.

The name handling is the security surface: every filename in a transfer is a
string a stranger chose. The transfer tests run a real sender against a real
receiver over loopback, because the parts worth testing here — splice on a
blocking socket, exact byte counts, the .part rename — only exist when there
is a socket.
"""
import hashlib
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load():
    loader = importlib.machinery.SourceFileLoader(
        'mintbook_drop', str(ROOT / 'bin' / 'mintbook_drop.py'))
    module = importlib.util.module_from_spec(
        importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(module)
    return module


drop = load()


class NameTests(unittest.TestCase):
    def test_traversal_cannot_escape_the_directory(self):
        for hostile in ('../../etc/passwd', '/etc/passwd', '..',
                        'a/b/c.txt', '..\\..\\windows'):
            name = drop.safe_name(hostile)
            self.assertNotIn('/', name)
            self.assertNotIn('\\', name)
            self.assertFalse(name.startswith('.'), name)
            joined = os.path.normpath(os.path.join('/downloads', name))
            self.assertTrue(joined.startswith('/downloads/'), joined)

    def test_control_characters_and_newlines_go(self):
        self.assertEqual(drop.safe_name('re\nport\x00.pdf'), 're_port_.pdf')

    def test_empty_and_dotfiles_become_a_name(self):
        self.assertEqual(drop.safe_name(''), 'received')
        self.assertEqual(drop.safe_name('...'), 'received')
        self.assertEqual(drop.safe_name('.bashrc'), 'bashrc')

    def test_long_names_are_bounded(self):
        self.assertLessEqual(len(drop.safe_name('x' * 900)), 200)

    def test_existing_files_are_never_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            first = drop.unique_path(d, 'report.pdf')
            Path(first).write_text('original')
            second = drop.unique_path(d, 'report.pdf')
            self.assertNotEqual(first, second)
            self.assertTrue(second.endswith('report (2).pdf'))
            self.assertEqual(Path(first).read_text(), 'original')


class AddressTests(unittest.TestCase):
    def test_v4_mapped_peers_are_recognised_as_local(self):
        # The receiver binds one dual-stack socket, so every IPv4 peer arrives
        # mapped. Rejecting these rejected the entire LAN.
        self.assertTrue(drop.is_local_address('::ffff:192.168.1.5'))
        self.assertTrue(drop.is_local_address('::ffff:127.0.0.1'))

    def test_routable_addresses_are_refused(self):
        for address in ('8.8.8.8', '::ffff:8.8.8.8', '2605:59c0::1', 'nonsense'):
            self.assertFalse(drop.is_local_address(address), address)

    def test_private_ranges_are_accepted(self):
        for address in ('10.0.0.1', '192.168.1.5', '172.16.3.2', '169.254.1.1',
                        'fe80::1', 'fd00::1'):
            self.assertTrue(drop.is_local_address(address), address)

    def test_172_is_only_private_in_its_own_range(self):
        self.assertTrue(drop.is_local_address('172.31.255.254'))
        self.assertFalse(drop.is_local_address('172.32.0.1'))


class HeaderTests(unittest.TestCase):
    def roundtrip(self, header):
        left, right = socket.socketpair()
        drop.write_header(left, header)
        try:
            return drop.read_header(right)
        finally:
            left.close()
            right.close()

    def test_a_normal_offer_survives(self):
        name, files, total = self.roundtrip(
            {'name': 'Studio', 'files': [{'name': 'a.pdf', 'size': 12},
                                         {'name': 'b.png', 'size': 30}]})
        self.assertEqual(name, 'Studio')
        self.assertEqual(total, 42)
        self.assertEqual([f['name'] for f in files], ['a.pdf', 'b.png'])

    def test_names_are_sanitised_on_the_way_in(self):
        _name, files, _total = self.roundtrip(
            {'name': 'x', 'files': [{'name': '../../etc/passwd', 'size': 1}]})
        self.assertNotIn('/', files[0]['name'])

    def test_a_lying_size_is_refused(self):
        with self.assertRaises(drop.DropError):
            self.roundtrip({'name': 'x',
                            'files': [{'name': 'a', 'size': -1}]})
        with self.assertRaises(drop.DropError):
            self.roundtrip({'name': 'x',
                            'files': [{'name': 'a', 'size': 1 << 60}]})

    def test_a_stranger_on_the_port_is_not_a_sender(self):
        left, right = socket.socketpair()
        left.sendall(b'GET / HTTP/1.1\r\nHost: x\r\n\r\n')
        with self.assertRaises(drop.DropError):
            drop.read_header(right)
        left.close()
        right.close()

    def test_an_empty_offer_is_refused(self):
        with self.assertRaises(drop.DropError):
            self.roundtrip({'name': 'x', 'files': []})


class TransferTests(unittest.TestCase):
    """A real sender against a real receiver, over loopback."""

    @classmethod
    def setUpClass(cls):
        cls.work = tempfile.mkdtemp(prefix='mintdrop-test-')
        cls.inbox = os.path.join(cls.work, 'inbox')
        os.makedirs(cls.inbox)
        cls.conf = os.path.join(cls.work, 'mintdrop.conf')
        Path(cls.conf).write_text(f'dir = {cls.inbox}\n')

    def send_and_receive(self, payloads, extra=()):
        """Run `serve --once --yes` and `send`, return the receiver's log."""
        port = _free_port()
        env = dict(os.environ, HOME=self.work, MINTDROP_STAT='1')
        os.makedirs(os.path.join(self.work, '.config/mintbook'), exist_ok=True)
        Path(self.work, '.config/mintbook/mintdrop.conf').write_text(
            f'dir = {self.inbox}\n')

        server = subprocess.Popen(
            [sys.executable, str(ROOT / 'bin' / 'mintdrop'), 'serve', '--once',
             '--yes', '--port', str(port), *extra],
            stderr=subprocess.PIPE, text=True, env=env)
        while True:
            line = server.stderr.readline()
            if not line:
                self.fail('listener exited before it was ready')
            if 'listening' in line:
                break
        sent = subprocess.run(
            [sys.executable, str(ROOT / 'bin' / 'mintdrop'), 'send', '--quiet',
             f'127.0.0.1:{port}', *payloads],
            capture_output=True, text=True, env=env)
        log = server.stderr.read()
        server.stderr.close()
        server.wait(timeout=60)
        self.assertEqual(sent.returncode, 0, sent.stderr + log)
        return log

    def make_payload(self, name, size):
        path = os.path.join(self.work, name)
        with open(path, 'wb') as f:
            f.write(os.urandom(size))
        return path

    def test_a_file_arrives_byte_for_byte(self):
        source = self.make_payload('payload.bin', 3 << 20)
        self.send_and_receive([source])
        landed = os.path.join(self.inbox, 'payload.bin')
        self.assertTrue(os.path.exists(landed))
        self.assertEqual(_digest(source), _digest(landed))

    def test_the_buffered_path_agrees_with_splice(self):
        source = self.make_payload('buffered.bin', 3 << 20)
        self.send_and_receive([source], extra=('--no-splice',))
        landed = os.path.join(self.inbox, 'buffered.bin')
        self.assertEqual(_digest(source), _digest(landed))

    def test_several_files_keep_their_boundaries(self):
        # The stream has no per-file framing: the sizes in the header are the
        # only boundary, so a run of files is where an off-by-one would show.
        sources = [self.make_payload(f'many{i}.bin', 100_000 + i * 7919)
                   for i in range(4)]
        self.send_and_receive(sources)
        for source in sources:
            landed = os.path.join(self.inbox, os.path.basename(source))
            self.assertEqual(_digest(source), _digest(landed), landed)

    def test_an_empty_file_still_arrives(self):
        source = self.make_payload('empty.bin', 0)
        self.send_and_receive([source])
        self.assertTrue(os.path.exists(os.path.join(self.inbox, 'empty.bin')))

    def test_nothing_partial_is_left_named_like_a_finished_file(self):
        self.send_and_receive([self.make_payload('clean.bin', 1 << 20)])
        leftovers = [n for n in os.listdir(self.inbox) if n.endswith('.part')]
        self.assertEqual(leftovers, [])


def _free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def _digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


if __name__ == '__main__':
    unittest.main()


class TargetTests(unittest.TestCase):
    """`mintdrop send` takes whatever the user (or the picker) typed."""

    def setUp(self):
        loader = importlib.machinery.SourceFileLoader(
            'mintdrop_cli', str(ROOT / 'bin' / 'mintdrop'))
        self.cli = importlib.util.module_from_spec(
            importlib.util.spec_from_loader(loader.name, loader))
        loader.exec_module(self.cli)

    def test_an_ipv6_literal_keeps_its_colons(self):
        # Splitting on the first colon sent every IPv6 peer the picker offered
        # to a host called 'fe80'.
        self.assertEqual(self.cli.resolve_peer('::1')['address'], '::1')
        self.assertEqual(self.cli.resolve_peer('::1')['port'], drop.PORT)

    def test_a_bracketed_ipv6_port_is_honoured(self):
        peer = self.cli.resolve_peer('[::1]:9999')
        self.assertEqual((peer['address'], peer['port']), ('::1', 9999))

    def test_ipv4_with_and_without_a_port(self):
        self.assertEqual(self.cli.resolve_peer('127.0.0.1')['port'], drop.PORT)
        self.assertEqual(self.cli.resolve_peer('127.0.0.1:9999')['port'], 9999)

    def test_a_name_that_is_nowhere_resolves_to_nothing(self):
        self.assertIsNone(self.cli.resolve_peer('no-such-host.invalid'))
