"""mintdrop's wire protocol — the half that both ends share.

AirDrop's trick is not the file transfer. It is that you never choose a
network, a folder or a password: a name appears, you click it, the file is
there. Everything below exists to keep that true on this machine, and to do
it at the speed the 5 GHz link is actually capable of.

Why this is not AirDrop, and why it can still be native
-------------------------------------------------------
Apple's AirDrop puts the *data* on AWDL, a peer-to-peer link that needs
monitor mode and frame injection. This machine's BCM4350 on brcmfmac has
neither, and no nexmon patch exists for it, so speaking real AirDrop here is
not a matter of effort — the radio cannot do it.

Quick Share, the Samsung/Google equivalent, separates the two media: BLE and
mDNS to announce and agree, then an ordinary TCP connection over the access
point both devices are already associated with. That is the shape this
follows, and it is why it works on hardware AirDrop cannot use. A Quick Share
adapter can plug into the same listener later — see the dispatch note on
MAGIC below — which is the reason discovery, the accept prompt and the
receive loop live here rather than inside one protocol's code.

The wire
--------
One TCP connection carries one transfer::

    ->  'MNTD' 0x01  u32 header length  header (JSON, UTF-8)
    <-  one byte: 0x01 accept, 0x00 decline, 0x02 busy
    ->  every file's bytes, back to back, exactly `size` each, in order
    <-  one byte: 0x01 received

Back to back with no chunk framing is the whole performance argument. The
sender can hand a file descriptor and a byte count straight to
``os.sendfile()`` and never touch the bytes; the receiver can pull the same
run out of the socket with ``os.splice()`` and never touch them either. A
per-chunk header — the obvious design — would force both ends to break the
stream at userspace and copy it twice for nothing.

The cost of that choice is that the receiver must trust the declared sizes to
find the boundary between two files. It does not: every read is bounded by
the remaining count, a short stream fails the transfer rather than running
into the next file, and nothing is renamed into place until its own byte
count has landed exactly.
"""
import errno
import fcntl
import select
import json
import os
import re
import socket
import subprocess
import unicodedata

# 'MNTD' is also the protocol dispatch. The listener reads four bytes before
# deciding anything: this is mintdrop, and a future Quick Share adapter takes
# everything that is not this, because its first frame is a protobuf length
# and can never collide.
MAGIC = b'MNTD'
VERSION = 1
PORT = 8771
SERVICE = '_mintdrop._tcp'

# The header is small by construction — names and sizes. The cap is here so a
# hostile or broken peer cannot make the receiver allocate before the prompt.
MAX_HEADER = 64 * 1024
MAX_FILES = 512

ACCEPT, DECLINE, BUSY = b'\x01', b'\x00', b'\x02'

# 1 MiB of pipe for the splice path. The default pipe is 64 KiB, which at
# link speed is a round trip through the scheduler every millisecond; a
# megabyte lets the socket drain in a few large moves instead of sixteen.
PIPE_BYTES = 1 << 20
CHUNK = 1 << 20

HOME = os.path.expanduser('~')
CONFIG = f'{HOME}/.config/mintbook/mintdrop.conf'
STATE = f'{HOME}/.local/state/mintbook'


# ---------------------------------------------------------------------------
# identity
# ---------------------------------------------------------------------------

def device_name():
    """What the other end calls this machine.

    The pretty hostname if one is set, because 'cobo-MacBook' is a DNS label
    and "Cobo's MacBook" is a name. Falls back to the static hostname with the
    -MacBook suffix left alone: it is accurate here.
    """
    try:
        with open('/etc/machine-info') as f:
            for line in f:
                if line.startswith('PRETTY_HOSTNAME='):
                    name = line.split('=', 1)[1].strip().strip('"')
                    if name:
                        return name
    except OSError:
        pass
    return socket.gethostname().split('.')[0]


def config():
    """User settings. Absent file means defaults — a missing config must never
    stop a transfer, the same rule bin/palette-generate follows for popups."""
    values = {'accept': 'ask', 'dir': '', 'name': ''}
    try:
        with open(CONFIG) as f:
            for line in f:
                line = line.split('#', 1)[0].strip()
                if '=' in line:
                    key, _, value = line.partition('=')
                    key = key.strip()
                    if key in values:
                        values[key] = value.strip()
    except OSError:
        pass
    return values


