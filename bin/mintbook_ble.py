"""The Bluetooth half of being discoverable.

Advertising over mDNS is not enough to be seen by an Android phone, and the
reason is a battery decision on their side rather than anything wrong here:
**Android sleeps its Nearby stack**, and a phone that is asleep does not look
at the network. A BLE advertisement carrying the Nearby service UUID is what
wakes it. rquickshare, the Rust implementation, carries one for the same
reason; its README is blunt that without Bluetooth a phone often never lists
the Linux machine at all.

    0000fe2c-0000-1000-8000-00805f9b34fb

The payload is a fixed 24-byte constant, not something derived from this
machine. It is the Nearby "fast initiation" advertisement, taken from
rquickshare's BleAdvertiser (`core_lib/src/hdl/blea.rs`), which is the
implementation known to make Android wake up:

    fc 12 8e 01 42 00 00 00 00 00 00 00 00 00
    bf 2d 5b a0 e1 d8 75 24 ca 00

An earlier version of this file advertised eight bytes captured off the air
instead, on the theory that they came from the phone. They did not: a leading
0x00 followed by seven bytes is a Fast Pair account-key-filter advertisement,
which is what earbuds broadcast, and 0xFE2C is the Fast Pair UUID that Nearby
borrows. Advertising those bytes did nothing at all — the phone sat in
receive mode with its mDNS dormant while we broadcast a headphone's hello.

**This is the one resident thing in mintdrop, and it is deliberately
temporary.** A BLE advertisement lives as long as the D-Bus connection that
registered it, so being visible to a phone costs a process for exactly as
long as you asked for and not a second longer — the sheet holds one while it
is open, and `mintdrop visible` holds one for a couple of minutes. Nothing
advertises in the background, which is the difference between a laptop that
can be found when you want it and one that broadcasts its presence all day.
"""
import os

import dbus
import dbus.mainloop.glib
import dbus.service

BLUEZ = 'org.bluez'
ADAPTER_PATH = '/org/bluez/hci0'
LE_MANAGER = 'org.bluez.LEAdvertisingManager1'
ADVERTISEMENT = 'org.bluez.LEAdvertisement1'
PROPERTIES = 'org.freedesktop.DBus.Properties'

NEARBY_UUID = '0000fe2c-0000-1000-8000-00805f9b34fb'
PATH = '/org/mintbook/mintdrop/advertisement0'

# Nearby "fast initiation". A constant: it says "somebody nearby wants to
# share", not who. From rquickshare's blea.rs — see the module docstring.
FAST_INITIATION = bytes([
    0xfc, 0x12, 0x8e, 0x01, 0x42, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0xbf, 0x2d, 0x5b, 0xa0, 0xe1, 0xd8, 0x75, 0x24, 0xca, 0x00,
])


def payload():
    """One advertisement's worth of service data."""
    return FAST_INITIATION


class NotAvailable(Exception):
    """No adapter, no advertising support, or Bluetooth is switched off.

    Never fatal to anything that catches it: mintdrop works between Linux
    machines with no Bluetooth at all, and a phone that cannot be woken is a
    phone that does not appear, not a broken program.
    """


class Advertisement(dbus.service.Object):
    """The object BlueZ reads our advertisement out of.

    BlueZ does not take the bytes as arguments — it takes a D-Bus object path
    and then asks that object for its properties, which is why this has to be
    exported and why the process has to stay alive to answer.
    """

    def __init__(self, bus, data=None):
        self.data = data if data is not None else payload()
        super().__init__(bus, PATH)

    @dbus.service.method(PROPERTIES, in_signature='s', out_signature='a{sv}')
    def GetAll(self, interface):
        if interface != ADVERTISEMENT:
            raise dbus.exceptions.DBusException(
                'org.freedesktop.DBus.Error.InvalidArgs')
        # Exactly these three properties, and the bytes as dbus.Byte.
        # Passing a Python bytes to dbus.Array(signature='y'), or adding
        # Discoverable/IncludeTxPower, both got 'Failed to parse
        # advertisement' out of BlueZ with nothing to say which field it
        # disliked — the shape below is the one that was measured to
        # register. A name in the packet would only cost room in an
        # advertisement with 31 bytes to spend, and the phone is being woken
        # rather than connected to.
        # Service data only, no ServiceUUIDs. A BLE advertisement is 31
        # bytes total: the service-data structure alone is 1 + 1 + 2 + 24 =
        # 28, and adding a 16-bit UUID list costs another 4 and overflows —
        # which BlueZ reports as 'Failed to register advertisement' without
        # mentioning length. rquickshare sets service data and nothing else.
        return {
            'Type': dbus.String('broadcast'),
            'ServiceData': dbus.Dictionary(
                {dbus.String(NEARBY_UUID):
                 dbus.Array([dbus.Byte(b) for b in self.data],
                            signature='y')},
                signature='sv'),
        }

    @dbus.service.method(ADVERTISEMENT, in_signature='', out_signature='')
    def Release(self):
        """BlueZ telling us it has dropped the advertisement."""


