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
