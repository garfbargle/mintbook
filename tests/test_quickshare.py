"""Quick Share's byte layouts, pinned.

These are the fields that fail silently. A wrong bit in the endpoint info
raises nothing and logs nothing — the phone simply never lists the machine,
and there is no way to tell that apart from being out of range. So the
layouts are asserted here against the reverse-engineered specification in
grishka/NearDrop's PROTOCOL.md rather than trusted to a comment.
"""
import base64
import importlib.machinery
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load():
    loader = importlib.machinery.SourceFileLoader(
        'mintbook_quickshare', str(ROOT / 'bin' / 'mintbook_quickshare.py'))
    module = importlib.util.module_from_spec(
        importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(module)
    return module


qs = load()


def unb64(text):
    return base64.urlsafe_b64decode(text + '=' * (-len(text) % 4))


class InstanceNameTests(unittest.TestCase):
    def test_the_ten_bytes_are_exactly_the_specified_ones(self):
        blob = unb64(qs.instance_name('AB12'))
        self.assertEqual(len(blob), 10)
        self.assertEqual(blob[0], 0x23)                  # P2P_CLUSTER
        self.assertEqual(blob[1:5], b'AB12')             # endpoint id
        self.assertEqual(blob[5:8], b'\xfc\x9f\x5e')     # SHA256('NearbySharing')
        self.assertEqual(blob[8:10], b'\x00\x00')

    def test_the_name_carries_no_base64_padding(self):
        # The wire form is unpadded; '=' in a DNS label is a different label.
        self.assertNotIn('=', qs.instance_name('AB12'))

    def test_a_wrong_length_endpoint_is_refused_loudly(self):
        for bad in ('ABC', 'ABCDE', ''):
            with self.assertRaises(ValueError):
                qs.instance_name(bad)


class EndpointInfoTests(unittest.TestCase):
    def test_a_visible_laptop_is_0x06(self):
        # version 0 << 5 | visible 0 << 4 | LAPTOP 3 << 1
        info = qs.endpoint_info('x', qs.LAPTOP)
        self.assertEqual(info[0], 0x06)

    def test_the_device_type_sits_in_bits_1_to_3(self):
        for device_type in range(7):
            info = qs.endpoint_info('x', device_type)
            self.assertEqual((info[0] >> 1) & 0b111, device_type)

    def test_hidden_sets_the_visibility_bit_and_drops_the_name(self):
        info = qs.endpoint_info('Cobo', qs.LAPTOP, visible=False)
        self.assertEqual((info[0] >> 4) & 1, 1)
        self.assertEqual(len(info), 17)

    def test_the_name_follows_sixteen_bytes_of_identity(self):
        info = qs.endpoint_info('Cobo', qs.LAPTOP)
        self.assertEqual(len(info), 1 + 16 + 1 + 4)
        self.assertEqual(info[17], 4)
        self.assertEqual(info[18:].decode(), 'Cobo')

    def test_the_identity_bytes_differ_between_calls(self):
        # They stand in for an account this machine does not have; fixed bytes
        # would be a stable fingerprint for no benefit.
        self.assertNotEqual(qs.endpoint_info('x')[1:17],
                            qs.endpoint_info('x')[1:17])

    def test_a_multibyte_name_is_not_cut_mid_character(self):
        info = qs.endpoint_info('é' * 200)
        name = info[18:]
        self.assertEqual(len(name), info[17])
        name.decode()          # must not raise

    def test_an_out_of_range_device_type_is_refused(self):
        with self.assertRaises(ValueError):
            qs.endpoint_info('x', 9)


class AdvertTests(unittest.TestCase):
    def test_the_service_file_is_well_formed_and_complete(self):
        import xml.etree.ElementTree as ET
        xml = qs.avahi_service('Cobo', endpoint='AB12')
        root = ET.fromstring(xml)
        self.assertEqual(root.findtext('name'), qs.instance_name('AB12'))
        service = root.find('service')
        self.assertEqual(service.findtext('type'), '_FC9F5ED42C8A._tcp')
        self.assertEqual(service.findtext('port'), str(qs.PORT))
        txt = service.findtext('txt-record')
        self.assertTrue(txt.startswith('n='))
        self.assertEqual(unb64(txt[2:])[18:].decode(), 'Cobo')

    def test_it_advertises_the_port_mintdrop_already_listens_on(self):
        drop_loader = importlib.machinery.SourceFileLoader(
            'mintbook_drop', str(ROOT / 'bin' / 'mintbook_drop.py'))
        drop = importlib.util.module_from_spec(
            importlib.util.spec_from_loader(drop_loader.name, drop_loader))
        drop_loader.exec_module(drop)
        # One listener for both protocols, dispatched on the first four bytes.
        self.assertEqual(qs.PORT, drop.PORT)


if __name__ == '__main__':
    unittest.main()


def pb_load():
    loader = importlib.machinery.SourceFileLoader(
        'mintbook_protobuf', str(ROOT / 'bin' / 'mintbook_protobuf.py'))
    module = importlib.util.module_from_spec(
        importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(module)
    return module


pb = pb_load()


def v1_of(frame):
    """The V1Frame inside an OfflineFrame, as a decoded dict."""
    outer = pb.unpack(frame)
    assert pb.one(outer, 1) == 1, 'version must be V1'
    return pb.submessage(outer, 2)


class TransportFrameTests(unittest.TestCase):
    """Field numbers here are checked against vendor/nearby-protobufs."""

    def test_connection_request_carries_who_we_are(self):
        info = qs.endpoint_info('Mintbook1')
        v1 = v1_of(qs.connection_request('AB12', info, hostname='host'))
        self.assertEqual(pb.one(v1, 1), qs.CONNECTION_REQUEST)
        body = pb.submessage(v1, 2)
        self.assertEqual(pb.one(body, 1), b'AB12')          # endpoint_id
        # endpoint_name: omitting it made a real phone hang up without a word
        self.assertEqual(pb.one(body, 2), b'host')
        self.assertEqual(body[5], [qs.WIFI_LAN])            # mediums
        self.assertEqual(pb.one(body, 6), info)             # endpoint_info

    def test_connection_response_accepts(self):
        v1 = v1_of(qs.connection_response_accept())
        self.assertEqual(pb.one(v1, 1), qs.CONNECTION_RESPONSE)
        self.assertEqual(pb.one(pb.submessage(v1, 3), 3), qs.ACCEPT_RESPONSE)

    def test_keep_alive_can_be_an_ack(self):
        v1 = v1_of(qs.keep_alive(ack=True))
        self.assertEqual(pb.one(v1, 1), qs.KEEP_ALIVE)
        self.assertEqual(pb.one(pb.submessage(v1, 6), 1), 1)


class PayloadFramingTests(unittest.TestCase):
    """A payload is two frames. Getting this wrong cost a working transfer:
    the phone accepted the offer and saved nothing, because the terminator it
    was waiting for never came."""

    def test_a_bytes_payload_is_data_then_a_last_chunk(self):
        data, end = qs.bytes_payload(7, b'hello')
        first = pb.submessage(v1_of(data), 4)
        self.assertEqual(pb.one(pb.submessage(first, 2), 1), 7)      # id
        self.assertEqual(pb.one(pb.submessage(first, 2), 2),
                         qs.PAYLOAD_BYTES)
        chunk = pb.submessage(first, 3)
        self.assertEqual(pb.one(chunk, 1), 0)                        # no flag
        self.assertEqual(pb.one(chunk, 3), b'hello')

        last = pb.submessage(pb.submessage(v1_of(end), 4), 3)
        self.assertEqual(pb.one(last, 1), qs.LAST_CHUNK)
        self.assertEqual(pb.one(last, 2), 5)                         # offset
        self.assertIsNone(pb.one(last, 3))                           # no body

    def test_a_file_chunk_names_the_file_and_its_size(self):
        frame = qs.file_chunk(9, 1234, 'a.jpg', 0, b'xyz')
        transfer = pb.submessage(v1_of(frame), 4)
        header = pb.submessage(transfer, 2)
        self.assertEqual(pb.one(header, 1), 9)
        self.assertEqual(pb.one(header, 2), qs.PAYLOAD_FILE)
        self.assertEqual(pb.one(header, 3), 1234)
        self.assertEqual(pb.one(header, 5), b'a.jpg')
        self.assertEqual(pb.one(pb.submessage(transfer, 3), 3), b'xyz')

    def test_the_final_file_chunk_is_empty_and_flagged(self):
        frame = qs.file_chunk(9, 1234, 'a.jpg', 1234, b'', last=True)
        chunk = pb.submessage(pb.submessage(v1_of(frame), 4), 3)
        self.assertEqual(pb.one(chunk, 1), qs.LAST_CHUNK)
        self.assertEqual(pb.one(chunk, 2), 1234)
        self.assertIsNone(pb.one(chunk, 3))


class SharingFrameTests(unittest.TestCase):
    def test_the_introduction_describes_every_file(self):
        frame = qs.introduction([
            {'name': 'a.jpg', 'size': 10, 'payload_id': 1, 'mime': 'image/jpeg'},
            {'name': 'b.pdf', 'size': 20, 'payload_id': 2}])
        v1 = pb.submessage(pb.unpack(frame), 2)
        self.assertEqual(pb.one(v1, 1), qs.INTRODUCTION)
        files = pb.submessage(v1, 2)[1]
        self.assertEqual(len(files), 2)
        first = pb.unpack(files[0])
        self.assertEqual(pb.one(first, 1), b'a.jpg')
        self.assertEqual(pb.one(first, 3), 1)          # payload_id
        self.assertEqual(pb.one(first, 4), 10)         # size
        self.assertEqual(pb.one(first, 5), b'image/jpeg')
        self.assertEqual(pb.one(pb.unpack(files[1]), 5),
                         b'application/octet-stream')

    def test_paired_key_frames_say_we_are_a_stranger(self):
        v1 = pb.submessage(pb.unpack(qs.paired_key_encryption()), 2)
        self.assertEqual(pb.one(v1, 1), qs.PAIRED_KEY_ENCRYPTION)
        body = pb.submessage(v1, 4)
        self.assertEqual(len(pb.one(body, 1)), 72)     # signed_data
        self.assertEqual(len(pb.one(body, 2)), 6)      # secret_id_hash

        v1 = pb.submessage(pb.unpack(qs.paired_key_result()), 2)
        self.assertEqual(pb.one(v1, 1), qs.PAIRED_KEY_RESULT)
        self.assertEqual(pb.one(pb.submessage(v1, 5), 1), qs.PAIRED_KEY_UNABLE)


class BleTests(unittest.TestCase):
    def test_the_fast_init_payload_is_the_known_constant(self):
        ble = importlib.util.module_from_spec(
            importlib.util.spec_from_loader(
                'mintbook_ble',
                importlib.machinery.SourceFileLoader(
                    'mintbook_ble', str(ROOT / 'bin' / 'mintbook_ble.py'))))
        loader = importlib.machinery.SourceFileLoader(
            'mintbook_ble', str(ROOT / 'bin' / 'mintbook_ble.py'))
        ble = importlib.util.module_from_spec(
            importlib.util.spec_from_loader(loader.name, loader))
        loader.exec_module(ble)
        # Not derived from anything here: it is the advertisement Android
        # recognises. An earlier version broadcast eight bytes captured from
        # what turned out to be a Fast Pair device, and no phone ever woke.
        self.assertEqual(ble.payload().hex(),
                         'fc128e0142000000000000000000bf2d5ba0e1d87524ca00')
        self.assertEqual(len(ble.payload()), 24)


class EndpointAdvertisementTests(unittest.TestCase):
    """The BLE advertisement a phone lists, pinned to what one actually parsed.

    A Galaxy Z Fold7 decoded the bytes below and logged
    EndpointDiscovered(endpointId=MB01), so these are not a reading of the
    specification — they are a reading of the specification that a device
    agreed with.
    """

    def setUp(self):
        loader = importlib.machinery.SourceFileLoader(
            'mintbook_ble', str(ROOT / 'bin' / 'mintbook_ble.py'))
        self.ble = importlib.util.module_from_spec(
            importlib.util.spec_from_loader(loader.name, loader))
        loader.exec_module(self.ble)

    def test_the_bytes_a_phone_accepted(self):
        info = bytes([0x06, 0x09]) + b'Mintbook1'
        blob = self.ble.endpoint_advertisement('MB01', info,
                                               token=bytes([0x8a, 0x89]))
        self.assertEqual(blob.hex(), '4a11234d42303' + '10b06094d696e74626f6f6b318a89')

    def test_the_outer_header_encodes_version_socket_and_fast(self):
        blob = self.ble.endpoint_advertisement('AB12', b'\x06', version=2,
                                               socket_version=2)
        head = blob[0]
        self.assertEqual((head >> 5) & 0b111, 2)      # version
        self.assertEqual((head >> 2) & 0b111, 2)      # socket version
        self.assertEqual((head >> 1) & 1, 1)          # fast advertisement

    def test_the_inner_advertisement_opens_with_the_pcp_byte(self):
        # 0x23 — the same byte that opens the mDNS instance name.
        blob = self.ble.endpoint_advertisement('AB12', b'\x06')
        self.assertEqual(blob[2], 0x23)
        self.assertEqual(blob[3:7], b'AB12')

    def test_a_wrong_length_endpoint_is_refused(self):
        for bad in ('ABC', 'ABCDE'):
            with self.assertRaises(ValueError):
                self.ble.endpoint_advertisement(bad, b'\x06')

    def test_the_header_is_seventeen_bytes(self):
        header = self.ble.advertisement_header(b'\x00' * 10, b'\x01\x02\x03\x04')
        self.assertEqual(len(header), 17)
        self.assertEqual((header[0] >> 5) & 0b111, 1)     # version
        self.assertEqual(header[0] & 0x0F, 1)             # one slot

    def test_the_header_refuses_wrong_field_widths(self):
        with self.assertRaises(ValueError):
            self.ble.advertisement_header(b'\x00' * 9, b'\x01\x02\x03\x04')
        with self.assertRaises(ValueError):
            self.ble.advertisement_header(b'\x00' * 10, b'\x01\x02\x03')

    def test_a_full_endpoint_info_cannot_fit_a_legacy_packet(self):
        # The arithmetic that forces the GATT path on this machine: 24 bytes
        # of service data, 10 spent on headers, and a valid endpoint info is
        # 18 before the device has a name.
        full_info = bytes([0x06]) + b'\x00' * 16 + bytes([1]) + b'M'
        blob = self.ble.endpoint_advertisement('MB01', full_info)
        self.assertGreater(len(blob), 24)
