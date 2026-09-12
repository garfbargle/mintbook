"""UKEY2 and the encrypted channel Quick Share runs everything through.

After the first three messages on the wire, nothing else is plaintext. This
module is that boundary: it does the key agreement, then hands back an object
that turns a frame into a SecureMessage and back.

The shape, in order:

    ->  Ukey2Message CLIENT_INIT    version, random, a commitment
    <-  Ukey2Message SERVER_INIT    their P-256 public key
    ->  Ukey2Message CLIENT_FINISH  our P-256 public key
        ECDH, then HKDF twice, and the channel is up

The commitment in CLIENT_INIT is a SHA-512 of the CLIENT_FINISH message we
have not sent yet. It exists so the other end cannot choose its key after
seeing ours — which means CLIENT_FINISH has to be built *first* and held,
and a handshake that rebuilds it later will hash differently and be rejected.

Field numbers come from vendor/nearby-protobufs/, which is why they are
vendored: every `(N, ...)` below can be checked against a .proto in this
repository instead of being taken on trust.

The two fixed salts are SHA-256("D2D") and SHA-256("SecureMessage"); they are
written out as digests here the way the specification and every
implementation writes them, and asserted against the hashes in the tests so
a typo cannot survive.
"""
import hashlib
import hmac
import os

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

import importlib.machinery
import importlib.util


