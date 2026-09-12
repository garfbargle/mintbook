"""Quick Share — how this machine says hello to an Android phone.

Samsung's and Google's Quick Share is the same idea as AirDrop with one
decisive difference: it announces over BLE and mDNS but moves the bytes over
an ordinary TCP connection on the access point both devices are already
associated with. AirDrop puts the data itself on AWDL, which needs a radio
this machine does not have. That is the whole reason a phone can be made to
see this laptop and an iPhone cannot. See docs/mintdrop.md.

This module is the part that can be got right before anything is negotiated:
the identity, and the mDNS advertisement built out of it. The phone starts
looking when its share sheet opens, finds `_FC9F5ED42C8A._tcp` on the
network, and shows whatever name is in the TXT record. Nothing here talks to
Google, and nothing here needs an account.

The protocol is not documented by Google. The byte layouts below follow
grishka's reverse-engineered specification, which the Linux and macOS
implementations all build on:

    https://github.com/grishka/NearDrop/blob/master/PROTOCOL.md

Every offset in this file is load-bearing in a way that fails silently: a
wrong bit in the first byte does not raise anything, it just means the phone
never lists the machine. The tests pin the layout for that reason.
"""
import base64
import os
import random
import socket
import string
import time

# SHA-256("NearbySharing"), first three bytes, as everyone's service type.
SERVICE = '_FC9F5ED42C8A._tcp'
SERVICE_ID = b'\xfc\x9f\x5e'

# The port the phone is told to connect to. Deliberately the same socket
# mintdrop already listens on: bin/mintdrop reads four bytes before deciding
# anything, and 'MNTD' is not a protobuf length, so the two protocols share
# one listener and one socket unit rather than doubling the idle cost.
PORT = 8771

# P2P_CLUSTER. The first byte of the mDNS instance name.
PCP = 0x23

UNKNOWN, PHONE, TABLET, LAPTOP, CAR, FOLDABLE, XR = range(7)

STATE = os.path.expanduser('~/.local/state/mintbook')
ENDPOINT_FILE = os.path.join(STATE, 'quickshare-endpoint')


def endpoint_id():
    """Four characters identifying this machine for the length of a session.

    Kept in a file rather than regenerated: a phone that has seen this laptop
    remembers the endpoint, and a new id on every boot would show up as a new
    device each time. Four alphanumerics is what the protocol allows.
    """
    try:
        with open(ENDPOINT_FILE) as f:
            saved = f.read().strip()
        if len(saved) == 4 and saved.isalnum() and saved.isascii():
            return saved
    except OSError:
        pass
    fresh = ''.join(random.choice(string.ascii_uppercase + string.digits)
                    for _ in range(4))
    try:
        os.makedirs(STATE, exist_ok=True)
        with open(ENDPOINT_FILE, 'w') as f:
            f.write(fresh + '\n')
    except OSError:
        pass
    return fresh


def b64(blob):
    """URL-safe base64 with the padding stripped, which is what the wire uses."""
    return base64.urlsafe_b64encode(blob).decode().rstrip('=')


def instance_name(endpoint=None):
    """The mDNS instance name: ten bytes, base64url, no padding.

        byte 0      0x23, P2P_CLUSTER
        bytes 1-4   the endpoint id
        bytes 5-7   the service id, 0xFC 0x9F 0x5E
        bytes 8-9   zero

    This is a name, not a record: the phone parses the service instance's own
    label to learn the endpoint id before it resolves anything.
    """
    # `is None` rather than falsy: only an absent endpoint means "use this
    # machine's". An empty string is a caller that has lost its id, and
    # quietly advertising a different one is how a phone ends up unable to
    # connect to the device it just listed.
    endpoint = (endpoint_id() if endpoint is None else endpoint).encode()
    if len(endpoint) != 4:
        raise ValueError('endpoint id must be 4 characters')
    blob = bytes([PCP]) + endpoint + SERVICE_ID + b'\x00\x00'
    assert len(blob) == 10
    return b64(blob)


