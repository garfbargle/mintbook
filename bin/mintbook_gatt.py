"""Being listed on a phone: a GATT server, and the header that points at it.

A phone looking for somewhere to send does not read mDNS and does not care
about fast initiation. It scans BLE for a Nearby Connections advertisement,
and if the advertisement is only a *header* it connects and reads the real
one over GATT. This is that server.

Why the indirection is not optional here. A legacy BLE packet leaves 24
bytes of service data; the outer and inner advertisement headers cost 10;
and the smallest valid endpoint info is 18 bytes before the device has a
name. This adapter is HCI 4.2 and BlueZ reports `SupportedSecondaryChannels`
empty, so there is no extended advertising to escape into — the full
advertisement physically cannot be broadcast and has to be fetched.

Everything here was settled against a Galaxy Z Fold7 with `adb logcat`
watching, because every wrong guess in this area fails as silence:

    NearbySharing: DiscoveryController reported Discovered(endpointId=MB01,
        metadata=DeviceMetadata(deviceType=3, deviceName=Mintbook1, ...))
    mintdrop:      GATT READ of 00000000-0000-3000-8000-000000000000

Three things had to be right at once, and each was wrong first:

  * **0xFEF3**, not 0xFE2C. Nearby Connections advertises under FEF3; FE2C
    is Fast Pair, which Nearby borrows only for fast initiation — the
    *sender's* beacon, which a phone emits itself while scanning.
  * **Header version 2, with the psm field.** Version 1 with the same
    fifteen bytes is never picked up. The header is 17 bytes.
  * **Service data only.** Adding ServiceUUIDs alongside it costs four more
    bytes and the phone stops seeing it.
"""
import hashlib
import importlib.machinery
import importlib.util
import os

import dbus
import dbus.mainloop.glib
import dbus.service

BLUEZ = 'org.bluez'
ADAPTER = '/org/bluez/hci0'
GATT_MANAGER = 'org.bluez.GattManager1'
LE_MANAGER = 'org.bluez.LEAdvertisingManager1'
PROPERTIES = 'org.freedesktop.DBus.Properties'

# bleutils::kCopresenceServiceUuid
COPRESENCE = '0000fef3-0000-1000-8000-00805f9b34fb'
# bleutils::GenerateAdvertisementUuid(slot) — msb 0x3000, lsb 0x8000... | slot
SLOT_UUID = '00000000-0000-3000-8000-0000000000%02x'

APP_PATH = '/org/mintbook/nearby'
ADVERT_PATH = '/org/mintbook/nearby/advert0'

SERVICE_ID = 'NearbySharing'
SERVICE_ID_HASH = hashlib.sha256(SERVICE_ID.encode()).digest()[:3]

HEADER_VERSION = 2
ADVERTISEMENT_VERSION = 2
SOCKET_VERSION = 2
PCP_BYTE = 0x23


