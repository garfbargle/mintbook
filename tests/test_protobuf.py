"""The protobuf codec, including what it does with rubbish.

Everything this decodes arrives from a phone over a network, so the failure
cases matter as much as the round trips: a truncated or hostile message must
raise ProtobufError and not crash, hang, or allocate on a declared length it
never received.
"""
import importlib.machinery
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load():
    loader = importlib.machinery.SourceFileLoader(
        'mintbook_protobuf', str(ROOT / 'bin' / 'mintbook_protobuf.py'))
    module = importlib.util.module_from_spec(
        importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(module)
    return module


pb = load()


class WireFormatTests(unittest.TestCase):
    """Checked against the encoding protobuf actually specifies, by hand."""

    def test_a_varint_field_is_a_tag_then_a_varint(self):
        self.assertEqual(pb.pack((1, 5)), bytes.fromhex('0805'))

    def test_a_bytes_field_is_a_tag_a_length_then_the_bytes(self):
        self.assertEqual(pb.pack((2, b'hi')), bytes.fromhex('12026869'))

    def test_a_string_goes_out_as_utf8(self):
        self.assertEqual(pb.pack((3, 'né')), bytes.fromhex('1a03') + 'né'.encode())

    def test_fixed32_is_four_little_endian_bytes(self):
        self.assertEqual(pb.pack((4, pb.Fixed32(7))),
                         bytes.fromhex('2507000000'))

    def test_fixed64_is_eight_little_endian_bytes(self):
        self.assertEqual(pb.pack((4, pb.Fixed64(7))),
                         bytes.fromhex('210700000000000000'))

    def test_multibyte_varints_are_little_endian_base_128(self):
        self.assertEqual(pb.pack((1, 300)), bytes.fromhex('08ac02'))

    def test_a_field_number_above_15_uses_a_two_byte_tag(self):
        self.assertEqual(pb.pack((16, 1)), bytes.fromhex('800101'))


class RoundTripTests(unittest.TestCase):
    def test_every_supported_type_survives(self):
        blob = pb.pack((1, 5), (2, b'hi'), (3, 'name'), (4, pb.Fixed32(7)),
                       (5, pb.Fixed64(1 << 40)), (6, True))
        fields = pb.unpack(blob)
        self.assertEqual(pb.one(fields, 1), 5)
        self.assertEqual(pb.one(fields, 2), b'hi')
        self.assertEqual(pb.one(fields, 3), b'name')
        self.assertEqual(pb.one(fields, 4), 7)
        self.assertEqual(pb.one(fields, 5), 1 << 40)
        self.assertEqual(pb.one(fields, 6), 1)

    def test_a_list_becomes_a_repeated_field(self):
        self.assertEqual(pb.unpack(pb.pack((5, [1, 2, 3]))), {5: [1, 2, 3]})

    def test_none_is_skipped_so_optionals_need_no_branch(self):
        self.assertEqual(pb.pack((1, None)), b'')

    def test_nested_messages_decode_to_dicts(self):
        blob = pb.pack((1, pb.pack((2, 42), (3, b'x'))))
        inner = pb.submessage(pb.unpack(blob), 1)
        self.assertEqual(pb.one(inner, 2), 42)
        self.assertEqual(pb.one(inner, 3), b'x')

    def test_an_absent_submessage_stays_absent(self):
        self.assertIsNone(pb.submessage(pb.unpack(b''), 9))

    def test_one_returns_the_last_value_as_protobuf_specifies(self):
        self.assertEqual(pb.one(pb.unpack(pb.pack((1, 1), (1, 2))), 1), 2)

    def test_unknown_fields_are_kept_rather_than_dropped(self):
        # A newer phone may send fields this does not know; they must not
        # break the parse of the ones it does.
        fields = pb.unpack(pb.pack((1, 5), (99, b'from the future')))
        self.assertEqual(pb.one(fields, 1), 5)
        self.assertEqual(pb.one(fields, 99), b'from the future')

    def test_an_empty_message_is_empty_not_an_error(self):
        self.assertEqual(pb.unpack(b''), {})


class HostileInputTests(unittest.TestCase):
    def test_a_truncated_varint_raises(self):
        with self.assertRaises(pb.ProtobufError):
            pb.unpack(bytes.fromhex('08ff'))

    def test_a_length_longer_than_the_message_raises(self):
        # The allocation this would otherwise invite is the point.
        with self.assertRaises(pb.ProtobufError):
            pb.unpack(bytes.fromhex('12ff01') + b'short')

    def test_a_truncated_fixed_field_raises(self):
        with self.assertRaises(pb.ProtobufError):
            pb.unpack(bytes.fromhex('250700'))
        with self.assertRaises(pb.ProtobufError):
            pb.unpack(bytes.fromhex('2107'))

    def test_groups_are_refused_rather_than_guessed_at(self):
        with self.assertRaises(pb.ProtobufError):
            pb.unpack(bytes.fromhex('0b'))

    def test_field_number_zero_raises(self):
        with self.assertRaises(pb.ProtobufError):
            pb.unpack(bytes.fromhex('0001'))

    def test_an_overlong_varint_raises_instead_of_looping(self):
        with self.assertRaises(pb.ProtobufError):
            pb.unpack(b'\x08' + b'\xff' * 12)

    def test_a_submessage_that_is_not_a_message_raises(self):
        with self.assertRaises(pb.ProtobufError):
            pb.submessage(pb.unpack(pb.pack((1, 5))), 1)

    def test_every_truncation_of_a_real_message_raises_or_parses(self):
        # Nothing in here may raise something that is not a ProtobufError:
        # the receive loop catches that one and closes the connection.
        blob = pb.pack((1, 5), (2, b'hello'), (3, pb.Fixed32(9)),
                       (4, pb.pack((1, 300))))
        for cut in range(len(blob)):
            try:
                pb.unpack(blob[:cut])
            except pb.ProtobufError:
                pass


if __name__ == '__main__':
    unittest.main()
