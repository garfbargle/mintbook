"""Nearby's control packets on a BLE L2CAP channel.

A phone that discovers this machine over BLE opens the L2CAP channel named in
the advertisement header and talks *this* before anything else. Until it is
answered the channel is useless: the Z Fold7 sent its first packet and, one
second later, `l2c_link_timeout: All channels closed`. Silence is what it
read as failure, not anything about the share itself.

The format is Google's, from connections/implementation/mediums/ble in
google/nearby, and is two layers:

    frame     length(4, big endian) , payload
    payload   command(1)  ,  for the commands that carry data:
              command(1) , length(2, big endian) , data

Only REQUEST_ADVERTISEMENT and RESPONSE_ADVERTISEMENT carry data; every other
command is a bare byte. The 4-byte frame length is not in the C++ packet code
— it belongs to the stream layer above it (`kL2CAPPacketLength = 4` in the
Apple implementation) — but it is on the wire in both directions, and the
first packet this machine ever received from the phone opened with it:

    00 00 00 06  01  00 03  16 d9 ae
    <-- length   ^   <-len  <-- service id hash

L2CAP is SOCK_SEQPACKET here, so a read already returns one message and the
length is redundant. It is still parsed rather than assumed: a phone is free
to split a frame across packets, and trusting the boundary would be trusting
something nothing guarantees.
"""
import hashlib
import importlib.machinery
import importlib.util
import os