def download_dir():
    """Where received files land. XDG's Downloads, as any other download."""
    configured = config()['dir']
    if configured:
        return os.path.expanduser(configured)
    try:
        out = subprocess.run(['xdg-user-dir', 'DOWNLOAD'], text=True,
                             capture_output=True, timeout=3)
        path = out.stdout.strip()
        if path and path != HOME:
            return path
    except (OSError, subprocess.SubprocessError):
        pass
    return os.path.join(HOME, 'Downloads')


# ---------------------------------------------------------------------------
# names arriving from the network
# ---------------------------------------------------------------------------

_UNSAFE = re.compile(r'[\x00-\x1f\x7f/\\]')


def safe_name(name):
    """A basename that cannot escape the download directory.

    Everything here is defence against the sender, not tidying. Path
    separators and control characters go; '..' and '' become a name rather
    than a traversal; a leading dot would hide the file from the person who
    just accepted it, so it loses the dot. NFC because a name that looks
    identical to an existing one should collide with it and get a suffix,
    rather than sitting beside it indistinguishable.
    """
    name = unicodedata.normalize('NFC', str(name))
    name = _UNSAFE.sub('_', name).strip()
    name = name.lstrip('.') or 'received'
    return name[:200]


def unique_path(directory, name):
    """`report.pdf`, then `report (2).pdf`. Never overwrites: the sender does
    not get to replace a file on this machine by naming it."""
    stem, dot, ext = name.rpartition('.')
    if not dot:
        stem, ext = name, ''
    candidate = os.path.join(directory, name)
    n = 2
    while os.path.lexists(candidate):
        suffix = f' ({n})'
        candidate = os.path.join(directory, f'{stem}{suffix}{dot}{ext}')
        n += 1
    return candidate


# ---------------------------------------------------------------------------
# framing
# ---------------------------------------------------------------------------

class DropError(Exception):
    """A transfer that cannot continue. The message is shown to the user."""


def read_exactly(sock, count):
    parts = []
    got = 0
    while got < count:
        chunk = sock.recv(count - got)
        if not chunk:
            raise DropError('the connection closed early')
        parts.append(chunk)
        got += len(chunk)
    return b''.join(parts)


def write_header(sock, header):
    blob = json.dumps(header, separators=(',', ':')).encode()
    if len(blob) > MAX_HEADER:
        raise DropError('too many files in one transfer')
    sock.sendall(MAGIC + bytes([VERSION]) + len(blob).to_bytes(4, 'big') + blob)


def read_header(sock):
    """Parse and *validate* the offer. Returns (name, files, total).

    Validation is the point: after this returns, the byte counts are known to
    be sane integers and the names are known to be basenames, so the receive
    loop below can be a tight loop with no checking in it.
    """
    prefix = read_exactly(sock, 9)
    if prefix[:4] != MAGIC:
        raise DropError('not a mintdrop sender')
    if prefix[4] != VERSION:
        raise DropError(f'unsupported mintdrop version {prefix[4]}')
    length = int.from_bytes(prefix[5:9], 'big')
    if not 0 < length <= MAX_HEADER:
        raise DropError('bad header length')
    try:
        header = json.loads(read_exactly(sock, length))
        entries = header['files']
    except (ValueError, KeyError, TypeError) as exc:
        raise DropError('malformed offer') from exc
    if not isinstance(entries, list) or not 0 < len(entries) <= MAX_FILES:
        raise DropError('malformed offer')
    files = []
    total = 0
    for entry in entries:
        try:
            size = int(entry['size'])
            name = safe_name(entry['name'])
        except (KeyError, TypeError, ValueError) as exc:
            raise DropError('malformed offer') from exc
        if size < 0 or size > (1 << 45):
            raise DropError('implausible file size')
        files.append({'name': name, 'size': size})
        total += size
    name = str(header.get('name', ''))[:64] or 'Unknown device'
    return name, files, total


# ---------------------------------------------------------------------------
# the two zero-copy halves
# ---------------------------------------------------------------------------

def send_file(sock, path, size, progress=None):
    """File -> socket without the bytes entering this process.

    ``os.sendfile()`` is the whole send path: the page cache pages are handed
    to the socket inside the kernel, so a gigabyte costs no user-space memory
    traffic and no Python bytecode per byte. The loop exists only because
    sendfile returns short on a socket that has filled up.
    """
    sent = 0
    with open(path, 'rb') as f:
        fd = f.fileno()
        while sent < size:
            try:
                moved = os.sendfile(sock.fileno(), fd, sent, min(CHUNK, size - sent))
            except BlockingIOError:
                continue
            except BrokenPipeError as exc:
                raise DropError('the other end went away') from exc
            if moved == 0:
                raise DropError(f'{os.path.basename(path)} ended early '
                                f'({sent} of {size} bytes)')
            sent += moved
            if progress:
                progress(moved)
    return sent


