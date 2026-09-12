"""Nearby's service-id bloom filter, and the MurmurHash3 it is built on.

A BLE advertisement header carries ten bytes saying which services the
device behind it advertises, so a scanner can skip a GATT read for services
it does not care about. Getting it wrong means a phone never bothers to ask.

From connections/implementation/mediums/ble/bloom_filter.cc: MurmurHash3
x64/128 with seed 0, the low 64 bits split into two signed 32-bit halves,
five positions at `hash1 + i * hash2` with negatives bitwise-inverted, each
taken modulo the bit count.

The MurmurHash3 here is checked against the published vector for "hello"
(0xcbd8a7b341bd9b02, 0x5b1e906a48ae1d19) rather than against itself, because
a hash that is merely self-consistent would pass every test and match no
other implementation on earth — the same trap that hid SHA256(shared secret)
in bin/mintbook_ukey2.py for a whole session.
"""
M = 0xFFFFFFFFFFFFFFFF

def _rotl(x, r):
    return ((x << r) | (x >> (64 - r))) & M

def _fmix(k):
    k ^= k >> 33
    k = (k * 0xff51afd7ed558ccd) & M
    k ^= k >> 33
    k = (k * 0xc4ceb9fe1a85ec53) & M
    k ^= k >> 33
    return k

def murmur3_x64_128(data, seed=0):
    c1, c2 = 0x87c37b91114253d5, 0x4cf5ad432745937f
    length = len(data)
    nblocks = length // 16
    h1 = h2 = seed
    for i in range(nblocks):
        k1 = int.from_bytes(data[i*16:i*16+8], 'little')
        k2 = int.from_bytes(data[i*16+8:i*16+16], 'little')
        k1 = (k1 * c1) & M; k1 = _rotl(k1, 31); k1 = (k1 * c2) & M
        h1 ^= k1; h1 = _rotl(h1, 27); h1 = (h1 + h2) & M
        h1 = (h1 * 5 + 0x52dce729) & M
        k2 = (k2 * c2) & M; k2 = _rotl(k2, 33); k2 = (k2 * c1) & M
        h2 ^= k2; h2 = _rotl(h2, 31); h2 = (h2 + h1) & M
        h2 = (h2 * 5 + 0x38495ab5) & M
    tail = data[nblocks*16:]
    k1 = k2 = 0
    n = len(tail)
    if n >= 15: k2 ^= tail[14] << 48
    if n >= 14: k2 ^= tail[13] << 40
    if n >= 13: k2 ^= tail[12] << 32
    if n >= 12: k2 ^= tail[11] << 24
    if n >= 11: k2 ^= tail[10] << 16
    if n >= 10: k2 ^= tail[9] << 8
    if n >= 9:
        k2 ^= tail[8]
        k2 = (k2 * c2) & M; k2 = _rotl(k2, 33); k2 = (k2 * c1) & M; h2 ^= k2
    if n >= 8: k1 ^= tail[7] << 56
    if n >= 7: k1 ^= tail[6] << 48
    if n >= 6: k1 ^= tail[5] << 40
    if n >= 5: k1 ^= tail[4] << 32
    if n >= 4: k1 ^= tail[3] << 24
    if n >= 3: k1 ^= tail[2] << 16
    if n >= 2: k1 ^= tail[1] << 8
    if n >= 1:
        k1 ^= tail[0]
        k1 = (k1 * c1) & M; k1 = _rotl(k1, 31); k1 = (k1 * c2) & M; h1 ^= k1
    h1 ^= length; h2 ^= length
    h1 = (h1 + h2) & M; h2 = (h2 + h1) & M
    h1 = _fmix(h1); h2 = _fmix(h2)
    h1 = (h1 + h2) & M; h2 = (h2 + h1) & M
    return h1, h2

def _s32(v):
    v &= 0xFFFFFFFF
    return v - (1 << 32) if v & 0x80000000 else v

def hashes(text):
    """Five positions, exactly as BloomFilter::GetHashes computes them."""
    data = text.encode() if isinstance(text, str) else text
    low, _high = murmur3_x64_128(data, 0)
    h1 = _s32(low & 0xFFFFFFFF)
    h2 = _s32((low >> 32) & 0xFFFFFFFF)
    out = []
    for i in range(1, 6):
        combined = _s32(h1 + i * h2)
        if combined < 0:
            combined = ~combined
        out.append(combined)
    return out

class BloomFilter:
    """10 bytes, 80 bits. Bit b of byte k is bit 8k+b — the same convention
    the C++ constructor reads back, so a filter written here round-trips."""

    def __init__(self, size_bytes=10):
        self.size = size_bytes * 8
        self.bits = [0] * self.size

    def add(self, text):
        for h in hashes(text):
            self.bits[h % self.size] = 1
        return self

    def __bytes__(self):
        out = bytearray(self.size // 8)
        for position, bit in enumerate(self.bits):
            if bit:
                out[position // 8] |= 1 << (position % 8)
        return bytes(out)