def _load(name):
    loader = importlib.machinery.SourceFileLoader(
        name, os.path.join(os.path.dirname(os.path.realpath(__file__)),
                           name + '.py'))
    module = importlib.util.module_from_spec(
        importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(module)
    return module


bloom = _load('mintbook_bloom')


class NotAvailable(Exception):
    """No adapter, no GATT manager, or Bluetooth is off."""


def endpoint_advertisement(endpoint_id, endpoint_info, token=None):
    """The advertisement served over GATT — the regular, unsqueezed form.

        inner   (version<<5)|pcp , service id hash(3) , endpoint_id(4) ,
                len(info) , info , bluetooth mac(6)
        outer   (version<<5)|(socket<<2) , service id hash(3) ,
                len(inner) as u32 , inner , device token(2)

    The MAC is left zero: this machine is reachable over the LAN and the
    phone is told so during the connection, not here.
    """
    endpoint = endpoint_id.encode() if isinstance(endpoint_id, str) else endpoint_id
    if len(endpoint) != 4:
        raise ValueError('endpoint id must be 4 characters')
    inner = (bytes([PCP_BYTE]) + SERVICE_ID_HASH + endpoint
             + bytes([len(endpoint_info)]) + endpoint_info + b'\x00' * 6)
    head = ((ADVERTISEMENT_VERSION << 5) & 0xE0) | ((SOCKET_VERSION << 2) & 0x1C)
    return (bytes([head]) + SERVICE_ID_HASH + len(inner).to_bytes(4, 'big')
            + inner + (token or os.urandom(2)))


def advertisement_header(advertisement, slots=1, psm=0):
    """The 17 bytes actually broadcast.

        (version<<5)|(extended<<4)|slots , bloom filter(10) , hash(4) , psm(2)

    The filter carries a random dummy service id before the real one, and
    the hash chains from the dummy's hash through each advertisement body —
    ble.cc does both, and a phone that cannot match the filter never bothers
    to connect.
    """
    dummy = os.urandom(128)
    filter_bytes = bytes(bloom.BloomFilter().add(dummy).add(SERVICE_ID))
    digest = hashlib.sha256(dummy).digest()[:4]
    digest = hashlib.sha256(digest + advertisement).digest()[:4]
    head = ((HEADER_VERSION << 5) & 0xE0) | (slots & 0x0F)
    return (bytes([head]) + filter_bytes + digest
            + bytes([(psm >> 8) & 0xFF, psm & 0xFF]))


class _Characteristic(dbus.service.Object):
    """One advertisement slot, readable by anything that connects."""

    def __init__(self, bus, path, service_path, uuid, value):
        self.path = path
        self.service_path = service_path
        self.uuid = uuid
        self.value = value
        self.reads = 0
        super().__init__(bus, path)

    def properties(self):
        return {'UUID': self.uuid,
                'Service': dbus.ObjectPath(self.service_path),
                'Flags': dbus.Array(['read'], signature='s')}

    @dbus.service.method(PROPERTIES, in_signature='s', out_signature='a{sv}')
    def GetAll(self, interface):
        return self.properties()

    @dbus.service.method('org.bluez.GattCharacteristic1',
                         in_signature='a{sv}', out_signature='ay')
    def ReadValue(self, options):
        self.reads += 1
        return dbus.Array([dbus.Byte(b) for b in self.value], signature='y')


class _Service(dbus.service.Object):
    def __init__(self, bus, path, uuid):
        self.path = path
        self.uuid = uuid
        super().__init__(bus, path)

    @dbus.service.method(PROPERTIES, in_signature='s', out_signature='a{sv}')
    def GetAll(self, interface):
        return {'UUID': self.uuid, 'Primary': dbus.Boolean(True)}


class _Application(dbus.service.Object):
    def __init__(self, bus, path, advertisement):
        super().__init__(bus, path)
        self.service = _Service(bus, path + '/service0', COPRESENCE)
        self.characteristic = _Characteristic(
            bus, path + '/service0/char0', path + '/service0',
            SLOT_UUID % 0, advertisement)

    @dbus.service.method('org.freedesktop.DBus.ObjectManager',
                         out_signature='a{oa{sa{sv}}}')
    def GetManagedObjects(self):
        return {
            dbus.ObjectPath(self.service.path):
                {'org.bluez.GattService1': self.service.GetAll('')},
            dbus.ObjectPath(self.characteristic.path):
                {'org.bluez.GattCharacteristic1':
                 self.characteristic.properties()},
        }


class _Advert(dbus.service.Object):
    def __init__(self, bus, path, header):
        self.header = header
        super().__init__(bus, path)

    @dbus.service.method(PROPERTIES, in_signature='s', out_signature='a{sv}')
    def GetAll(self, interface):
        # Connectable, because the phone has to be able to read the GATT
        # characteristic. Service data and nothing else: a ServiceUUIDs list
        # costs four more bytes and the phone stops seeing the advert.
        return {'Type': dbus.String('peripheral'),
                'ServiceData': dbus.Dictionary(
                    {dbus.String(COPRESENCE):
                     dbus.Array([dbus.Byte(b) for b in self.header],
                                signature='y')}, signature='sv')}

    @dbus.service.method('org.bluez.LEAdvertisement1', in_signature='',
                         out_signature='')
    def Release(self):
        pass


class Listed:
    """Be a device a phone can pick. Requires a running GLib main loop."""

    def __init__(self, endpoint_id, endpoint_info):
        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        self.bus = dbus.SystemBus()
        self.advertisement = endpoint_advertisement(endpoint_id, endpoint_info)
        self.header = advertisement_header(self.advertisement)
        self.application = None
        self.advert = None
        self.gatt = None
        self.le = None
        self.error = None

    @property
    def reads(self):
        """How many times a phone has fetched the advertisement."""
        return self.application.characteristic.reads if self.application else 0

    def start(self, on_ready=None, on_error=None):
        try:
            adapter = self.bus.get_object(BLUEZ, ADAPTER)
            powered = adapter.Get('org.bluez.Adapter1', 'Powered',
                                  dbus_interface=PROPERTIES)
        except dbus.DBusException as exc:
            raise NotAvailable(f'no Bluetooth adapter: {exc.get_dbus_name()}')
        if not powered:
            raise NotAvailable('Bluetooth is switched off')

        self.application = _Application(self.bus, APP_PATH, self.advertisement)
        self.advert = _Advert(self.bus, ADVERT_PATH, self.header)
        self.gatt = dbus.Interface(adapter, GATT_MANAGER)
        self.le = dbus.Interface(adapter, LE_MANAGER)

        def failed(exc):
            self.error = NotAvailable(exc.get_dbus_message())
            if on_error:
                on_error(self.error)

        def registered():
            self.le.RegisterAdvertisement(
                ADVERT_PATH, dbus.Dictionary({}, signature='sv'),
                reply_handler=(on_ready or (lambda: None)),
                error_handler=failed)

        self.gatt.RegisterApplication(
            APP_PATH, dbus.Dictionary({}, signature='sv'),
            reply_handler=registered, error_handler=failed)
        return self

    def stop(self):
        for unregister, path in ((getattr(self.le, 'UnregisterAdvertisement', None),
                                  ADVERT_PATH),
                                 (getattr(self.gatt, 'UnregisterApplication', None),
                                  APP_PATH)):
            if unregister is None:
                continue
            try:
                unregister(path)
            except dbus.DBusException:
                pass
        for obj in (self.advert, self.application):
            try:
                if obj is not None:
                    obj.remove_from_connection()
            except Exception:
                pass
        self.advert = self.application = None