class Splicer:
    """Socket -> file without the bytes entering this process.

    The kernel cannot splice a socket straight into a file: splice needs a
    pipe on one side, so this keeps one and moves each run twice through it.
    Both moves are page-reference handoffs rather than copies, so the second
    one is close to free and the whole path stays out of user space.

    Held as an object because the pipe and its enlarged capacity are worth
    setting up once per transfer, not once per file.
    """

    def __init__(self):
        self.read_fd, self.write_fd = os.pipe()
        try:
            fcntl.fcntl(self.write_fd, fcntl.F_SETPIPE_SZ, PIPE_BYTES)
            self.capacity = fcntl.fcntl(self.write_fd, fcntl.F_GETPIPE_SZ)
        except (OSError, AttributeError):
            # A locked-down pipe-max-size only costs throughput, never
            # correctness: fall back to whatever the pipe already holds.
            self.capacity = 65536

    def close(self):
        for fd in (self.read_fd, self.write_fd):
            try:
                os.close(fd)
            except OSError:
                pass

    def recv_to(self, sock, out_fd, size, progress=None, stall=90):
        """Move exactly `size` bytes from the socket into the file.

        The socket must be *blocking*, and the poll() is how the stall timeout
        is kept anyway. This is the trap that cost the first working version:
        socket.settimeout() does not set a timeout, it sets O_NONBLOCK and
        emulates one in Python — and splice() on a non-blocking socket returns
        EAGAIN on the spot rather than waiting, so every transfer died at byte
        zero with 'Resource temporarily unavailable'. poll() gives the same
        deadline without taking the descriptor out of blocking mode.
        """
        sock.setblocking(True)
        sock_fd = sock.fileno()
        poller = select.poll()
        poller.register(sock_fd, select.POLLIN)
        left = size
        while left:
            if not poller.poll(stall * 1000):
                raise DropError(f'the sender stopped responding '
                                f'({human(left)} short)')
            try:
                pulled = os.splice(sock_fd, self.write_fd,
                                   min(self.capacity, left))
            except OSError as exc:
                if exc.errno in (errno.EINTR, errno.EAGAIN):
                    continue
                raise DropError(f'receive failed: {exc.strerror}') from exc
            if pulled == 0:
                raise DropError(f'sender stopped {left} bytes early')
            # Drain the pipe fully before pulling again: splice into a full
            # pipe blocks, and a partial push here would deadlock the next
            # iteration against a socket that still has data.
            pushed = 0
            while pushed < pulled:
                try:
                    pushed += os.splice(self.read_fd, out_fd, pulled - pushed)
                except OSError as exc:
                    if exc.errno == errno.EINTR:
                        continue
                    raise DropError(f'write failed: {exc.strerror}') from exc
            left -= pulled
            if progress:
                progress(pulled)
        return size


def recv_to_plain(sock, out_fd, size, progress=None):
    """The same move with a buffer in this process.

    Kept, and kept honest, because 'zero-copy is faster' is a claim and this
    repo measures claims. bin/mintdrop-probe runs both paths over the same
    connection; docs/mintdrop.md carries the number. It is also the fallback
    if splice ever refuses a socket it does not like.
    """
    view = memoryview(bytearray(CHUNK))
    left = size
    while left:
        got = sock.recv_into(view, min(CHUNK, left))
        if got == 0:
            raise DropError(f'sender stopped {left} bytes early')
        written = 0
        while written < got:
            written += os.write(out_fd, view[written:got])
        left -= got
        if progress:
            progress(got)
    return size


def allocate(fd, size):
    """Ask for the space up front.

    One extent instead of a few thousand, and — the reason it is here — the
    transfer fails now rather than after twenty minutes if the disk cannot
    hold the file. ENOSPC from fallocate is a clean decline; ENOSPC at 90%
    is a wasted transfer.
    """
    if size <= 0:
        return
    try:
        os.posix_fallocate(fd, 0, size)
    except OSError as exc:
        if exc.errno in (errno.ENOSPC, errno.EDQUOT):
            raise DropError('not enough free space for this transfer') from exc
        # Filesystems that cannot preallocate (some FUSE mounts) say EOPNOTSUPP
        # or EINVAL. Nothing is wrong; the file just grows as it is written.


# ---------------------------------------------------------------------------
# who is out there
# ---------------------------------------------------------------------------

