"""Nearby's BLE L2CAP control packets, against bytes a real phone sent."""
import importlib.machinery
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
loader = importlib.machinery.SourceFileLoader(
    'mintbook_l2cap_packet', str(ROOT / 'bin' / 'mintbook_l2cap_packet.py'))
packet = importlib.util.module_from_spec(
    importlib.util.spec_from_loader(loader.name, loader))
loader.exec_module(packet)

# The first packet this machine ever received over the BLE channel, from a
# Galaxy Z Fold7 on 2026-09-14. Everything here is checked against this
# rather than against the encoder's own output.
FROM_PHONE = bytes.fromhex('00000006010003' '16d9ae')


class RealPacketTests(unittest.TestCase):
    def test_reads_the_phones_request(self):
        got = list(packet.Reader().feed(FROM_PHONE).packets())
        self.assertEqual(got, [(packet.REQUEST_ADVERTISEMENT,
                                bytes.fromhex('16d9ae'))])

    def test_the_phone_asked_for_a_service_we_do_not_advertise(self):
        self.assertNotEqual(bytes.fromhex('16d9ae'),
                            packet.service_id_hash('NearbySharing'))

    def test_our_service_id_hash_matches_the_advertised_one(self):
        # The same 3 bytes the mDNS name _FC9F5ED42C8A._tcp is built from.
        self.assertEqual(packet.service_id_hash('NearbySharing').hex(),
                         'fc9f5e')

    def test_round_trips_the_phones_framing(self):
        self.assertEqual(
            packet.frame(packet.REQUEST_ADVERTISEMENT,
                         bytes.fromhex('16d9ae')), FROM_PHONE)


class FramingTests(unittest.TestCase):
    def test_bare_commands_carry_no_length(self):
        self.assertEqual(packet.frame(packet.RESPONSE_SERVICE_ID_NOT_FOUND),
                         bytes.fromhex('0000000116'))
        self.assertEqual(packet.frame(packet.RESPONSE_DATA_CONNECTION_READY),
                         bytes.fromhex('0000000117'))

    def test_advertisement_response_carries_a_two_byte_length(self):
        body = bytes(range(40))
        raw = packet.frame(packet.RESPONSE_ADVERTISEMENT, body)
        self.assertEqual(raw[:4], (len(body) + 3).to_bytes(4, 'big'))
        self.assertEqual(raw[4], packet.RESPONSE_ADVERTISEMENT)
        self.assertEqual(raw[5:7], len(body).to_bytes(2, 'big'))
        self.assertEqual(raw[7:], body)

    def test_two_packets_in_one_read(self):
        raw = (packet.frame(packet.REQUEST_ADVERTISEMENT, b'abc')
               + packet.frame(packet.REQUEST_ADVERTISEMENT_FINISH))
        got = list(packet.Reader().feed(raw).packets())
        self.assertEqual([c for c, _ in got],
                         [packet.REQUEST_ADVERTISEMENT,
                          packet.REQUEST_ADVERTISEMENT_FINISH])

    def test_a_packet_split_across_reads(self):
        raw = packet.frame(packet.REQUEST_ADVERTISEMENT, b'abc')
        reader = packet.Reader()
        self.assertEqual(list(reader.feed(raw[:5]).packets()), [])
        self.assertEqual(list(reader.feed(raw[5:]).packets()),
                         [(packet.REQUEST_ADVERTISEMENT, b'abc')])


class RefusalTests(unittest.TestCase):
    """What it refuses matters as much: a wrong guess is worse than a stop."""

    def test_unknown_command(self):
        with self.assertRaises(packet.ProtocolError):
            packet.parse(bytes([99]))

    def test_truncated_data(self):
        with self.assertRaises(packet.ProtocolError):
            packet.parse(bytes([packet.REQUEST_ADVERTISEMENT, 0, 9]) + b'ab')

    def test_short_service_id_hash(self):
        with self.assertRaises(packet.ProtocolError):
            packet.parse(bytes([packet.REQUEST_ADVERTISEMENT, 0, 2]) + b'ab')

    def test_zero_length(self):
        with self.assertRaises(packet.ProtocolError):
            packet.parse(bytes([packet.REQUEST_ADVERTISEMENT, 0, 0]))

    def test_absurd_frame_length(self):
        reader = packet.Reader().feed(b'\xff\xff\xff\xff' + b'x')
        with self.assertRaises(packet.ProtocolError):
            list(reader.packets())

    def test_data_on_a_bare_command(self):
        with self.assertRaises(packet.ProtocolError):
            packet.payload(packet.RESPONSE_DATA_CONNECTION_READY, b'x')

    def test_missing_data_on_a_data_command(self):
        with self.assertRaises(packet.ProtocolError):
            packet.payload(packet.REQUEST_ADVERTISEMENT)