class Visibility:
    """Hold a Nearby advertisement for as long as this object is alive."""

    def __init__(self, data=None):
        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        self.bus = dbus.SystemBus()
        self.manager = None
        self.advertisement = None
        self.data = data
        self.error = None

    def start(self, on_ready=None, on_error=None):
        """Register the advertisement. **Requires a running GLib main loop.**

        RegisterAdvertisement is not a call that returns the answer: BlueZ
        takes the object path, then calls back to ask this process for the
        advertisement's properties, and only then replies. Calling it
        synchronously deadlocks against exactly that — the call blocks the
        loop that would have served the callback, and BlueZ gives up with
        'Did not receive a reply'. So it is registered asynchronously, and
        the caller keeps a loop running.
        """
        try:
            adapter = self.bus.get_object(BLUEZ, ADAPTER_PATH)
            powered = adapter.Get('org.bluez.Adapter1', 'Powered',
                                  dbus_interface=PROPERTIES)
        except dbus.DBusException as exc:
            raise NotAvailable(f'no Bluetooth adapter: {exc.get_dbus_name()}')
        if not powered:
            raise NotAvailable('Bluetooth is switched off')
        self.manager = dbus.Interface(adapter, LE_MANAGER)
        self.advertisement = Advertisement(self.bus, self.data)

        def failed(exc):
            self.error = NotAvailable(f'BlueZ refused the advertisement: '
                                      f'{exc.get_dbus_message()}')
            if on_error:
                on_error(self.error)

        self.manager.RegisterAdvertisement(
            PATH, dbus.Dictionary({}, signature='sv'),
            reply_handler=(on_ready or (lambda: None)),
            error_handler=failed)
        return self

    def stop(self):
        if self.manager is not None:
            try:
                self.manager.UnregisterAdvertisement(PATH)
            except dbus.DBusException:
                pass
            self.manager = None
        if self.advertisement is not None:
            try:
                self.advertisement.remove_from_connection()
            except Exception:
                pass
            self.advertisement = None

    def __enter__(self):
        return self.start()

    def __exit__(self, *_exc):
        self.stop()
        return False


def hold(seconds, data=None, announce=None):
    """Advertise for *seconds*, with a main loop of our own. For the CLI.

    Returns the service data actually broadcast, or raises NotAvailable.
    """
    from gi.repository import GLib
    visibility = Visibility(data)
    loop = GLib.MainLoop()
    failure = []

    def ready():
        if announce:
            announce(visibility.advertisement.data)

    def failed(error):
        failure.append(error)
        loop.quit()

    visibility.start(on_ready=ready, on_error=failed)
    GLib.timeout_add_seconds(seconds, loop.quit)
    try:
        loop.run()
    except KeyboardInterrupt:
        pass
    finally:
        visibility.stop()
    if failure:
        raise failure[0]
    return visibility.data


class BackgroundNudge:
    """Advertise from a program that has no main loop of its own.

    The CLI is the case: `mintdrop peers` wants to be advertising *while* it
    browses, because a phone whose Nearby stack is asleep never answers. But
    RegisterAdvertisement needs a running GLib loop to serve BlueZ's callback,
    and a CLI has none — so this runs one on a thread for as long as the
    block lasts.

        with BackgroundNudge():
            peers = discover()

    A machine with no Bluetooth, or no python3-dbus, gets an object that does
    nothing: mintdrop between Linux machines never needed the radio, and a
    phone that cannot be woken is a phone that does not appear, not an error.
    """

    def __init__(self, data=None):
        self.data = data
        self.visibility = None
        self.loop = None
        self.thread = None

    def __enter__(self):
        try:
            from gi.repository import GLib
        except Exception:
            return self
        try:
            self.visibility = Visibility(self.data).start(
                on_error=lambda exc: None)
        except NotAvailable:
            self.visibility = None
            return self
        self.loop = GLib.MainLoop()
        import threading
        self.thread = threading.Thread(target=self.loop.run, daemon=True)
        self.thread.start()
        # BlueZ answers on the loop; give it the moment it needs before the
        # caller starts looking for something the nudge was meant to wake.
        import time
        time.sleep(1.5)
        return self

    def __exit__(self, *_exc):
        if self.visibility is not None:
            self.visibility.stop()
        if self.loop is not None:
            self.loop.quit()
        return False


