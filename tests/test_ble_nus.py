import asyncio

from serialterminal.transports import ble_nus
from serialterminal.transports.ble_nus import (
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
    assert normalize_ble_target("other") is None


def test_ble_log_slug():
    assert ble_log_slug(PINGER_NAME) == "pinger"
    assert ble_log_slug(REPEATER_NAME) == "repeater"


def test_ble_transport_roundtrip(monkeypatch):
    class FakeDevice:
        name = REPEATER_NAME
        address = "AA:BB"

    class FakeScanner:
        @staticmethod
        async def discover(timeout=3.0):
            await asyncio.sleep(0.001)
            return [FakeDevice()]

    class FakeClient:
        last = None

        def __init__(self, device, disconnected_callback=None, timeout=10.0):
            self.device = device
            self.disconnected_callback = disconnected_callback
            self.is_connected = False
            self.notify = None
            self.writes = []
            FakeClient.last = self

        async def connect(self):
            self.is_connected = True

        async def start_notify(self, _uuid, callback):
            self.notify = callback

        async def write_gatt_char(self, _uuid, data, response=False):
            self.writes.append(bytes(data))

        async def disconnect(self):
            self.is_connected = False
            if self.disconnected_callback is not None:
                self.disconnected_callback(self)

    monkeypatch.setattr(ble_nus, "BleakScanner", FakeScanner)
    monkeypatch.setattr(ble_nus, "BleakClient", FakeClient)

    transport = ble_nus.BleNusTransport(
        REPEATER_NAME,
        scan_timeout=0.05,
        connect_timeout=0.05,
    )
    assert transport.connect()
    assert transport.is_connected

    FakeClient.last.notify(None, bytearray(b"FATAL test\n"))
    assert transport.read(512) == b"FATAL test\n"

    transport.write(b"LC\n")
    assert FakeClient.last.writes == [b"LC\n"]

    transport.disconnect()
    assert not transport.is_connected
