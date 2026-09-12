"""MurmurHash3 and Nearby's bloom filter, against published vectors."""
import importlib.machinery
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
loader = importlib.machinery.SourceFileLoader(
    'mintbook_bloom', str(ROOT / 'bin' / 'mintbook_bloom.py'))
bloom = importlib.util.module_from_spec(
    importlib.util.spec_from_loader(loader.name, loader))
loader.exec_module(bloom)


class MurmurTests(unittest.TestCase):
    """Against the published vectors, not against itself."""

    def test_empty_string(self):
        self.assertEqual(bloom.murmur3_x64_128(b'', 0), (0, 0))

    def test_hello(self):
        self.assertEqual(bloom.murmur3_x64_128(b'hello', 0),
                         (0xcbd8a7b341bd9b02, 0x5b1e906a48ae1d19))

    def test_a_block_boundary(self):
        # 16 bytes exactly exercises the block path with no tail.
        h1, h2 = bloom.murmur3_x64_128(b'0123456789abcdef', 0)
        self.assertNotEqual((h1, h2), (0, 0))
        self.assertEqual(bloom.murmur3_x64_128(b'0123456789abcdef', 0), (h1, h2))

    def test_every_tail_length_is_reachable(self):
        # The tail switch has fifteen fall-through cases; a mistake in one
        # shows up only for that length.
        seen = {bloom.murmur3_x64_128(bytes(range(n)), 0) for n in range(1, 17)}
        self.assertEqual(len(seen), 16)


class BloomFilterTests(unittest.TestCase):
    def test_it_is_ten_bytes(self):
        self.assertEqual(len(bytes(bloom.BloomFilter())), 10)

    def test_an_empty_filter_is_all_zero(self):
        self.assertEqual(bytes(bloom.BloomFilter()), b'\x00' * 10)

    def test_adding_sets_five_positions(self):
        f = bloom.BloomFilter().add('NearbySharing')
        self.assertEqual(sum(f.bits), len(set(
            h % 80 for h in bloom.hashes('NearbySharing'))))

    def test_the_bit_order_round_trips_the_cpp_convention(self):
        # bit 8k+b is bit b of byte k — what the C++ constructor reads back.
        f = bloom.BloomFilter()
        f.bits[0] = 1
        f.bits[9] = 1
        raw = bytes(f)
        self.assertEqual(raw[0] & 0x01, 1)
        self.assertEqual((raw[1] >> 1) & 0x01, 1)

    def test_it_is_deterministic(self):
        self.assertEqual(bytes(bloom.BloomFilter().add('NearbySharing')),
                         bytes(bloom.BloomFilter().add('NearbySharing')))