# ---------------------------------------------------------------------------
# being discovered by a phone
# ---------------------------------------------------------------------------
#
# Fast initiation (above) says "somebody here wants to send" — it is what a
# *sender* broadcasts, and the phone emits it too while it scans. It does not
# put this machine in anybody's list. To be listed, a device broadcasts a
# Nearby Connections **endpoint advertisement**, and the phone's own log is
# unambiguous about the difference:
#
#     NearbyMediums:  No BLE Fast/GATT advertisements found in the latest cycle
#     NearbySharing:  Starting Fast Init advertisement because we're currently
#                     scanning/connecting
#
# Two layers, both from google/nearby, and both verified against a Galaxy
# Z Fold7 that parsed what this builds:
#
#     connections/implementation/ble_advertisement.cc         (inner)
#     connections/implementation/mediums/ble/ble_advertisement.cc  (outer)
#
# **The service UUID is 0xFEF3, not 0xFE2C.** That one substitution is what
# turned "No BLE advertisements found" into EndpointDiscovered(MB01) — FE2C
# is Fast Pair, which Nearby borrows only for fast initiation.

NEARBY_UUID_FEF3 = '0000fef3-0000-1000-8000-00805f9b34fb'

# P2P_CLUSTER, and version 1 — the same byte that opens the mDNS instance name.
PCP_BYTE = 0x23


def endpoint_advertisement(endpoint_id, endpoint_info, version=2,
                           socket_version=2, token=None):
    """The advertisement a phone lists as a device you can send to.

        inner:  (version<<5)|pcp , endpoint_id(4) , len(info) , info
        outer:  (version<<5)|(socket<<2)|(fast<<1)|second , len , inner , token

    A Galaxy Z Fold7 decoded exactly this and reported

        BleAdvertisement { version=2, socketVersion=2, isFast=true,
                           data=[0x23 'MB01' ...] }
        EndpointDiscovered(endpointId=MB01)

    so the framing is right. What it then said was
    `EndpointParsingFailure`, because the endpoint info it was handed was a
    shortened one — see the size problem in the docstring below.
    """
    endpoint = endpoint_id.encode() if isinstance(endpoint_id, str) else endpoint_id
    if len(endpoint) != 4:
        raise ValueError('endpoint id must be 4 characters')
    inner = (bytes([PCP_BYTE]) + endpoint
             + bytes([len(endpoint_info)]) + endpoint_info)
    head = (((version << 5) & 0xE0) | ((socket_version << 2) & 0x1C) | 0x02)
    return bytes([head, len(inner)]) + inner + (token or os.urandom(2))


def advertisement_header(bloom_filter, advertisement_hash, slots=1, psm=0,
                         version=1, extended=False):
    """The 17-byte stand-in that points at a GATT server.

        (version<<5)|(extended<<4)|slots , bloom filter(10) , hash(4) , psm(2)

    Needed because a full endpoint advertisement does not fit in a legacy BLE
    packet, and this adapter is HCI 4.2 — no extended advertising, and BlueZ
    reports `SupportedSecondaryChannels` empty. The arithmetic is unforgiving:
    a 31-byte packet leaves 24 bytes of service data, the outer and inner
    headers cost 10, and a valid endpoint info is at least 18 bytes before
    the device even has a name. So a device on 4.2 has to serve the real
    advertisement over GATT and broadcast this instead.
    """
    if len(bloom_filter) != 10:
        raise ValueError('service id bloom filter must be 10 bytes')
    if len(advertisement_hash) != 4:
        raise ValueError('advertisement hash must be 4 bytes')
    head = (((version << 5) & 0xE0) | ((1 if extended else 0) << 4)
            | (slots & 0x0F))
    return (bytes([head]) + bloom_filter + advertisement_hash
            + bytes([(psm >> 8) & 0xFF, psm & 0xFF]))
