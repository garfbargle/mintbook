"""The Bluetooth half of being discoverable.

Advertising over mDNS is not enough to be seen by an Android phone, and the
reason is a battery decision on their side rather than anything wrong here:
**Android sleeps its Nearby stack**, and a phone that is asleep does not look
at the network. A BLE advertisement carrying the Nearby service UUID is what
wakes it. rquickshare, the Rust implementation, carries one for the same
reason; its README is blunt that without Bluetooth a phone often never lists
the Linux machine at all.

    0000fe2c-0000-1000-8000-00805f9b34fb

The payload was not documented anywhere I could find, so it was **measured
instead of guessed**: with Bluetooth on, a real Quick Share device a metre
away broadcasts

    FE2C service data = 00 40 10 2a 05 00 11 5d      (8 bytes, 2026-09-12)

so this advertises the same shape — a zero version byte and seven bytes that
identify the sender — rather than a length invented here. The trailing bytes
are ours and random: they stand in for an account this machine does not have,
the same as the sixteen in the mDNS record. Copying the captured bytes
verbatim would be claiming to be that phone.

**This is the one resident thing in mintdrop, and it is deliberately
temporary.** A BLE advertisement lives as long as the D-Bus connection that
registered it, so being visible to a phone costs a process for exactly as
long as you asked for and not a second longer — the sheet holds one while it
is open, and `mintdrop visible` holds one for a couple of minutes. Nothing
advertises in the background, which is the difference between a laptop that
can be found when you want it and one that broadcasts its presence all day.
"""
import os
import random

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

# The first byte of what a real device broadcasts; the rest identifies it.
VERSION_BYTE = 0x00
PAYLOAD_BYTES = 8


def payload():
    """One advertisement's worth of service data, in the measured shape."""
    return bytes([VERSION_BYTE]) + os.urandom(PAYLOAD_BYTES - 1)


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
        return {
            'Type': dbus.String('broadcast'),
            'ServiceUUIDs': dbus.Array([dbus.String(NEARBY_UUID)],
                                       signature='s'),
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