def _protobuf():
    here = os.path.dirname(os.path.realpath(__file__))
    loader = importlib.machinery.SourceFileLoader(
        'mintbook_protobuf', os.path.join(here, 'mintbook_protobuf.py'))
    module = importlib.util.module_from_spec(
        importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(module)
    return module


pb = _protobuf()

# ukey.proto
CLIENT_INIT, SERVER_INIT, CLIENT_FINISH = 2, 3, 4
P256_SHA512 = 100
NEXT_PROTOCOL = 'AES_256_CBC-HMAC_SHA256'
UKEY2_VERSION = 1

# securemessage.proto
HMAC_SHA256, AES_256_CBC = 1, 2
EC_P256 = 1
# securegcm.proto: GcmMetadata.Type.DEVICE_TO_DEVICE_MESSAGE
DEVICE_TO_DEVICE_MESSAGE = 13

D2D_SALT = bytes.fromhex(
    '82aa55a0d397f88346ca1cee8d3909b95f13fa7deb1d4ab38376b8256da85510')
SECURE_MESSAGE_SALT = bytes.fromhex(
    'bf9d2a53c63616d75db0a7165b91c1ef73e537f2427405fa23610a4be657642e')
AUTH_SALT = b'UKEY2 v1 auth'
NEXT_SALT = b'UKEY2 v1 next'


class HandshakeError(Exception):
    """The other end said something this cannot continue from."""


def hkdf(salt, key, info, length=32):
    return HKDF(algorithm=hashes.SHA256(), length=length, salt=salt,
                info=info).derive(key)


def pad(blob):
    """PKCS#7 to the AES block size. A full block of padding when it fits."""
    fill = 16 - len(blob) % 16
    return blob + bytes([fill]) * fill


def unpad(blob):
    if not blob or len(blob) % 16:
        raise HandshakeError('ciphertext is not a whole number of blocks')
    fill = blob[-1]
    if not 1 <= fill <= 16 or blob[-fill:] != bytes([fill]) * fill:
        raise HandshakeError('bad padding')
    return blob[:-fill]


# ---------------------------------------------------------------------------
# keys on the wire
# ---------------------------------------------------------------------------

def public_key_bytes(key):
    """A P-256 public key as securemessage.GenericPublicKey.

    x and y are *unsigned* big-endian, and this is the detail that costs an
    afternoon: a coordinate whose top bit is set gets a leading zero byte
    from some encoders and not others, and the far end hashes what it was
    sent. Fixed 32-byte fields, no sign byte, no trimming.
    """
    numbers = key.public_numbers()
    x = numbers.x.to_bytes(32, 'big')
    y = numbers.y.to_bytes(32, 'big')
    ec_key = pb.pack((1, x), (2, y))                 # EcP256PublicKey
    return pb.pack((1, EC_P256), (2, ec_key))        # GenericPublicKey


def public_key_from(blob):
    fields = pb.unpack(blob)
    if pb.one(fields, 1) != EC_P256:
        raise HandshakeError('the other end is not using P-256')
    ec_key = pb.submessage(fields, 2)
    if ec_key is None:
        raise HandshakeError('no EC public key in the message')
    x = pb.one(ec_key, 1)
    y = pb.one(ec_key, 2)
    if not isinstance(x, bytes) or not isinstance(y, bytes):
        raise HandshakeError('malformed EC public key')
    # Some encoders sign-pad to 33 bytes; take the low 32 either way.
    numbers = ec.EllipticCurvePublicNumbers(
        int.from_bytes(x[-32:], 'big'), int.from_bytes(y[-32:], 'big'),
        ec.SECP256R1())
    return numbers.public_key()


def message(kind, body):
    """One Ukey2Message, which is what actually goes on the wire."""
    return pb.pack((1, kind), (2, body))


# ---------------------------------------------------------------------------
# the handshake
# ---------------------------------------------------------------------------

class ClientHandshake:
    """Our side of UKEY2 as the initiator — the side that sends files."""

    def __init__(self):
        self.private = ec.generate_private_key(ec.SECP256R1())
        # CLIENT_FINISH is built now because CLIENT_INIT commits to its hash.
        self.finish = message(
            CLIENT_FINISH, pb.pack((1, public_key_bytes(self.private.public_key()))))
        commitment = hashlib.sha512(self.finish).digest()
        client_init = pb.pack(
            (1, UKEY2_VERSION),
            (2, os.urandom(32)),
            (3, pb.pack((1, P256_SHA512), (2, commitment))),   # CipherCommitment
            (4, NEXT_PROTOCOL))
        self.init = message(CLIENT_INIT, client_init)
        self.server_init = None

    def client_init(self):
        return self.init

    def client_finish(self):
        return self.finish

    def accept_server_init(self, blob):
        """Parse SERVER_INIT and keep the bytes: the KDF hashes them."""
        outer = pb.unpack(blob)
        kind = pb.one(outer, 1)
        if kind != SERVER_INIT:
            raise HandshakeError(f'expected SERVER_INIT, got message type {kind}')
        body = pb.one(outer, 2)
        if not isinstance(body, bytes):
            raise HandshakeError('SERVER_INIT carried no message data')
        fields = pb.unpack(body)
        cipher = pb.one(fields, 3)
        if cipher != P256_SHA512:
            raise HandshakeError(f'server chose cipher {cipher}, not P256_SHA512')
        key = pb.one(fields, 4)
        if not isinstance(key, bytes):
            raise HandshakeError('SERVER_INIT carried no public key')
        self.server_init = blob
        self.peer = public_key_from(key)
        return self.peer

    def context(self):
        """The encrypted channel, once both sides have spoken."""
        if self.server_init is None:
            raise HandshakeError('SERVER_INIT has not arrived yet')
        # SHA-256 of the ECDH output, not the output itself. UKEY2 hashes
        # the shared secret before it becomes HKDF input keying material, and
        # skipping that produces four perfectly self-consistent keys that no
        # real device shares: the handshake completes, the phone answers, and
        # the first encrypted frame back fails to verify.
        shared = hashlib.sha256(
            self.private.exchange(ec.ECDH(), self.peer)).digest()
        transcript = self.init + self.server_init
        next_secret = hkdf(NEXT_SALT, shared, transcript)
        auth = hkdf(AUTH_SALT, shared, transcript)
        return D2DContext(next_secret, is_client=True, auth_string=auth)


class D2DContext:
    """The channel: sequence-numbered, encrypted, and authenticated.

    Four keys out of one secret. The client encrypts with the key derived
    from 'client' and verifies with the one derived from 'server', and the
    other end does the mirror image — so the two directions never share a
    key or a sequence number.
    """

    def __init__(self, next_secret, is_client, auth_string=None):
        client_key = hkdf(D2D_SALT, next_secret, b'client')
        server_key = hkdf(D2D_SALT, next_secret, b'server')
        mine, theirs = ((client_key, server_key) if is_client
                        else (server_key, client_key))
        self.encrypt_key = hkdf(SECURE_MESSAGE_SALT, mine, b'ENC:2')
        self.send_hmac = hkdf(SECURE_MESSAGE_SALT, mine, b'SIG:1')
        self.decrypt_key = hkdf(SECURE_MESSAGE_SALT, theirs, b'ENC:2')
        self.receive_hmac = hkdf(SECURE_MESSAGE_SALT, theirs, b'SIG:1')
        self.auth_string = auth_string
        self.sent = 0
        self.received = 0

    def pin(self):
        """The four digits both screens show, from the auth string.

        Quick Share does not make you compare them for a normal transfer, but
        the value is what stops a machine in the middle, so it is computed
        rather than ignored.
        """
        total = sum((-1 if i % 2 else 1) * byte
                    for i, byte in enumerate(self.auth_string or b''))
        return f'{total % 10000:04d}'

    def encrypt(self, frame):
        self.sent += 1
        body = pb.pack((1, frame), (2, self.sent))        # DeviceToDeviceMessage
        iv = os.urandom(16)
        encryptor = Cipher(algorithms.AES(self.encrypt_key),
                           modes.CBC(iv)).encryptor()
        ciphertext = encryptor.update(pad(body)) + encryptor.finalize()
        metadata = pb.pack((1, DEVICE_TO_DEVICE_MESSAGE), (2, 1))   # GcmMetadata
        header = pb.pack((1, HMAC_SHA256), (2, AES_256_CBC), (5, iv),
                         (6, metadata))
        header_and_body = pb.pack((1, header), (2, ciphertext))
        signature = hmac.new(self.send_hmac, header_and_body,
                             hashlib.sha256).digest()
        return pb.pack((1, header_and_body), (2, signature))

    def decrypt(self, blob):
        fields = pb.unpack(blob)
        header_and_body = pb.one(fields, 1)
        signature = pb.one(fields, 2)
        if not isinstance(header_and_body, bytes) or not isinstance(signature, bytes):
            raise HandshakeError('malformed SecureMessage')
        expected = hmac.new(self.receive_hmac, header_and_body,
                            hashlib.sha256).digest()
        # Constant time: this is the check that says the message is theirs.
        if not hmac.compare_digest(expected, signature):
            raise HandshakeError('signature does not verify')
        inner = pb.unpack(header_and_body)
        header = pb.submessage(inner, 1)
        ciphertext = pb.one(inner, 2)
        if header is None or not isinstance(ciphertext, bytes):
            raise HandshakeError('malformed HeaderAndBody')
        iv = pb.one(header, 5)
        if not isinstance(iv, bytes) or len(iv) != 16:
            raise HandshakeError('missing or bad IV')
        decryptor = Cipher(algorithms.AES(self.decrypt_key),
                           modes.CBC(iv)).decryptor()
        plain = unpad(decryptor.update(ciphertext) + decryptor.finalize())
        d2d = pb.unpack(plain)
        self.received = pb.one(d2d, 2, self.received)
        payload = pb.one(d2d, 1)
        if not isinstance(payload, bytes):
            raise HandshakeError('DeviceToDeviceMessage carried no message')
        return payload
