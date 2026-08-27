import asyncio

from serialterminal.transports import ble_nus
from serialterminal.transports.ble_nus import (
    BleDeviceIdentity,
    NUS_CHAT_TX_UUID,
    NUS_TELEMETRY_TX_UUID,
    PINGER_NAME,
    REPEATER_NAME,
    ble_log_slug,
    normalize_ble_target,
)


def test_normalize_ble_target():
    assert normalize_ble_target("p") == PINGER_NAME
    assert normalize_ble_target("PINGER") == PINGER_NAME
    assert normalize_ble_target("r") == REPEATER_NAME
    assert normalize_ble_target("repeater") == REPEATER_NAME
    assert normalize_ble_target("LoRa-Chatter-72E0") == "LoRa-Chatter-72E0"
    assert normalize_ble_target("other") is None


def test_ble_log_slug():
    assert ble_log_slug(PINGER_NAME) == "pinger"
    assert ble_log_slug("LoRa-Chatter-72E0") == "chatter-72e0"


def _install_fake_ble(monkeypatch):
    class FakeDevice:
        def __init__(self, name, address):
            self.name = name
            self.address = address

    class FakeScanner:
        devices = []

        @staticmethod
        async def discover(timeout=3.0):
            await asyncio.sleep(0.001)
            return list(FakeScanner.devices)

    class FakeClient:
        last = None

        def __init__(self, device, disconnected_callback=None, timeout=10.0):
            self.device = device
            self.disconnected_callback = disconnected_callback
            self.is_connected = False
            self.notify = {}
            self.writes = []
            FakeClient.last = self

        async def connect(self):
            self.is_connected = True

        async def start_notify(self, uuid, callback):
            self.notify[uuid] = callback

        async def write_gatt_char(self, _uuid, data, response=False):
            self.writes.append(bytes(data))

        async def disconnect(self):
            self.is_connected = False
            if self.disconnected_callback is not None:
                self.disconnected_callback(self)

    monkeypatch.setattr(ble_nus, "BleakScanner", FakeScanner)
    monkeypatch.setattr(ble_nus, "BleakClient", FakeClient)
    return FakeDevice, FakeScanner, FakeClient


def test_discovery_preserves_multiple_same_name(monkeypatch):
    FakeDevice, FakeScanner, _ = _install_fake_ble(monkeypatch)
    FakeScanner.devices = [
        FakeDevice("LoRa-Chatter-72E0", "AA:01"),
        FakeDevice("LoRa-Chatter-72E0", "AA:02"),
        FakeDevice("unrelated", "AA:03"),
    ]

    found = ble_nus.discover_nus_devices(0.01)
    assert [(item.name, item.address) for item in found] == [
        ("LoRa-Chatter-72E0", "AA:01"),
        ("LoRa-Chatter-72E0", "AA:02"),
    ]


def test_ble_transport_streams_and_sticky_reconnect(monkeypatch):
    FakeDevice, FakeScanner, FakeClient = _install_fake_ble(monkeypatch)
    selected = FakeDevice("LoRa-Chatter-72E0", "AA:01")
    other = FakeDevice("LoRa-Chatter-A193", "AA:02")
    FakeScanner.devices = [selected, other]

    transport = ble_nus.BleNusTransport(
        BleDeviceIdentity(selected.name, selected.address),
        scan_timeout=0.05,
        connect_timeout=0.05,
    )
    try:
        assert transport.connect()
        assert transport.is_connected
        assert FakeClient.last.device.address == "AA:01"
        assert transport.telemetry_available

        FakeClient.last.notify[NUS_CHAT_TX_UUID](None, bytearray(b"chat\n"))
        FakeClient.last.notify[NUS_TELEMETRY_TX_UUID](
            None,
            bytearray(b"telemetry\n"),
        )
        assert transport.read_chunk(512).stream == "chat"
        second = transport.read_chunk(512)
        assert second.stream == "telemetry"
        assert second.data == b"telemetry\n"

        transport.write(b"hello\n")
        assert FakeClient.last.writes == [b"hello\n"]

        transport.disconnect()
        assert not transport.is_connected

        # Only another LoRa device is visible: sticky reconnect must refuse it.
        FakeScanner.devices = [other]
        assert not transport.connect()

        # The selected physical address comes back: reconnect succeeds.
        FakeScanner.devices = [selected, other]
        assert transport.connect()
        assert FakeClient.last.device.address == "AA:01"
    finally:
        transport.close()
