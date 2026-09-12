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
import string

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
