import asyncio
import time

from serialterminal.session import ManagedSession
from serialterminal.transports import ble_nus
from serialterminal.transports.ble_nus import BleDeviceIdentity, NUS_TX_UUID


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
            FakeClient.last = self

        async def connect(self):
            self.is_connected = True

        async def start_notify(self, uuid, callback):
            self.notify[uuid] = callback

        async def stop_notify(self, uuid):
            self.notify.pop(uuid, None)

        async def write_gatt_char(self, uuid, data, response=False):
            return None

        async def disconnect(self):
            was_connected = self.is_connected
            self.is_connected = False
            if was_connected and self.disconnected_callback is not None:
                self.disconnected_callback(self)

    monkeypatch.setattr(ble_nus, "BleakScanner", FakeScanner)
    monkeypatch.setattr(ble_nus, "BleakClient", FakeClient)
    return FakeDevice, FakeScanner, FakeClient


def test_notification_burst_is_byte_complete_through_managed_session(monkeypatch):
    FakeDevice, FakeScanner, FakeClient = _install_fake_ble(monkeypatch)
    selected = FakeDevice("Burst Controller", "AA:01")
    FakeScanner.devices = [selected]

    transport = ble_nus.BleNusTransport(
        BleDeviceIdentity(selected.name, selected.address),
        scan_timeout=0.05,
        connect_timeout=0.05,
        read_timeout=0.005,
    )
    session = ManagedSession(
        transport,
        reconnect_delay=0.001,
        event_limit=2048,
    )

    try:
        session.start()
        assert session.wait_connected(timeout=1.0)
        callback = FakeClient.last.notify[NUS_TX_UUID]

        fragments = [
            f"frag-{index:04d}|".encode("ascii")
            for index in range(1000)
        ]
        fragments.append(b"done\n")
        expected = b"".join(fragments)

        for fragment in fragments:
            callback(None, bytearray(fragment))

        expected_line = expected[:-1].decode("ascii")
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if any(
                line.stream == "main" and line.text == expected_line
                for line in session.lines_after(0)
            ):
                break
            time.sleep(0.01)
        else:
            raise AssertionError("BLE burst did not reach a complete logical line")

        events, lines = session.observation_after(0)
        rx_events = [
            event
            for event in events
            if event.kind == "rx" and event.stream == "main"
        ]

        assert len(rx_events) == len(fragments)
        assert b"".join(event.data or b"" for event in rx_events) == expected
        assert any(
            line.stream == "main" and line.text == expected_line
            for line in lines
        )
    finally:
        session.stop()
