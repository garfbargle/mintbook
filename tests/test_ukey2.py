"""UKEY2 and the encrypted channel, checked against a peer we also implement.

There is no phone in these tests. The point is that both ends of the key
agreement, run independently, arrive at the same four keys and can talk — if
the derivation were wrong in the same way on both sides that would pass, so
the salts are additionally pinned to the digests they are supposed to be, and
the transcript binding is checked by breaking it.
"""
import hashlib
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import unittest

from cryptography.hazmat.primitives.asymmetric import ec

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    loader = importlib.machinery.SourceFileLoader(
        name, str(ROOT / 'bin' / (name + '.py')))
    module = importlib.util.module_from_spec(
        importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(module)
    return module


ukey2 = load('mintbook_ukey2')
pb = load('mintbook_protobuf')


def be_the_server(client_init_blob):
    """The other half of the handshake, as the phone would run it."""
    outer = pb.unpack(client_init_blob)
    assert pb.one(outer, 1) == ukey2.CLIENT_INIT
    private = ec.generate_private_key(ec.SECP256R1())
    server_init = pb.pack(
        (1, ukey2.UKEY2_VERSION),
        (2, os.urandom(32)),
        (3, ukey2.P256_SHA512),
        (4, ukey2.public_key_bytes(private.public_key())))
    return private, ukey2.message(ukey2.SERVER_INIT, server_init)


class SaltTests(unittest.TestCase):
    def test_the_two_fixed_salts_are_the_digests_they_claim_to_be(self):
        self.assertEqual(ukey2.D2D_SALT, hashlib.sha256(b'D2D').digest())
        self.assertEqual(ukey2.SECURE_MESSAGE_SALT,
                         hashlib.sha256(b'SecureMessage').digest())


class KeyEncodingTests(unittest.TestCase):
    def test_a_public_key_survives_the_round_trip(self):
        private = ec.generate_private_key(ec.SECP256R1())
        back = ukey2.public_key_from(
            ukey2.public_key_bytes(private.public_key()))
        self.assertEqual(back.public_numbers(),
                         private.public_key().public_numbers())

    def test_coordinates_are_a_fixed_32_bytes_with_no_sign_byte(self):
        # A coordinate with its top bit set must not grow a leading zero:
        # the far end hashes the bytes it was sent.
        for _ in range(40):
            private = ec.generate_private_key(ec.SECP256R1())
            ec_key = pb.submessage(
                pb.unpack(ukey2.public_key_bytes(private.public_key())), 2)
            self.assertEqual(len(pb.one(ec_key, 1)), 32)
            self.assertEqual(len(pb.one(ec_key, 2)), 32)

    def test_a_non_p256_key_is_refused(self):
        with self.assertRaises(ukey2.HandshakeError):
            ukey2.public_key_from(pb.pack((1, 2), (2, b'')))


class HandshakeTests(unittest.TestCase):
    def agree(self):
        client = ukey2.ClientHandshake()
        server_private, server_init = be_the_server(client.client_init())
        client.accept_server_init(server_init)
        theirs = ukey2.D2DContext(
            ukey2.hkdf(ukey2.NEXT_SALT,
                       hashlib.sha256(server_private.exchange(
                           ec.ECDH(), _client_key(client))).digest(),
                       client.client_init() + server_init),
            is_client=False)
        return client.context(), theirs

    def test_both_ends_derive_the_same_four_keys(self):
        ours, theirs = self.agree()
        self.assertEqual(ours.encrypt_key, theirs.decrypt_key)
        self.assertEqual(ours.decrypt_key, theirs.encrypt_key)
        self.assertEqual(ours.send_hmac, theirs.receive_hmac)
        self.assertEqual(ours.receive_hmac, theirs.send_hmac)

    def test_the_four_keys_are_all_different(self):
        ours, _ = self.agree()
        keys = {ours.encrypt_key, ours.decrypt_key,
                ours.send_hmac, ours.receive_hmac}
        self.assertEqual(len(keys), 4)

    def test_a_frame_survives_the_channel(self):
        ours, theirs = self.agree()
        for frame in (b'', b'x', os.urandom(15), os.urandom(16),
                      os.urandom(17), os.urandom(200000)):
            self.assertEqual(theirs.decrypt(ours.encrypt(frame)), frame)

    def test_sequence_numbers_count_up_from_one(self):
        ours, theirs = self.agree()
        for expected in (1, 2, 3):
            theirs.decrypt(ours.encrypt(b'hello'))
            self.assertEqual(theirs.received, expected)

    def test_a_tampered_message_does_not_verify(self):
        ours, theirs = self.agree()
        blob = bytearray(ours.encrypt(b'hello'))
        blob[len(blob) // 2] ^= 0x01
        with self.assertRaises(ukey2.HandshakeError):
            theirs.decrypt(bytes(blob))

    def test_a_message_from_a_different_channel_does_not_verify(self):
        ours, _ = self.agree()
        _, someone_else = self.agree()
        with self.assertRaises(ukey2.HandshakeError):
            someone_else.decrypt(ours.encrypt(b'hello'))

    def test_the_commitment_covers_the_finish_message(self):
        # CLIENT_INIT commits to the hash of CLIENT_FINISH, so rebuilding
        # CLIENT_FINISH later would not match. It must be the same bytes.
        client = ukey2.ClientHandshake()
        commitment = pb.one(pb.unpack(pb.one(pb.unpack(client.client_init()), 2)), 3)
        inner = pb.unpack(commitment)
        self.assertEqual(pb.one(inner, 1), ukey2.P256_SHA512)
        self.assertEqual(pb.one(inner, 2),
                         hashlib.sha512(client.client_finish()).digest())

    def test_a_server_init_of_the_wrong_type_is_refused(self):
        client = ukey2.ClientHandshake()
        with self.assertRaises(ukey2.HandshakeError):
            client.accept_server_init(ukey2.message(ukey2.CLIENT_INIT, b''))

    def test_a_server_choosing_another_cipher_is_refused(self):
        client = ukey2.ClientHandshake()
        bad = ukey2.message(ukey2.SERVER_INIT,
                            pb.pack((1, 1), (2, os.urandom(32)), (3, 200),
                                    (4, b'')))
        with self.assertRaises(ukey2.HandshakeError):
            client.accept_server_init(bad)

    def test_the_pin_is_four_digits(self):
        ours, _ = self.agree()
        self.assertRegex(ours.pin(), r'^\d{4}$')


class PaddingTests(unittest.TestCase):
    def test_a_full_block_is_added_when_it_already_fits(self):
        self.assertEqual(len(ukey2.pad(b'x' * 16)), 32)

    def test_round_trip(self):
        for n in range(0, 40):
            self.assertEqual(ukey2.unpad(ukey2.pad(b'y' * n)), b'y' * n)

    def test_bad_padding_raises(self):
        for bad in (b'', b'short', b'x' * 16 + b'\x11' * 16, b'x' * 15 + b'\x00'):
            with self.assertRaises(ukey2.HandshakeError):
                ukey2.unpad(bad)


def _client_key(client):
    """The client's public key, read back out of its own CLIENT_FINISH."""
    body = pb.one(pb.unpack(client.client_finish()), 2)
    return ukey2.public_key_from(pb.one(pb.unpack(body), 1))


if __name__ == '__main__':
    unittest.main()


class ClientMeetsServerTests(unittest.TestCase):
    """Our client and our server, talking to each other.

    This is the test the sending work never had: until now the "server" in
    these tests was fifteen lines written to agree with the client, which is
    exactly how SHA256(shared secret) went unnoticed. Both sides are real
    implementations here.
    """

    def handshake(self):
        client = ukey2.ClientHandshake()
        server = ukey2.ServerHandshake()
        server.accept_client_init(client.client_init())
        client.accept_server_init(server.server_init_message())
        server.accept_client_finish(client.client_finish())
        return client.context(), server.context()

    def test_the_two_ends_agree_on_every_key(self):
        ours, theirs = self.handshake()
        self.assertEqual(ours.encrypt_key, theirs.decrypt_key)
        self.assertEqual(ours.decrypt_key, theirs.encrypt_key)
        self.assertEqual(ours.send_hmac, theirs.receive_hmac)
        self.assertEqual(ours.receive_hmac, theirs.send_hmac)

    def test_frames_cross_in_both_directions(self):
        ours, theirs = self.handshake()
        self.assertEqual(theirs.decrypt(ours.encrypt(b'to the phone')),
                         b'to the phone')
        self.assertEqual(ours.decrypt(theirs.encrypt(b'from the phone')),
                         b'from the phone')

    def test_both_ends_compute_the_same_pin(self):
        ours, theirs = self.handshake()
        self.assertEqual(ours.pin(), theirs.pin())

    def test_a_client_finish_that_breaks_its_commitment_is_refused(self):
        client = ukey2.ClientHandshake()
        server = ukey2.ServerHandshake()
        server.accept_client_init(client.client_init())
        client.accept_server_init(server.server_init_message())
        # A second client: a valid CLIENT_FINISH, but not the one committed to.
        other = ukey2.ClientHandshake()
        with self.assertRaises(ukey2.HandshakeError):
            server.accept_client_finish(other.client_finish())

    def test_a_client_init_without_a_p256_commitment_is_refused(self):
        server = ukey2.ServerHandshake()
        bad = ukey2.message(ukey2.CLIENT_INIT, pb.pack(
            (1, 1), (2, os.urandom(32)),
            (3, pb.pack((1, 200), (2, b'x' * 64)))))     # CURVE25519 only
        with self.assertRaises(ukey2.HandshakeError):
            server.accept_client_init(bad)

    def test_the_wrong_message_type_is_refused(self):
        server = ukey2.ServerHandshake()
        with self.assertRaises(ukey2.HandshakeError):
            server.accept_client_init(ukey2.message(ukey2.SERVER_INIT, b''))