def _load(name):
    loader = importlib.machinery.SourceFileLoader(
        name, os.path.join(os.path.dirname(os.path.realpath(__file__)),
                           name + '.py'))
    module = importlib.util.module_from_spec(
        importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(module)
    return module


pb = _load('mintbook_protobuf')

# Requests a phone sends.
REQUEST_ADVERTISEMENT = 1
REQUEST_ADVERTISEMENT_FINISH = 2
REQUEST_DATA_CONNECTION = 3
# Responses this machine sends. The gap from 3 to 21 is reserved in Google's
# enum, so leaving it empty is deliberate rather than an oversight.
RESPONSE_ADVERTISEMENT = 21
RESPONSE_SERVICE_ID_NOT_FOUND = 22
RESPONSE_DATA_CONNECTION_READY = 23
RESPONSE_DATA_CONNECTION_FAILURE = 24

NAMES = {
    REQUEST_ADVERTISEMENT: 'REQUEST_ADVERTISEMENT',
    REQUEST_ADVERTISEMENT_FINISH: 'REQUEST_ADVERTISEMENT_FINISH',
    REQUEST_DATA_CONNECTION: 'REQUEST_DATA_CONNECTION',
    RESPONSE_ADVERTISEMENT: 'RESPONSE_ADVERTISEMENT',
    RESPONSE_SERVICE_ID_NOT_FOUND: 'RESPONSE_SERVICE_ID_NOT_FOUND',
    RESPONSE_DATA_CONNECTION_READY: 'RESPONSE_DATA_CONNECTION_READY',
    RESPONSE_DATA_CONNECTION_FAILURE: 'RESPONSE_DATA_CONNECTION_FAILURE',
}

# The commands whose payload is command + length + data. Everything else is a
# single byte, and a length on one of those would be misread as a command.
WITH_DATA = (REQUEST_ADVERTISEMENT, RESPONSE_ADVERTISEMENT)

SERVICE_ID_HASH_LENGTH = 3
# The advertisement the header points at is far smaller than this; the cap is
# Google's, and is here so a bad length cannot ask for an unbounded read.
MAX_ADVERTISEMENT = 512
MAX_FRAME = 5 * 1024 * 1024


class ProtocolError(Exception):
    """A packet that cannot be read as one."""


def service_id_hash(service_id):
    """The 3 bytes a phone names a service by.

    Plain SHA-256, truncated — the same hash the BLE advertisement carries,
    which is why a request can be matched against what is being advertised
    without keeping a second table.
    """
    if isinstance(service_id, str):
        service_id = service_id.encode()
    return hashlib.sha256(service_id).digest()[:SERVICE_ID_HASH_LENGTH]


def payload(command, data=None):
    """One packet, without the frame length."""
    if command in WITH_DATA:
        if not data:
            raise ProtocolError(f'{NAMES.get(command, command)} needs data')
        if len(data) > 0xFFFF:
            raise ProtocolError('data too long for a 2-byte length')
        return bytes([command]) + len(data).to_bytes(2, 'big') + bytes(data)
    if data:
        raise ProtocolError(f'{NAMES.get(command, command)} carries no data')
    return bytes([command])


def frame(command, data=None):
    """One packet, ready to write to the channel."""
    body = payload(command, data)
    return len(body).to_bytes(4, 'big') + body


def parse(body):
    """Read one payload. Returns (command, data), data possibly empty.

    Anything unrecognised raises rather than being guessed at. A command this
    does not know is a command it cannot answer correctly, and answering
    incorrectly is worse than saying so.
    """
    if len(body) < 1:
        raise ProtocolError('empty packet')
    command = body[0]
    if command not in WITH_DATA:
        if command not in NAMES:
            raise ProtocolError(f'unsupported command {command}')
        return command, b''
    if len(body) < 3:
        raise ProtocolError(f'{NAMES[command]} without a length')
    length = int.from_bytes(body[1:3], 'big')
    if length == 0:
        raise ProtocolError(f'{NAMES[command]} with a zero length')
    data = body[3:3 + length]
    if len(data) != length:
        raise ProtocolError(
            f'{NAMES[command]} wants {length} bytes, got {len(data)}')
    if command == REQUEST_ADVERTISEMENT and length < SERVICE_ID_HASH_LENGTH:
        raise ProtocolError(f'service id hash is {length} bytes, not 3')
    if command == RESPONSE_ADVERTISEMENT and length > MAX_ADVERTISEMENT:
        raise ProtocolError(f'advertisement of {length} bytes is too long')
    return command, data


class Reader:
    """Frames in, packets out.

    Feed it whatever a read returned; take whole packets off it. This exists
    because the 4-byte length is the only thing that says where a packet ends
    — SOCK_SEQPACKET usually agrees, but a sender is not obliged to make it
    agree, and a reassembler that is wrong only under load is worse than one
    that is always used.
    """

    def __init__(self):
        self.buffer = bytearray()

    def feed(self, data):
        self.buffer.extend(data)
        return self

    def packets(self):
        while True:
            if len(self.buffer) < 4:
                return
            length = int.from_bytes(self.buffer[:4], 'big')
            if length == 0 or length > MAX_FRAME:
                raise ProtocolError(f'frame length {length} is not credible')
            if len(self.buffer) < 4 + length:
                return
            body = bytes(self.buffer[4:4 + length])
            del self.buffer[:4 + length]
            yield parse(body)


# Once the channel is a data connection it stops carrying the control packets
# above and carries this instead:
#
#     length(4, big endian) , service id hash(3) , payload
#
# with two kinds of payload, told apart by the hash:
#
#   00 00 00   a control protobuf — the phone opening or closing a service
#   <ours>     the Nearby conversation itself, which is a 4-byte length and
#              an OfflineFrame, exactly what mintdrop already speaks on TCP
#
# All four packets a Z Fold7 sent fit this: a connect naming the service and
# a token, a 639-byte ConnectionRequest ("Codi's Z Fold7", endpoint QYJ7), a
# 136-byte UKEY2 client init, and a disconnect. The envelope is the only
# thing that differs from the TCP path, which is why Channel below is an
# adapter and not a second implementation of the protocol.
CONTROL_HASH = b'\x00\x00\x00'

# proto/mediums/ble_frames.proto, SocketControlFrame.ControlFrameType. The
# phone sends all three: an INTRODUCTION naming the service, a
# PACKET_ACKNOWLEDGEMENT for every data packet it receives, and a
# DISCONNECTION at the end.
INTRODUCTION = 1
DISCONNECTION = 2
PACKET_ACKNOWLEDGEMENT = 3


def acknowledgement(service_id_hash, received):
    """Say how many bytes just arrived.

    Nearby's BLE socket acknowledges every data packet, and the count is the
    whole envelope payload — hash included — not the bytes handed upward. A
    Z Fold7 acked this machine's 123-byte ServerInit with `received_size:
    123`, which is what fixes the number: 3 bytes of hash plus 120 of frame.

    This is flow control, so not sending it is not a missing nicety. The
    sender is waiting.
    """
    body = pb.pack((1, service_id_hash), (2, received))
    return pb.pack((1, PACKET_ACKNOWLEDGEMENT), (4, body))

# Conservative: an LE L2CAP channel negotiates its MTU and this is the
# smallest that is reasonable to assume. A message longer than this is split
# across packets, which is safe because the length prefix — not the packet
# boundary — is what says where a message ends.
DEFAULT_MTU = 512


class Channel:
    """The Nearby byte stream, with the L2CAP envelope taken off.

    Presents `recv` and `sendall`, which is all the Quick Share receiver
    wants from a socket, so the same code that serves a phone over TCP can
    serve one over BLE without knowing the difference.
    """

    def __init__(self, socket_, service_id_hash, mtu=DEFAULT_MTU, log=None):
        self.socket = socket_
        self.hash = service_id_hash
        self.mtu = mtu
        self.log = log or (lambda message: None)
        self.reader = Reader()
        self.stream = bytearray()          # inner bytes, envelope removed
        self.closed = False
        self.control = []                  # what the phone said out of band

    # -- the socket face --------------------------------------------------

    def recv(self, count):
        while not self.stream and not self.closed:
            self._pump()
        taken = bytes(self.stream[:count])
        del self.stream[:count]
        return taken

    def sendall(self, data):
        # One message may span several packets; the receiver reassembles on
        # the length, so the split point does not have to mean anything.
        room = self.mtu - 4 - len(self.hash)
        body = len(self.hash) + len(data)
        packet = body.to_bytes(4, 'big') + self.hash + bytes(data)
        for start in range(0, len(packet), self.mtu):
            self.socket.send(packet[start:start + self.mtu])
        if room <= 0:                      # pathological MTU; say so loudly
            raise ProtocolError(f'mtu of {self.mtu} leaves no room for data')

    def settimeout(self, seconds):
        self.socket.settimeout(seconds)

    def close(self):
        self.closed = True
        try:
            self.socket.close()
        except OSError:
            pass

    # -- the envelope ------------------------------------------------------

    def _pump(self):
        try:
            chunk = self.socket.recv(4096)
        except OSError:
            self.closed = True
            return
        if not chunk:
            self.closed = True
            return
        self.reader.feed(chunk)
        for payload in self._envelopes():
            head, body = payload[:len(self.hash)], payload[len(self.hash):]
            if head == self.hash:
                self.stream.extend(body)
                self._acknowledge(len(payload))
            elif head == CONTROL_HASH:
                # Opening and closing a service. The phone does not wait for
                # an answer to these — it sent its ConnectionRequest without
                # one — so they are recorded, and a close ends the stream.
                self.control.append(body)
                self.log(f'  control {body.hex(" ")[:48]}')
                if body[:2] == b'\x08\x02':
                    self.closed = True
            else:
                self.log(f'  packet for another service {head.hex(" ")}')

    def _acknowledge(self, received):
        """Every data packet is acknowledged; the phone waits for it."""
        frame_ = acknowledgement(self.hash, received)
        packet = (len(CONTROL_HASH) + len(frame_)).to_bytes(4, 'big') \
            + CONTROL_HASH + frame_
        try:
            self.socket.send(packet)
        except OSError as exc:
            self.log(f'  could not acknowledge {received} bytes: {exc}')
            self.closed = True

    def _envelopes(self):
        """Whole `length , hash , payload` packets, as they complete."""
        while True:
            if len(self.reader.buffer) < 4:
                return
            length = int.from_bytes(self.reader.buffer[:4], 'big')
            if length < len(self.hash) or length > MAX_FRAME:
                raise ProtocolError(f'frame length {length} is not credible')
            if len(self.reader.buffer) < 4 + length:
                return
            payload = bytes(self.reader.buffer[4:4 + length])
            del self.reader.buffer[:4 + length]
            yield payload