def unmap(ip):
    """::ffff:192.168.1.5 -> 192.168.1.5.

    The receiver binds one dual-stack socket, so every IPv4 peer arrives
    wearing an IPv6 address. Unwrapping here rather than at each call site is
    what keeps `is_local_address` from having to know about it — it is the
    same address, and the first version of this rejected the whole v4 internet
    by treating the mapped form as a routable v6 one.
    """
    if ip.startswith('::ffff:') and '.' in ip:
        return ip[7:]
    return ip


def is_local_address(ip):
    """Private, link-local or loopback only.

    A listener that will prompt for anything routable is a doorbell anyone on
    the internet can ring. Nearby means nearby.
    """
    ip = unmap(ip)
    try:
        packed = socket.inet_pton(socket.AF_INET, ip)
    except OSError:
        try:
            packed = socket.inet_pton(socket.AF_INET6, ip.split('%')[0])
        except OSError:
            return False
        if packed == b'\0' * 15 + b'\x01':          # ::1
            return True
        if packed[0] == 0xfe and packed[1] & 0xc0 == 0x80:   # fe80::/10
            return True
        if packed[0] & 0xfe == 0xfc:                # fc00::/7 unique local
            return True
        return False
    a, b = packed[0], packed[1]
    return (a == 10 or a == 127 or (a == 192 and b == 168)
            or (a == 172 and 16 <= b <= 31) or (a == 169 and b == 254))


def local_addresses():
    """This machine's own addresses, so it does not offer to send to itself.

    avahi answers our own advertisement along with everyone else's, and a
    picker whose only entry is this laptop is a picker that looks broken. The
    UDP connect never sends a packet; it just asks the routing table which
    source address would be used to reach the LAN.
    """
    found = {'127.0.0.1', '::1'}
    for family, probe in ((socket.AF_INET, ('192.168.1.1', 9)),
                          (socket.AF_INET6, ('fd00::1', 9))):
        try:
            sock = socket.socket(family, socket.SOCK_DGRAM)
            try:
                sock.connect(probe)
                found.add(sock.getsockname()[0].split('%')[0])
            finally:
                sock.close()
        except OSError:
            pass
    return found


def discover(timeout=1.2):
    """Peers advertising _mintdrop._tcp, from the avahi-daemon already running.

    Browsed only while the picker is open — rule 3 in CONTRIBUTING. There is
    no resident discovery process on either side of this feature: the receiver
    advertises through a static service file avahi already publishes, and this
    asks avahi only when a human is looking at a list.
    """
    argv = ['avahi-browse', '--resolve', '--terminate', '--parsable',
            '--no-db-lookup', SERVICE]
    try:
        out = subprocess.run(argv, text=True, capture_output=True,
                             timeout=max(timeout, 1) + 4)
    except (OSError, subprocess.SubprocessError):
        return []
    mine = device_name()
    ours = local_addresses()
    peers = {}
    for line in out.stdout.splitlines():
        # =;wlp1s0;IPv4;name;_mintdrop._tcp;local;host;address;port;txt
        parts = line.split(';')
        if len(parts) < 9 or parts[0] != '=':
            continue
        name = parts[3].replace('\\032', ' ').replace('\\.', '.')
        address, port = parts[7], parts[8]
        if not is_local_address(address):
            continue
        if name == mine or unmap(address).split('%')[0] in ours:
            continue
        try:
            port = int(port)
        except ValueError:
            continue
        # One row per device: a machine on both IPv4 and IPv6 is one machine,
        # and IPv6 first because that is the link the AP will route directly.
        current = peers.get(name)
        if current is None or (parts[2] == 'IPv6' and current['family'] == 'IPv4'):
            peers[name] = {'name': name, 'address': address, 'port': port,
                           'family': parts[2], 'interface': parts[1]}
    return sorted(peers.values(), key=lambda p: p['name'].lower())


def connect(address, port, timeout=8):
    """A connection with Nagle off and the address family the peer gave us."""
    family = socket.AF_INET6 if ':' in address else socket.AF_INET
    sock = socket.socket(family, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    if family is socket.AF_INET6 and address.startswith('fe80'):
        # A link-local peer needs the scope, and avahi hands the interface back
        # in its own column rather than in the address.
        info = socket.getaddrinfo(address, port, family, socket.SOCK_STREAM)
        sock.connect(info[0][4])
    else:
        sock.connect((address, port))
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    return sock


def human(size):
    for unit, scale in (('GB', 1 << 30), ('MB', 1 << 20), ('kB', 1 << 10)):
        if size >= scale:
            return f'{size / scale:.1f} {unit}'.replace('.0 ', ' ')
    return f'{size} bytes'
