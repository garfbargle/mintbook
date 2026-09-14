"""A BLE L2CAP channel for a phone to connect on.

A phone connects over the medium it discovered you on. It discovers this
machine over BLE, so it opens a BLE socket — and if there is nothing to open,
it gives up without ever considering the network. That is the whole of the
"connecting… failed" the Z Fold7 showed while this machine's TCP port sat
untouched: the advertisement said `psm = 0`, meaning no L2CAP, and carried a
zeroed MAC, meaning no Bluetooth Classic, so there was nothing to connect to.

The psm field in the advertisement header exists for exactly this. Listening
on one and publishing it gives the phone somewhere to go.

Python's socket module cannot ask for this on its own: it builds `sockaddr_l2`
from `(address, psm)` and leaves `l2_bdaddr_type` at BDADDR_BREDR, which gets
a Bluetooth Classic channel rather than the LE one. So the structure is built
here and passed to bind() directly. Measured on this adapter: LE public
channels bind and listen on 0x80, 0x83 and 0xc1, and psm 0 auto-assigns.
"""
import ctypes
import os
import socket
import threading

AF_BLUETOOTH = 31
BTPROTO_L2CAP = 0
BDADDR_BREDR = 0
BDADDR_LE_PUBLIC = 1

# The LE dynamic range is 0x0080-0x00FF. Anything in it is fine; a fixed one
# keeps the advertisement stable between windows, which matters because a
# phone caches what it discovered.
DEFAULT_PSM = 0x0083

_libc = ctypes.CDLL('libc.so.6', use_errno=True)


class _sockaddr_l2(ctypes.Structure):
    _pack_ = 1
    _fields_ = [('l2_family', ctypes.c_ushort),
                ('l2_psm', ctypes.c_ushort),
                ('l2_bdaddr', ctypes.c_ubyte * 6),
                ('l2_cid', ctypes.c_ushort),
                ('l2_bdaddr_type', ctypes.c_ubyte)]


class NotAvailable(Exception):
    """No Bluetooth, or the channel could not be opened."""


class Listener:
    """Accept BLE L2CAP connections, one handler per connection.

    The socket is SOCK_SEQPACKET: L2CAP preserves message boundaries, so a
    read returns one packet rather than a slice of a stream. Anything parsing
    a byte stream on top of this has to put the boundaries back.
    """

    def __init__(self, psm=DEFAULT_PSM, on_connect=None):
        self.psm = psm
        self.on_connect = on_connect
        self.socket = None
        self.thread = None
        self.stopping = False
        self.connections = 0

    def start(self):
        sock = socket.socket(AF_BLUETOOTH, socket.SOCK_SEQPACKET, BTPROTO_L2CAP)
        address = _sockaddr_l2()
        address.l2_family = AF_BLUETOOTH
        address.l2_psm = self.psm
        address.l2_cid = 0
        address.l2_bdaddr_type = BDADDR_LE_PUBLIC
        ctypes.memset(ctypes.byref(address.l2_bdaddr), 0, 6)    # any adapter
        if _libc.bind(sock.fileno(), ctypes.byref(address),
                      ctypes.sizeof(address)) != 0:
            err = ctypes.get_errno()
            sock.close()
            raise NotAvailable(f'cannot listen on LE psm 0x{self.psm:02x}: '
                               f'{os.strerror(err)}')
        if _libc.listen(sock.fileno(), 4) != 0:
            err = ctypes.get_errno()
            sock.close()
            raise NotAvailable(f'listen failed: {os.strerror(err)}')

        # Read back what was actually assigned: psm 0 means "pick one".
        assigned = _sockaddr_l2()
        length = ctypes.c_int(ctypes.sizeof(assigned))
        _libc.getsockname(sock.fileno(), ctypes.byref(assigned),
                          ctypes.byref(length))
        self.psm = assigned.l2_psm
        self.socket = sock
        self.thread = threading.Thread(target=self._accept, daemon=True)
        self.thread.start()
        return self

    def _accept(self):
        while not self.stopping:
            try:
                connection, peer = self.socket.accept()
            except OSError:
                return
            self.connections += 1
            if self.on_connect is None:
                connection.close()
                continue
            threading.Thread(target=self._serve, args=(connection, peer),
                             daemon=True).start()

    def _serve(self, connection, peer):
        try:
            self.on_connect(connection, peer)
        except Exception:
            pass
        finally:
            try:
                connection.close()
            except OSError:
                pass

    def stop(self):
        self.stopping = True
        if self.socket is not None:
            try:
                self.socket.close()
            except OSError:
                pass
            self.socket = None