def endpoint_info(name, device_type=LAPTOP, visible=True, version=0):
    """The `n` TXT record — the byte that decides whether the phone lists us.

        byte 0        version << 5 | visible << 4 | device_type << 1
        bytes 1-2     salt
        bytes 3-16    encrypted metadata key
        byte 17       length of the device name
        bytes 18+     the device name, UTF-8

    The salt and metadata key identify a *Google account* to a phone that
    already knows it — which is how "Contacts" visibility works. Nothing here
    has an account, so those sixteen bytes are random: the phone cannot place
    us as a contact and lists the machine under Everyone instead, which is
    the visibility a laptop with no account should have anyway.

    `visible` is 0 for visible. It reads backwards because the bit means
    hidden, and the name follows it only when there is a name to show.
    """
    if not 0 <= device_type <= 7:
        raise ValueError('device type out of range')
    flags = (version << 5) | ((0 if visible else 1) << 4) | (device_type << 1)
    blob = bytes([flags]) + os.urandom(16)
    if visible:
        encoded = name.encode()[:255]
        # A name cut mid-character is a name with a replacement glyph in it on
        # the phone; drop the broken tail rather than show one.
        encoded = encoded.decode(errors='ignore').encode()
        blob += bytes([len(encoded)]) + encoded
    return blob


def parse_endpoint_info(blob):
    """The other direction: what a phone's TXT record says about itself.

    Returns (device_type, name or None). A phone set to Contacts-only
    advertises the flags and the sixteen identity bytes and stops there — the
    name is withheld from anyone who cannot decrypt the metadata key, which
    is everyone without the matching Google account. That is not an error and
    not something to fix; it means the caller shows the mDNS host label
    instead.
    """
    if not blob:
        raise ValueError('empty endpoint info')
    flags = blob[0]
    device_type = (flags >> 1) & 0b111
    name = None
    if len(blob) > 17:
        length = blob[17]
        raw = blob[18:18 + length]
        if len(raw) == length:
            name = raw.decode('utf-8', errors='replace') or None
    return device_type, name


def discover(timeout=1.5):
    """Quick Share devices on this network, from the running avahi-daemon.

    Same browse-while-open rule as mintdrop's own discovery: one short
    avahi-browse, nothing resident. Our own advertisement is filtered out by
    endpoint id, which is the one identifier that is ours by construction.
    """
    import subprocess
    argv = ['avahi-browse', '--resolve', '--terminate', '--parsable',
            '--no-db-lookup', SERVICE]
    try:
        out = subprocess.run(argv, text=True, capture_output=True,
                             timeout=max(timeout, 1) + 4)
    except (OSError, subprocess.SubprocessError):
        return []
    # Two ways of recognising ourselves, because one is not enough: the
    # endpoint id is exact but lives in a state file that can be missing, and
    # a machine that has lost it would otherwise advertise itself, discover
    # itself, and offer to send files to itself. The addresses catch that.
    ours = instance_name()
    our_addresses = set()
    try:
        import importlib.machinery
        import importlib.util
        loader = importlib.machinery.SourceFileLoader(
            'mintbook_drop', os.path.join(os.path.dirname(
                os.path.realpath(__file__)), 'mintbook_drop.py'))
        module = importlib.util.module_from_spec(
            importlib.util.spec_from_loader(loader.name, loader))
        loader.exec_module(module)
        our_addresses = module.local_addresses()
    except Exception:
        pass
    found = {}
    for line in out.stdout.splitlines():
        parts = line.split(';')
        if len(parts) < 10 or parts[0] != '=':
            continue
        label, host, address, port = parts[3], parts[6], parts[7], parts[8]
        if label == ours or address.split('%')[0] in our_addresses:
            continue
        info = None
        for item in parts[9].split('" "'):
            item = item.strip('"')
            if item.startswith('n='):
                try:
                    info = base64.urlsafe_b64decode(
                        item[2:] + '=' * (-len(item[2:]) % 4))
                except Exception:
                    info = None
        device_type, name = (None, None)
        if info:
            try:
                device_type, name = parse_endpoint_info(info)
            except ValueError:
                pass
        # A withheld name leaves the mDNS host label, which is the only other
        # thing the phone has told us. 'Android_GFD7A3R3.local' reads better
        # with the suffix and the underscore gone.
        if not name:
            name = host.removesuffix('.local').replace('_', ' ')
        try:
            port = int(port)
        except ValueError:
            continue
        current = found.get(label)
        if current is None or (parts[2] == 'IPv4' and ':' in current['address']):
            found[label] = {'name': name, 'address': address, 'port': port,
                            'endpoint': label, 'protocol': 'quickshare',
                            'device_type': device_type if device_type is not None
                            else PHONE}
    return sorted(found.values(), key=lambda p: p['name'].lower())


