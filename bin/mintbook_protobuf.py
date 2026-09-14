"""Just enough protobuf to talk to a phone.

Quick Share speaks protobuf, and the obvious move is `python3-protobuf` plus
generated `_pb2` modules from Google's `.proto` files. This does not do that,
for two reasons: it puts a package and a code-generation step between this
machine and moving a file, and the generated modules would be several
thousand lines of vendored output nobody in this repo can read.

The wire format does not need any of that. A protobuf message is a flat
sequence of `(field number, wire type, value)`, nested messages are just
length-delimited bytes holding another such sequence, and the twenty or so
messages Quick Share needs use four field types between them. So this is the
whole codec, in about a hundred lines, with no dependency and nothing
generated.

    >>> unpack(pack((1, 5), (2, b'hi')))
    {1: [5], 2: [b'hi']}

What it deliberately does not do: field names, defaults, required-field
checks, or groups (wire types 3 and 4, deprecated since 2010 and unused
here). Callers work in field numbers, which is what the protocol
documentation is written in anyway — see bin/mintbook_quickshare.py, where
every number is commented with the field it is.
"""

VARINT, FIXED64, LENGTH, FIXED32 = 0, 1, 2, 5


class ProtobufError(ValueError):
    """A message that is not decodable. Always from the network, never from us."""


class Fixed32(int):
    """An int that must go on the wire as 4 bytes, not as a varint."""


class Fixed64(int):
    """An int that must go on the wire as 8 bytes."""


def varint(value):
    if value < 0:
        # Negative varints are encoded as 10-byte two's complement. Nothing in
        # Quick Share sends one, so a negative here is a bug on this side.
        raise ProtobufError(f'negative varint: {value}')
    out = bytearray()
    while True:
        byte = value & 0x7f
        value >>= 7
        out.append(byte | (0x80 if value else 0))
        if not value:
            return bytes(out)


def read_varint(blob, at):
    value = shift = 0
    while True:
        if at >= len(blob):
            raise ProtobufError('varint runs past the end of the message')
        byte = blob[at]
        at += 1
        value |= (byte & 0x7f) << shift
        if not byte & 0x80:
            return value, at
        shift += 7
        if shift > 63:
            raise ProtobufError('varint too long')


def pack(*fields):
    """Fields as (number, value) pairs, in the order given.

    int -> varint, bool -> varint, bytes -> length-delimited, str -> UTF-8
    length-delimited, Fixed32/Fixed64 -> fixed. A list or tuple value is a
    repeated field and is emitted once per element. None is skipped, so an
    optional field can be passed unconditionally.
    """
    out = bytearray()
    for number, value in fields:
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            for item in value:
                out += pack((number, item))
            continue
        if isinstance(value, Fixed32):
            out += varint(number << 3 | FIXED32) + int(value).to_bytes(4, 'little')
        elif isinstance(value, Fixed64):
            out += varint(number << 3 | FIXED64) + int(value).to_bytes(8, 'little')
        elif isinstance(value, bool):
            out += varint(number << 3 | VARINT) + varint(int(value))
        elif isinstance(value, int):
            out += varint(number << 3 | VARINT) + varint(value)
        else:
            if isinstance(value, str):
                value = value.encode()
            out += varint(number << 3 | LENGTH) + varint(len(value)) + value
    return bytes(out)


def unpack(blob):
    """Decode to {field number: [values]}.

    Repeated because protobuf allows any field to repeat and the last one
    usually wins — keeping every occurrence means a caller can tell the
    difference rather than having it decided here.
    """
    fields = {}
    at = 0
    while at < len(blob):
        key, at = read_varint(blob, at)
        number, wire = key >> 3, key & 7
        if number == 0:
            raise ProtobufError('field number 0')
        if wire == VARINT:
            value, at = read_varint(blob, at)
        elif wire == LENGTH:
            length, at = read_varint(blob, at)
            if at + length > len(blob):
                raise ProtobufError('length-delimited field runs past the end')
            value, at = blob[at:at + length], at + length
        elif wire == FIXED32:
            if at + 4 > len(blob):
                raise ProtobufError('fixed32 runs past the end')
            value, at = int.from_bytes(blob[at:at + 4], 'little'), at + 4
        elif wire == FIXED64:
            if at + 8 > len(blob):
                raise ProtobufError('fixed64 runs past the end')
            value, at = int.from_bytes(blob[at:at + 8], 'little'), at + 8
        else:
            # Groups. Deprecated before this protocol existed; if one ever
            # arrives, stopping is better than guessing where it ends.
            raise ProtobufError(f'unsupported wire type {wire}')
        fields.setdefault(number, []).append(value)
    return fields


def one(fields, number, default=None):
    """The last value of a field, or *default*.

    Last rather than first: protobuf's own rule for a scalar that repeats.
    """
    values = fields.get(number)
    return values[-1] if values else default


def submessage(fields, number, default=None):
    """A nested message, decoded. Absent stays absent rather than becoming {}."""
    raw = one(fields, number)
    if raw is None:
        return default
    if not isinstance(raw, bytes):
        raise ProtobufError(f'field {number} is not a message')
    return unpack(raw)