if __name__ == '__main__':
    unittest.main()


class FakeSocket:
    """Replays packets a phone sent, and records what was written back."""

    def __init__(self, packets):
        self.packets = list(packets)
        self.written = []

    def recv(self, count):
        return self.packets.pop(0) if self.packets else b''

    def send(self, data):
        self.written.append(data)
        return len(data)

    def close(self):
        pass


OURS = bytes.fromhex('fc9f5e')

# The control packets a Z Fold7 sent, whole and unedited.
CONNECT = bytes.fromhex(
    '00000026' '000000' '080112' '1f' '0a03fc9f5e' '1002' '1a16'
    + b'jbxB9cQdjwR9_gvQlnqdCQ'.hex())
DISCONNECT = bytes.fromhex('0000000c' '000000' '08021a050a03fc9f5e')


class EnvelopeTests(unittest.TestCase):
    """The lengths are the phone's; only the payloads are invented."""

    def test_the_phones_control_packets_are_self_consistent(self):
        for raw in (CONNECT, DISCONNECT):
            outer = int.from_bytes(raw[:4], 'big')
            self.assertEqual(len(raw), 4 + outer)
            self.assertEqual(raw[4:7], packet.CONTROL_HASH)

    def test_stream_payload_has_the_envelope_removed(self):
        inner = b'\x00\x00\x00\x04abcd'
        raw = (len(OURS) + len(inner)).to_bytes(4, 'big') + OURS + inner
        channel = packet.Channel(FakeSocket([raw]), OURS)
        self.assertEqual(channel.recv(64), inner)

    def test_a_connect_is_recorded_not_streamed(self):
        channel = packet.Channel(FakeSocket([CONNECT]), OURS)
        self.assertEqual(channel.recv(64), b'')
        self.assertEqual(len(channel.control), 1)

    def test_a_disconnect_closes_the_stream(self):
        channel = packet.Channel(FakeSocket([DISCONNECT]), OURS)
        self.assertEqual(channel.recv(64), b'')
        self.assertTrue(channel.closed)

    def test_a_packet_for_another_service_is_ignored(self):
        other = bytes.fromhex('16d9ae')
        raw = (3 + 2).to_bytes(4, 'big') + other + b'hi'
        channel = packet.Channel(FakeSocket([raw]), OURS)
        self.assertEqual(channel.recv(64), b'')

    def test_control_then_stream_in_one_read(self):
        inner = b'\x00\x00\x00\x02hi'
        raw = CONNECT + ((3 + len(inner)).to_bytes(4, 'big') + OURS + inner)
        channel = packet.Channel(FakeSocket([raw]), OURS)
        self.assertEqual(channel.recv(64), inner)

    def test_sendall_puts_the_envelope_back(self):
        socket_ = FakeSocket([])
        packet.Channel(socket_, OURS).sendall(b'\x00\x00\x00\x02hi')
        self.assertEqual(b''.join(socket_.written),
                         bytes.fromhex('00000009') + OURS
                         + b'\x00\x00\x00\x02hi')

    def test_a_long_message_is_split_but_stays_one_message(self):
        body = bytes(2000)
        socket_ = FakeSocket([])
        channel = packet.Channel(socket_, OURS, mtu=512)
        channel.sendall(body)
        self.assertTrue(len(socket_.written) > 1)
        self.assertTrue(all(len(p) <= 512 for p in socket_.written))
        rejoined = b''.join(socket_.written)
        self.assertEqual(int.from_bytes(rejoined[:4], 'big'),
                         len(OURS) + len(body))

    def test_recv_returns_what_is_asked_for_and_keeps_the_rest(self):
        inner = b'0123456789'
        raw = (3 + len(inner)).to_bytes(4, 'big') + OURS + inner
        channel = packet.Channel(FakeSocket([raw]), OURS)
        self.assertEqual(channel.recv(4), b'0123')
        self.assertEqual(channel.recv(64), b'456789')

    def test_a_closed_socket_ends_the_stream(self):
        channel = packet.Channel(FakeSocket([]), OURS)
        self.assertEqual(channel.recv(16), b'')
        self.assertTrue(channel.closed)