def avahi_service(name, port=PORT, device_type=LAPTOP, endpoint=None):
    """The static advertisement, as an avahi service file.

    A file rather than a process, for the reason the rest of mintdrop is
    built this way: avahi-daemon is already running, so being discoverable
    costs nothing that was not already running. The endpoint id and the
    random metadata bytes are fixed when this is generated, which is why
    bin/mintdrop-install writes it rather than shipping it.
    """
    info = b64(endpoint_info(name, device_type))
    return f'''<?xml version="1.0" standalone='no'?><!--*-nxml-*-->
<!DOCTYPE service-group SYSTEM "avahi-service.dtd">

<!-- Quick Share. GENERATED by bin/mintdrop-install — edit
     bin/mintbook_quickshare.py instead, then reinstall.

     The instance name carries the endpoint id and the TXT record carries the
     name the phone shows. Both are fixed at install time so that a phone
     which has seen this machine keeps seeing the same one. -->
<service-group>
  <name>{instance_name(endpoint)}</name>
  <service>
    <type>{SERVICE}</type>
    <port>{port}</port>
    <txt-record>n={info}</txt-record>
  </service>
</service-group>
'''


# ===========================================================================
# The conversation
# ===========================================================================
#
# Everything below talks to a phone. The shape, once the socket is open:
#
#     ->  OfflineFrame CONNECTION_REQUEST      who we are          plaintext
#     ->  Ukey2 CLIENT_INIT                                        plaintext
#     <-  Ukey2 SERVER_INIT                                        plaintext
#     ->  Ukey2 CLIENT_FINISH                                      plaintext
#     ->  OfflineFrame CONNECTION_RESPONSE     accept              plaintext
#     <-  OfflineFrame CONNECTION_RESPONSE                         plaintext
#     -><- PAIRED_KEY_ENCRYPTION / _RESULT     who we claim to be  encrypted
#     ->  INTRODUCTION                         these files         encrypted
#     <-  RESPONSE  ACCEPT                     the phone's prompt  encrypted
#     ->  PAYLOAD_TRANSFER ...                 the bytes           encrypted
#
# Two layers of frame share the word. `OfflineFrame` is Nearby Connections —
# the transport. The sharing `Frame` is the application on top, and it does
# not get its own socket: it travels as the body of a BYTES payload inside a
# PAYLOAD_TRANSFER OfflineFrame. Files travel the same way with a FILE
# payload. Everything after the handshake is inside a SecureMessage.
#
# Every field number is from vendor/nearby-protobufs.

import struct

# offline_wire_formats.proto — V1Frame.FrameType
CONNECTION_REQUEST, CONNECTION_RESPONSE, PAYLOAD_TRANSFER = 1, 2, 3
KEEP_ALIVE, DISCONNECTION = 5, 6
WIFI_LAN = 5                                   # ConnectionRequestFrame.Medium
ACCEPT_RESPONSE = 1                            # ResponseStatus.ACCEPT
OS_LINUX = 100                                 # OsInfo.OsType

# PayloadTransferFrame
PACKET_DATA = 1
PAYLOAD_BYTES, PAYLOAD_FILE = 1, 2
LAST_CHUNK = 1

