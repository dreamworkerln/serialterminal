import asyncio
import threading
import time

import pytest

from serialterminal.session import ManagedSession
from serialterminal.transports import ble_nus
from serialterminal.transports.base import (
    ReceivedChunk,
    Transport,
    TransportWriteOutcomeUnknown,
)
from serialterminal.transports.ble_nus import BleDeviceIdentity, NUS_RX_UUID


def _wait_until(predicate, timeout=1.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def test_ble_write_timeout_reports_unknown_even_if_backend_completes_late(monkeypatch):
    class FakeDevice:
        name = "Controller"
        address = "AA:01"

    class FakeScanner:
        @staticmethod
        async def discover(timeout=3.0):
            return [FakeDevice()]

    class FakeClient:
        last = None

        def __init__(self, device, disconnected_callback=None, timeout=10.0):
            self.device = device
            self.disconnected_callback = disconnected_callback
            self.is_connected = False
            self.release_write = threading.Event()
            self.cancel_seen = threading.Event()
            self.late_completed = threading.Event()
            self.writes = []
            FakeClient.last = self

        async def connect(self):
            self.is_connected = True

        async def start_notify(self, uuid, callback):
            pass

        async def stop_notify(self, uuid):
            pass

        async def disconnect(self):
            self.is_connected = False

        async def write_gatt_char(self, uuid, data, response=False):
            try:
                while not self.release_write.is_set():
                    await asyncio.sleep(0.001)
            except asyncio.CancelledError:
                # Моделируем backend/native write, который уже вышел за точку,
                # где отмена Python Task доказывает отсутствие side effect.
                self.cancel_seen.set()
                while not self.release_write.is_set():
                    await asyncio.sleep(0.001)
                self.writes.append((uuid, bytes(data), response))
                self.late_completed.set()
                raise
            self.writes.append((uuid, bytes(data), response))

    monkeypatch.setattr(ble_nus, "BleakScanner", FakeScanner)
    monkeypatch.setattr(ble_nus, "BleakClient", FakeClient)

    transport = ble_nus.BleNusTransport(
        BleDeviceIdentity("Controller", "AA:01"),
        scan_timeout=0.01,
        connect_timeout=0.05,
        write_timeout=0.01,
    )
    try:
        assert transport.connect()
        with pytest.raises(TransportWriteOutcomeUnknown, match="outcome unknown"):
            transport.write(b"late-write")

        client = FakeClient.last
        assert client.cancel_seen.wait(timeout=0.5)
        client.release_write.set()
        assert client.late_completed.wait(timeout=0.5)
        assert client.writes == [(NUS_RX_UUID, b"late-write", False)]
    finally:
        transport.close()


class _AmbiguousOnceTransport(Transport):
    def __init__(self):
        self.connected = False
        self.writes = []
        self.connect_count = 0

    @property
    def is_connected(self):
        return self.connected

    @property
    def description(self):
        return "ambiguous-once"

    @property
    def device_key(self):
        return "ambiguous-once"

    def connect(self):
        self.connect_count += 1
        self.connected = True
        return True

    def disconnect(self):
        self.connected = False

    def read(self, size=512):
        time.sleep(0.005)
        return b""

    def read_chunk(self, size=512):
        time.sleep(0.005)
        return ReceivedChunk("main", b"")

    def write(self, data):
        self.writes.append(bytes(data))
        if len(self.writes) == 1:
            raise TransportWriteOutcomeUnknown("write outcome unknown")


def test_managed_session_does_not_retry_ambiguous_write_and_continues_after_reconnect():
    transport = _AmbiguousOnceTransport()
    session = ManagedSession(transport, reconnect_delay=0.01)
    session.start()
    try:
        assert session.wait_connected(0.5)
        first_tx = session.queue_line("first")

        assert _wait_until(
            lambda: any(
                event.kind == "tx"
                and event.tx_id == first_tx
                and event.tx_state == "unknown"
                for event in session.events_after(0)
            )
        )
        assert _wait_until(lambda: session.connected_event.is_set())

        second_tx = session.queue_line("second")
        assert _wait_until(
            lambda: any(
                event.kind == "tx"
                and event.tx_id == second_tx
                and event.tx_state == "written"
                for event in session.events_after(0)
            )
        )

        assert transport.writes == [b"first\n", b"second\n"]
        events = session.events_after(0)
        assert not any(
            event.kind == "tx"
            and event.tx_id == first_tx
            and event.tx_state == "written"
            for event in events
        )
        assert any(
            event.kind == "error"
            and event.tx_id == first_tx
            and event.state == "send-outcome-unknown"
            for event in events
        )
    finally:
        session.stop()
