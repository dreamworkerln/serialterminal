import asyncio

from serialterminal.transports import ble_nus
from serialterminal.transports.ble_nus import (
    BleDeviceIdentity,
    BleReceiveStream,
    NUS_RX_UUID,
    NUS_TX_UUID,
    PINGER_NAME,
    REPEATER_NAME,
    ble_log_slug,
    normalize_ble_target,
)

SECONDARY_TX_UUID = "12345678-1234-5678-1234-56789abcdef0"


def test_normalize_ble_target():
    assert normalize_ble_target("p") == PINGER_NAME
    assert normalize_ble_target("PINGER") == PINGER_NAME
    assert normalize_ble_target("r") == REPEATER_NAME
    assert normalize_ble_target("repeater") == REPEATER_NAME
    assert normalize_ble_target("LoRa-Chatter-72E0") == "LoRa-Chatter-72E0"
    assert normalize_ble_target("other") is None


def test_ble_log_slug_is_generic():
    assert ble_log_slug(PINGER_NAME) == "lora-pinger"
    assert ble_log_slug("LoRa-Chatter-72E0") == "lora-chatter-72e0"
    assert ble_log_slug("Plain Controller") == "plain-controller"


def test_transport_module_owns_only_standard_nus_characteristics():
    assert not hasattr(ble_nus, "NUS_CHAT_TX_UUID")
    assert not hasattr(ble_nus, "NUS_TELEMETRY_TX_UUID")


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
        instances = []
        fail_notify_uuids = set()

        def __init__(self, device, disconnected_callback=None, timeout=10.0):
            self.device = device
            self.disconnected_callback = disconnected_callback
            self.is_connected = False
            self.notify = {}
            self.stop_calls = []
            self.writes = []
            FakeClient.last = self
            FakeClient.instances.append(self)

        async def connect(self):
            self.is_connected = True

        async def start_notify(self, uuid, callback):
            if uuid in FakeClient.fail_notify_uuids:
                raise RuntimeError(f"notify unavailable: {uuid}")
            self.notify[uuid] = callback

        async def stop_notify(self, uuid):
            self.stop_calls.append(uuid)
            self.notify.pop(uuid, None)

        async def write_gatt_char(self, uuid, data, response=False):
            self.writes.append((uuid, bytes(data), response))

        async def disconnect(self):
            was_connected = self.is_connected
            self.is_connected = False
            if was_connected and self.disconnected_callback is not None:
                self.disconnected_callback(self)

        def remote_disconnect(self):
            self.is_connected = False
            if self.disconnected_callback is not None:
                self.disconnected_callback(self)

    monkeypatch.setattr(ble_nus, "BleakScanner", FakeScanner)
    monkeypatch.setattr(ble_nus, "BleakClient", FakeClient)
    return FakeDevice, FakeScanner, FakeClient


def _multi_stream_transport(identity, *, scan_timeout=0.05, connect_timeout=0.05):
    return ble_nus.BleNusTransport(
        identity,
        scan_timeout=scan_timeout,
        connect_timeout=connect_timeout,
        receive_streams=(
            BleReceiveStream(NUS_TX_UUID, "primary"),
            BleReceiveStream(
                SECONDARY_TX_UUID,
                "secondary",
                required=False,
            ),
        ),
    )


def test_name_only_transport_uses_exact_arbitrary_advertised_name(monkeypatch):
    _install_fake_ble(monkeypatch)
    transport = ble_nus.BleNusTransport("Plain Controller")
    try:
        assert transport.target_name == "Plain Controller"
        assert transport.target_address is None
        assert transport.device_key == "ble-name:plain controller"
    finally:
        transport.close()


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


def test_ble_transport_defaults_to_standard_nus_main_stream(monkeypatch):
    FakeDevice, FakeScanner, FakeClient = _install_fake_ble(monkeypatch)
    selected = FakeDevice("Controller", "AA:01")
    FakeScanner.devices = [selected]

    transport = ble_nus.BleNusTransport(
        BleDeviceIdentity(selected.name, selected.address),
        scan_timeout=0.05,
        connect_timeout=0.05,
    )
    try:
        assert transport.stream_capabilities == ("main",)
        assert transport.connect()
        assert transport.available_streams == ("main",)
        assert set(FakeClient.last.notify) == {NUS_TX_UUID}

        FakeClient.last.notify[NUS_TX_UUID](None, bytearray(b"ready\n"))
        chunk = transport.read_chunk(512)
        assert (chunk.stream, chunk.data) == ("main", b"ready\n")

        transport.write(b"hello\n")
        assert FakeClient.last.writes == [
            (NUS_RX_UUID, b"hello\n", False),
        ]
    finally:
        transport.close()