# wire_format.proto — V1Frame.FrameType
INTRODUCTION, RESPONSE, PAIRED_KEY_ENCRYPTION, PAIRED_KEY_RESULT = 1, 2, 3, 4
SHARING_ACCEPT, SHARING_REJECT = 1, 2           # ConnectionResponseFrame.Status
PAIRED_KEY_UNABLE = 3                           # PairedKeyResultFrame.Status

# Nearby moves files in chunks. 512 KiB is what the Android side uses; a
# larger one is not faster over a radio that is the bottleneck anyway, and a
# smaller one multiplies the per-frame encryption cost.
CHUNK = 512 * 1024
MAX_FRAME = 8 << 20


class ProtocolError(Exception):
    """The phone said something we cannot continue from."""


def _load(name):
    import importlib.machinery
    import importlib.util
    loader = importlib.machinery.SourceFileLoader(
        name, os.path.join(os.path.dirname(os.path.realpath(__file__)),
                           name + '.py'))
    module = importlib.util.module_from_spec(
        importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(module)
    return module


pb = _load('mintbook_protobuf')
ukey2 = _load('mintbook_ukey2')


# ---------------------------------------------------------------------------
# frames
# ---------------------------------------------------------------------------

def offline_frame(frame_type, **bodies):
    """OfflineFrame{version=V1, v1=V1Frame{type, <one body>}}."""
    fields = [(1, frame_type)]
    for number, body in bodies.values():
        fields.append((number, body))
    return pb.pack((1, 1), (2, pb.pack(*fields)))


def connection_request(endpoint, info):
    body = pb.pack(
        (1, endpoint),                 # endpoint_id
        (5, [WIFI_LAN]),               # mediums: we are on the LAN
        (6, info),                     # endpoint_info — carries our name
        (8, 10_000),                   # keep_alive_interval_millis
        (9, 30_000))                   # keep_alive_timeout_millis
    return offline_frame(CONNECTION_REQUEST, connection_request=(2, body))


def connection_response_accept():
    body = pb.pack((1, 0),             # status, deprecated but still read
                   (3, ACCEPT_RESPONSE),
                   (4, pb.pack((1, OS_LINUX))))     # os_info
    return offline_frame(CONNECTION_RESPONSE, connection_response=(3, body))


def keep_alive(ack=False):
    return offline_frame(KEEP_ALIVE, keep_alive=(6, pb.pack((1, bool(ack)))))


def disconnection():
    return offline_frame(DISCONNECTION, disconnection=(7, pb.pack()))


def bytes_payload(payload_id, blob):
    """A sharing frame, wrapped so the transport will carry it."""
    header = pb.pack((1, payload_id), (2, PAYLOAD_BYTES), (3, len(blob)))
    chunk = pb.pack((1, LAST_CHUNK), (2, 0), (3, blob))
    body = pb.pack((1, PACKET_DATA), (2, header), (3, chunk))
    return offline_frame(PAYLOAD_TRANSFER, payload_transfer=(4, body))


def file_chunk(payload_id, size, name, offset, blob, last=False):
    header = pb.pack((1, payload_id), (2, PAYLOAD_FILE), (3, size), (5, name))
    chunk = pb.pack((1, LAST_CHUNK if last else 0), (2, offset),
                    (3, blob if blob else None))
    body = pb.pack((1, PACKET_DATA), (2, header), (3, chunk))
    return offline_frame(PAYLOAD_TRANSFER, payload_transfer=(4, body))


def sharing_frame(frame_type, **bodies):
    fields = [(1, frame_type)]
    for number, body in bodies.values():
        fields.append((number, body))
    return pb.pack((1, 1), (2, pb.pack(*fields)))


def paired_key_encryption():
    """We have no certificate, so this says so in the only way the protocol
    allows: random bytes the phone cannot match against a contact. It then
    treats us as an unknown device and asks the person holding it."""
    return sharing_frame(PAIRED_KEY_ENCRYPTION,
                         paired_key_encryption=(4, pb.pack(
                             (1, os.urandom(72)),      # signed_data
                             (2, os.urandom(6)))))     # secret_id_hash


def paired_key_result():
    return sharing_frame(PAIRED_KEY_RESULT,
                         paired_key_result=(5, pb.pack((1, PAIRED_KEY_UNABLE))))


def introduction(files):
    """'Here is what I would like to send you' — this is what raises the
    prompt on the phone."""
    metadata = [pb.pack((1, f['name']),
                        (2, f.get('kind', 0)),
                        (3, f['payload_id']),
                        (4, f['size']),
                        (5, f.get('mime', 'application/octet-stream')))
                for f in files]
    return sharing_frame(INTRODUCTION,
                         introduction=(2, pb.pack((1, metadata))))


# ---------------------------------------------------------------------------
# the connection
# ---------------------------------------------------------------------------

class Connection:
    """One conversation with a phone, framed and then encrypted.

    Every message on this socket — handshake, transport frame, file chunk —
    is a 4-byte big-endian length followed by that many bytes. After UKEY2
    the bytes are a SecureMessage wrapping what would otherwise be there.
    """

    def __init__(self, sock):
        self.sock = sock
        self.context = None
        self.payload_id = random.randint(1, 2 ** 31)

    # -- framing -----------------------------------------------------------

    def send_raw(self, blob):
        self.sock.sendall(struct.pack('>I', len(blob)) + blob)

    def recv_exactly(self, count):
        parts = []
        while count:
            chunk = self.sock.recv(count)
            if not chunk:
                raise ProtocolError('the phone closed the connection')
            parts.append(chunk)
            count -= len(chunk)
        return b''.join(parts)

    def recv_raw(self):
        length, = struct.unpack('>I', self.recv_exactly(4))
        if length > MAX_FRAME:
            # The length is the first thing a broken or hostile peer controls.
            raise ProtocolError(f'frame of {length} bytes is implausible')
        return self.recv_exactly(length)

    def send(self, frame):
        self.send_raw(self.context.encrypt(frame) if self.context else frame)

    def recv(self):
        blob = self.recv_raw()
        return self.context.decrypt(blob) if self.context else blob

    # -- handshake ---------------------------------------------------------

    def connect_as_client(self, endpoint, info):
        """Introduce ourselves and put the channel up.

        The order is not negotiable: CONNECTION_REQUEST is plaintext and must
        come first, the three UKEY2 messages follow, and only then does
        CONNECTION_RESPONSE — still plaintext — close the plaintext phase.
        """
        self.send_raw(connection_request(endpoint, info))

        handshake = ukey2.ClientHandshake()
        self.send_raw(handshake.client_init())
        handshake.accept_server_init(self.recv_raw())
        self.send_raw(handshake.client_finish())

        self.send_raw(connection_response_accept())
        their_response = pb.submessage(pb.unpack(self.recv_raw()), 2)
        if their_response is None or pb.one(their_response, 1) != CONNECTION_RESPONSE:
            raise ProtocolError('the phone did not answer the connection')

        # Everything from here is encrypted.
        self.context = handshake.context()
        return self.context

    # -- the sharing layer -------------------------------------------------

    def send_sharing(self, frame):
        self.payload_id += 1
        self.send(bytes_payload(self.payload_id, frame))

    def next_sharing(self, timeout=60):
        """The next sharing frame, answering keep-alives while we wait.

        Android sends KEEP_ALIVE every ten seconds and expects one back. It
        arrives interleaved with everything else, so it is handled here
        rather than by every caller — a transfer waiting on a person to tap
        Accept is mostly a transfer exchanging keep-alives.
        """
        deadline = time.monotonic() + timeout
        while True:
            self.sock.settimeout(max(deadline - time.monotonic(), 0.1))
            try:
                blob = self.recv()
            except socket.timeout:
                raise ProtocolError('the phone stopped answering')
            v1 = pb.submessage(pb.unpack(blob), 2)
            if v1 is None:
                continue
            kind = pb.one(v1, 1)
            if kind == KEEP_ALIVE:
                self.send(keep_alive(ack=True))
            elif kind == DISCONNECTION:
                raise ProtocolError('the phone hung up')
            elif kind == PAYLOAD_TRANSFER:
                transfer = pb.submessage(v1, 4)
                header = pb.submessage(transfer or {}, 2)
                chunk = pb.submessage(transfer or {}, 3)
                if not header or not chunk:
                    continue
                if pb.one(header, 2) != PAYLOAD_BYTES:
                    continue
                body = pb.one(chunk, 3)
                if not body:
                    continue
                inner = pb.submessage(pb.unpack(body), 2)
                if inner is not None:
                    return inner
            if time.monotonic() > deadline:
                raise ProtocolError('the phone stopped answering')

    def pair(self):
        """Exchange the paired-key frames. We have no certificate, so this
        only establishes that we are a stranger — which is the whole reason
        the phone then asks its owner."""
        self.send_sharing(paired_key_encryption())
        seen = set()
        # The phone sends its own encryption frame and a result frame. Both
        # arrive before anything else will, and neither needs an answer
        # beyond ours.
        while len(seen) < 2:
            frame = self.next_sharing(timeout=20)
            kind = pb.one(frame, 1)
            seen.add(kind)
            if kind == PAIRED_KEY_ENCRYPTION:
                self.send_sharing(paired_key_result())
            elif kind not in (PAIRED_KEY_RESULT,):
                return frame          # something else already: hand it back
        return None

    def introduce(self, files, timeout=120):
        """Offer the files, and wait for the person to answer the prompt."""
        self.send_sharing(introduction(files))
        while True:
            frame = self.next_sharing(timeout=timeout)
            if pb.one(frame, 1) != RESPONSE:
                continue
            response = pb.submessage(frame, 3)
            return pb.one(response or {}, 1)

    def send_file(self, entry, progress=None):
        """The bytes, in chunks, then an empty last chunk.

        Not sendfile(): every chunk is encrypted and framed, so the bytes
        have to come through this process. That is the protocol's price, not
        a choice — the mintdrop path between two Linux machines keeps its
        zero-copy send precisely because it does not have to do this.
        """
        sent = 0
        with open(entry['path'], 'rb') as f:
            while True:
                block = f.read(CHUNK)
                if not block:
                    break
                self.send(file_chunk(entry['payload_id'], entry['size'],
                                     entry['name'], sent, block))
                sent += len(block)
                if progress:
                    progress(len(block))
        self.send(file_chunk(entry['payload_id'], entry['size'],
                             entry['name'], sent, b'', last=True))
        return sent

    def close(self):
        try:
            self.send(disconnection())
        except (OSError, ProtocolError, AttributeError):
            pass
        try:
            self.sock.close()
        except OSError:
            pass


def send_files(peer, paths, name=None, on_wait=None, progress=None):
    """Send files to a Quick Share device. Returns (sent bytes, seconds).

    `on_wait` is called once the offer is out and the phone is showing its
    prompt — there is nothing to report for as long as somebody takes to
    pick the notification up, and a progress bar that sits at zero for that
    whole time looks broken.
    """
    files = []
    for path in paths:
        size = os.stat(path).st_size
        files.append({'path': path, 'name': os.path.basename(path),
                      'size': size,
                      'payload_id': random.randint(1, 2 ** 62)})

    family = socket.AF_INET6 if ':' in peer['address'] else socket.AF_INET
    sock = socket.socket(family, socket.SOCK_STREAM)
    sock.settimeout(15)
    sock.connect((peer['address'], peer['port']))
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

    connection = Connection(sock)
    started = time.monotonic()
    try:
        connection.connect_as_client(
            endpoint_id(), endpoint_info(name or device_name()))
        connection.pair()
        if on_wait:
            on_wait()
        status = connection.introduce(files)
        if status != SHARING_ACCEPT:
            raise ProtocolError('declined on the phone'
                                if status == SHARING_REJECT
                                else f'the phone answered {status}')
        total = 0
        for entry in files:
            total += connection.send_file(entry, progress)
        return total, time.monotonic() - started
    finally:
        connection.close()