def test_ble_transport_streams_and_sticky_reconnect(monkeypatch):
    FakeDevice, FakeScanner, FakeClient = _install_fake_ble(monkeypatch)
    selected = FakeDevice("LoRa-Chatter-72E0", "AA:01")
    other = FakeDevice("LoRa-Chatter-A193", "AA:02")
    FakeScanner.devices = [selected, other]

    transport = _multi_stream_transport(
        BleDeviceIdentity(selected.name, selected.address),
    )
    try:
        assert transport.connect()
        assert transport.is_connected
        assert FakeClient.last.device.address == "AA:01"
        assert transport.stream_capabilities == ("primary", "secondary")
        assert transport.available_streams == ("primary", "secondary")

        FakeClient.last.notify[NUS_TX_UUID](None, bytearray(b"primary\n"))
        FakeClient.last.notify[SECONDARY_TX_UUID](
            None,
            bytearray(b"secondary\n"),
        )
        assert transport.read_chunk(512).stream == "primary"
        second = transport.read_chunk(512)
        assert second.stream == "secondary"
        assert second.data == b"secondary\n"

        transport.write(b"hello\n")
        assert FakeClient.last.writes == [
            (NUS_RX_UUID, b"hello\n", False),
        ]

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


def test_ble_connect_keeps_required_stream_when_optional_notify_is_missing(
    monkeypatch,
):
    FakeDevice, FakeScanner, FakeClient = _install_fake_ble(monkeypatch)
    selected = FakeDevice("LoRa-Echo", "AA:01")
    FakeScanner.devices = [selected]
    FakeClient.fail_notify_uuids = {SECONDARY_TX_UUID}

    transport = _multi_stream_transport(
        BleDeviceIdentity(selected.name, selected.address),
    )
    try:
        assert transport.connect()
        assert transport.is_connected
        assert transport.available_streams == ("primary",)
        assert NUS_TX_UUID in FakeClient.last.notify
        assert SECONDARY_TX_UUID not in FakeClient.last.notify
    finally:
        transport.close()


def test_power_cycle_reconnect_ignores_stale_ble_callbacks(monkeypatch):
    FakeDevice, FakeScanner, FakeClient = _install_fake_ble(monkeypatch)
    selected = FakeDevice("LoRa-Chatter-72E0", "AA:01")
    FakeScanner.devices = [selected]

    transport = _multi_stream_transport(
        BleDeviceIdentity(selected.name, selected.address),
    )
    try:
        assert transport.connect()
        first = FakeClient.last
        first_primary = first.notify[NUS_TX_UUID]
        first_secondary = first.notify[SECONDARY_TX_UUID]

        # Reproduce the real failure shape: the peripheral disappears without
        # serialterminal being closed, so Bleak reports a remote disconnect.
        first.remote_disconnect()
        assert not transport.is_connected

        # Even before normal cleanup runs, callbacks from the dead connection
        # must no longer be allowed to enqueue bytes.
        first_primary(None, bytearray(b"stale-before-reconnect\n"))
        first_secondary(None, bytearray(b"stale-before-reconnect\n"))

        # TerminalSession does this after read_chunk notices the disconnect.
        transport.disconnect()
        assert set(first.stop_calls) == {
            NUS_TX_UUID,
            SECONDARY_TX_UUID,
        }

        assert transport.connect()
        second = FakeClient.last
        assert second is not first
        assert transport.is_connected

        # Model a backend retaining the old notify registrations across the
        # reconnect. These callbacks must be ignored instead of producing the
        # observed 2x/3x copies after successive board power cycles.
        first_primary(None, bytearray(b"stale-primary\n"))
        first_secondary(None, bytearray(b"stale-secondary\n"))

        # A delayed disconnect callback from the old BleakClient must also not
        # clear the state of the current connection.
        first.disconnected_callback(first)
        assert transport.is_connected

        second.notify[NUS_TX_UUID](None, bytearray(b"fresh-primary\n"))
        second.notify[SECONDARY_TX_UUID](
            None,
            bytearray(b"fresh-secondary\n"),
        )

        first_chunk = transport.read_chunk(512)
        second_chunk = transport.read_chunk(512)
        assert (first_chunk.stream, first_chunk.data) == (
            "primary",
            b"fresh-primary\n",
        )
        assert (second_chunk.stream, second_chunk.data) == (
            "secondary",
            b"fresh-secondary\n",
        )
    finally:
        transport.close()
