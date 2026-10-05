import asyncio
import time

from serialterminal.transports import ble_nus
from serialterminal.transports.ble_nus import BleDeviceIdentity, NUS_RX_UUID


def _install_fake_ble(monkeypatch, size_sequences, *, bluez_mtus=None):
    class FakeDevice:
        def __init__(self, name, address):
            self.name = name
            self.address = address

    class FakeScanner:
        devices = []

        @staticmethod
        async def discover(timeout=3.0):
            return list(FakeScanner.devices)

        @staticmethod
        async def find_device_by_address(address, timeout=10.0):
            wanted = address.lower()
            for device in FakeScanner.devices:
                if device.address.lower() == wanted:
                    return device
            return None

    class FakeCharacteristic:
        def __init__(self, client):
            self._client = client

        @property
        def max_write_without_response_size(self):
            return self._client.next_write_size()

    class FakeServices:
        def __init__(self, client):
            self._characteristic = FakeCharacteristic(client)

        def get_characteristic(self, _uuid):
            return self._characteristic

    class FakeBlueZBackend:
        def __init__(self, client, mtu_value):
            self._client = client
            self._mtu_value = mtu_value

        async def _acquire_mtu(self):
            callback = FakeClient.on_mtu_acquire
            if callback is not None:
                callback(self._client, self._mtu_value)
            if isinstance(self._mtu_value, BaseException):
                raise self._mtu_value
            if self._mtu_value is None:
                raise RuntimeError("MTU unavailable")
            self._client._mtu_size = self._mtu_value

    FakeBlueZBackend.__module__ = "bleak.backends.bluezdbus.client"

    class FakeClient:
        instances = []
        size_sequences = []
        bluez_mtu_values = None
        on_size_read = None
        on_mtu_acquire = None

        def __init__(self, device, disconnected_callback=None, timeout=10.0):
            self.device = device
            self.disconnected_callback = disconnected_callback
            self.is_connected = False
            self.notify = {}
            self.writes = []
            self.stop_calls = []
            self._mtu_size = 23
            index = len(type(self).instances)
            if index < len(type(self).size_sequences):
                values = type(self).size_sequences[index]
            else:
                values = type(self).size_sequences[-1]
            self._write_sizes = list(values)
            self._write_size_reads = 0
            self.services = FakeServices(self)
            mtu_values = type(self).bluez_mtu_values
            if mtu_values is not None:
                mtu_value = (
                    mtu_values[index]
                    if index < len(mtu_values)
                    else mtu_values[-1]
                )
                self._backend = FakeBlueZBackend(self, mtu_value)
            type(self).instances.append(self)

        @property
        def mtu_size(self):
            return self._mtu_size

        def next_write_size(self):
            index = min(self._write_size_reads, len(self._write_sizes) - 1)
            value = self._write_sizes[index]
            self._write_size_reads += 1
            callback = type(self).on_size_read
            if callback is not None:
                callback(self, self._write_size_reads, value)
            return value

        async def connect(self):
            self.is_connected = True

        async def start_notify(self, uuid, callback):
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

    FakeClient.size_sequences = [list(values) for values in size_sequences]
    FakeClient.bluez_mtu_values = (
        None if bluez_mtus is None else list(bluez_mtus)
    )
    monkeypatch.setattr(ble_nus, "BleakScanner", FakeScanner)
    monkeypatch.setattr(ble_nus, "BleakClient", FakeClient)
    monkeypatch.setattr(ble_nus, "BLE_WRITE_SIZE_RESOLVE_INTERVAL_S", 0.001)
    monkeypatch.setattr(ble_nus, "BLE_WRITE_SIZE_RESOLVE_TIMEOUT_S", 0.006)
    monkeypatch.setattr(ble_nus, "BLE_BLUEZ_MTU_RESOLVE_TIMEOUT_S", 0.01)
    return FakeDevice, FakeScanner, FakeClient


def _transport(selected):
    return ble_nus.BleNusTransport(
        BleDeviceIdentity(selected.name, selected.address),
        scan_timeout=0.02,
        connect_timeout=0.05,
    )


def _resolved_events(events):
    return [fields for name, fields in events if name == "ble_write_size_resolved"]


def _aborted_events(events):
    return [
        fields
        for name, fields in events
        if name == "ble_write_size_resolution_aborted"
    ]


def test_write_size_244_immediately_resolves_without_recheck(monkeypatch):
    FakeDevice, FakeScanner, FakeClient = _install_fake_ble(monkeypatch, [[244]])
    selected = FakeDevice("Controller", "AA:01")
    FakeScanner.devices = [selected]
    events = []
    transport = _transport(selected)
    transport.set_timing_sink(lambda event, **fields: events.append((event, fields)))
    try:
        assert transport.connect()
        resolution = _resolved_events(events)[-1]
        assert resolution["generation"] == 1
        assert resolution["source"] == "characteristic_property"
        assert resolution["initial_size"] == 244
        assert resolution["final_size"] == 244
        assert resolution["rechecks"] == 0
        assert resolution["fallback"] is False
        assert FakeClient.instances[0]._write_size_reads == 1
    finally:
        transport.close()


def test_write_size_transient_20_resolves_to_244(monkeypatch):
    FakeDevice, FakeScanner, FakeClient = _install_fake_ble(
        monkeypatch,
        [[20, 20, 244]],
    )
    selected = FakeDevice("Controller", "AA:01")
    FakeScanner.devices = [selected]
    events = []
    transport = _transport(selected)
    transport.set_timing_sink(lambda event, **fields: events.append((event, fields)))
    try:
        assert transport.connect()
        resolution = _resolved_events(events)[-1]
        assert resolution["source"] == "characteristic_property"
        assert resolution["initial_size"] == 20
        assert resolution["final_size"] == 244
        assert resolution["rechecks"] == 2
        assert resolution["fallback"] is False
        assert FakeClient.instances[0]._write_size_reads == 3
    finally:
        transport.close()


def test_write_size_permanent_20_uses_bounded_fallback(monkeypatch):
    FakeDevice, FakeScanner, _FakeClient = _install_fake_ble(monkeypatch, [[20]])
    selected = FakeDevice("Controller", "AA:01")
    FakeScanner.devices = [selected]
    events = []
    transport = _transport(selected)
    transport.set_timing_sink(lambda event, **fields: events.append((event, fields)))
    started = time.monotonic()
    try:
        assert transport.connect()
        elapsed = time.monotonic() - started
        resolution = _resolved_events(events)[-1]
        assert resolution["source"] == "fallback"
        assert resolution["initial_size"] == 20
        assert resolution["final_size"] == 20
        assert resolution["rechecks"] >= 1
        assert resolution["fallback"] is True
        assert elapsed < 0.2
    finally:
        transport.close()


def test_disconnect_during_write_size_resolution_does_not_publish_state(monkeypatch):
    FakeDevice, FakeScanner, FakeClient = _install_fake_ble(monkeypatch, [[20]])
    selected = FakeDevice("Controller", "AA:01")
    FakeScanner.devices = [selected]
    events = []

    def disconnect_on_first_read(client, read_count, _value):
        if read_count == 1:
            client.remote_disconnect()

    FakeClient.on_size_read = disconnect_on_first_read
    transport = _transport(selected)
    transport.set_timing_sink(lambda event, **fields: events.append((event, fields)))
    try:
        assert not transport.connect()
        assert not transport.is_connected
        assert _resolved_events(events) == []
        aborted = _aborted_events(events)
        assert aborted
        assert aborted[-1]["generation"] == 1
        assert aborted[-1]["reason"] == "connection_changed"
        assert transport._write_size_generation is None
        assert transport._write_size_bytes is None
    finally:
        transport.close()


def test_reconnect_resolves_write_size_again_for_new_generation(monkeypatch):
    FakeDevice, FakeScanner, FakeClient = _install_fake_ble(
        monkeypatch,
        [[244], [20, 244]],
    )
    selected = FakeDevice("Controller", "AA:01")
    FakeScanner.devices = [selected]
    events = []
    transport = _transport(selected)
    transport.set_timing_sink(lambda event, **fields: events.append((event, fields)))
    try:
        assert transport.connect()
        transport.disconnect()
        assert transport.connect()

        resolutions = _resolved_events(events)
        resolved_sizes = [
            (item["generation"], item["initial_size"], item["final_size"])
            for item in resolutions
        ]
        assert resolved_sizes == [
            (1, 244, 244),
            (2, 20, 244),
        ]
        assert len(FakeClient.instances) == 2
        assert FakeClient.instances[1]._write_size_reads == 2
    finally:
        transport.close()


def test_stale_generation_resolution_cannot_publish_into_new_connection(monkeypatch):
    FakeDevice, _FakeScanner, FakeClient = _install_fake_ble(
        monkeypatch,
        [[20, 244], [244]],
    )
    selected = FakeDevice("Controller", "AA:01")
    events = []
    transport = _transport(selected)
    transport.set_timing_sink(lambda event, **fields: events.append((event, fields)))
    holder = {}
    try:
        first, generation = transport._begin_connection(selected)
        first.is_connected = True

        def replace_on_second_read(client, read_count, _value):
            if client is first and read_count == 2:
                second, second_generation = transport._begin_connection(selected)
                second.is_connected = True
                holder["client"] = second
                holder["generation"] = second_generation

        FakeClient.on_size_read = replace_on_second_read
        assert not asyncio.run(
            transport._resolve_write_size_async(first, generation)
        )
        assert holder["generation"] == 2
        assert transport._active_generation == 2
        assert transport._client is holder["client"]
        assert transport._write_size_generation is None
        assert transport._write_size_bytes is None
        aborted = _aborted_events(events)
        assert aborted[-1]["generation"] == 1
        assert aborted[-1]["reason"] == "stale_completion"
    finally:
        transport.close()


def test_successful_resolution_chunks_330_bytes_as_244_plus_86(monkeypatch):
    FakeDevice, FakeScanner, FakeClient = _install_fake_ble(
        monkeypatch,
        [[20, 244]],
    )
    selected = FakeDevice("Controller", "AA:01")
    FakeScanner.devices = [selected]
    transport = _transport(selected)
    try:
        assert transport.connect()
        payload = bytes(index % 251 for index in range(330))
        transport.write(payload)
        writes = FakeClient.instances[0].writes
        assert [len(data) for _uuid, data, _response in writes] == [244, 86]
        assert b"".join(data for _uuid, data, _response in writes) == payload
        assert all(uuid == NUS_RX_UUID for uuid, _data, _response in writes)
        assert all(response is False for _uuid, _data, response in writes)
    finally:
        transport.close()


def test_fallback_20_continues_with_safe_chunking(monkeypatch):
    FakeDevice, FakeScanner, FakeClient = _install_fake_ble(monkeypatch, [[20]])
    selected = FakeDevice("Controller", "AA:01")
    FakeScanner.devices = [selected]
    transport = _transport(selected)
    try:
        assert transport.connect()
        payload = b"x" * 41
        transport.write(payload)
        writes = FakeClient.instances[0].writes
        assert [len(data) for _uuid, data, _response in writes] == [20, 20, 1]
        assert b"".join(data for _uuid, data, _response in writes) == payload
    finally:
        transport.close()


def test_bluez_mtu_247_overrides_characteristic_default_20(monkeypatch):
    FakeDevice, FakeScanner, FakeClient = _install_fake_ble(
        monkeypatch,
        [[20]],
        bluez_mtus=[247],
    )
    selected = FakeDevice("Controller", "AA:01")
    FakeScanner.devices = [selected]
    events = []
    transport = _transport(selected)
    transport.set_timing_sink(lambda event, **fields: events.append((event, fields)))
    try:
        assert transport.connect()
        resolution = _resolved_events(events)[-1]
        assert resolution["generation"] == 1
        assert resolution["source"] == "bluez_mtu"
        assert resolution["mtu"] == 247
        assert resolution["initial_characteristic_size"] == 20
        assert resolution["final_size"] == 244
        assert resolution["rechecks"] == 0
        assert resolution["fallback"] is False
        assert FakeClient.instances[0]._write_size_reads == 1
    finally:
        transport.close()


def test_bluez_mtu_23_resolves_to_safe_20_without_fallback(monkeypatch):
    FakeDevice, FakeScanner, _FakeClient = _install_fake_ble(
        monkeypatch,
        [[20]],
        bluez_mtus=[23],
    )
    selected = FakeDevice("Controller", "AA:01")
    FakeScanner.devices = [selected]
    events = []
    transport = _transport(selected)
    transport.set_timing_sink(lambda event, **fields: events.append((event, fields)))
    try:
        assert transport.connect()
        resolution = _resolved_events(events)[-1]
        assert resolution["source"] == "bluez_mtu"
        assert resolution["mtu"] == 23
        assert resolution["final_size"] == 20
        assert resolution["fallback"] is False
    finally:
        transport.close()


def test_bluez_mtu_185_resolves_to_182(monkeypatch):
    FakeDevice, FakeScanner, _FakeClient = _install_fake_ble(
        monkeypatch,
        [[20]],
        bluez_mtus=[185],
    )
    selected = FakeDevice("Controller", "AA:01")
    FakeScanner.devices = [selected]
    events = []
    transport = _transport(selected)
    transport.set_timing_sink(lambda event, **fields: events.append((event, fields)))
    try:
        assert transport.connect()
        resolution = _resolved_events(events)[-1]
        assert resolution["source"] == "bluez_mtu"
        assert resolution["mtu"] == 185
        assert resolution["final_size"] == 182
    finally:
        transport.close()


def test_bluez_mtu_failure_uses_characteristic_property(monkeypatch):
    FakeDevice, FakeScanner, _FakeClient = _install_fake_ble(
        monkeypatch,
        [[244]],
        bluez_mtus=[RuntimeError("probe failed")],
    )
    selected = FakeDevice("Controller", "AA:01")
    FakeScanner.devices = [selected]
    events = []
    transport = _transport(selected)
    transport.set_timing_sink(lambda event, **fields: events.append((event, fields)))
    try:
        assert transport.connect()
        resolution = _resolved_events(events)[-1]
        assert resolution["source"] == "characteristic_property"
        assert resolution["final_size"] == 244
        assert resolution["fallback"] is False
        assert resolution["reason"] == "bluez_acquire_mtu_RuntimeError"
    finally:
        transport.close()


def test_bluez_mtu_and_characteristic_default_use_safe_fallback(monkeypatch):
    FakeDevice, FakeScanner, _FakeClient = _install_fake_ble(
        monkeypatch,
        [[20]],
        bluez_mtus=[RuntimeError("probe failed")],
    )
    selected = FakeDevice("Controller", "AA:01")
    FakeScanner.devices = [selected]
    events = []
    transport = _transport(selected)
    transport.set_timing_sink(lambda event, **fields: events.append((event, fields)))
    try:
        assert transport.connect()
        resolution = _resolved_events(events)[-1]
        assert resolution["source"] == "fallback"
        assert resolution["final_size"] == 20
        assert resolution["fallback"] is True
        assert resolution["reason"] == "bluez_acquire_mtu_RuntimeError"
    finally:
        transport.close()


def test_bluez_reconnect_resolves_mtu_again_for_each_generation(monkeypatch):
    FakeDevice, FakeScanner, FakeClient = _install_fake_ble(
        monkeypatch,
        [[20], [20]],
        bluez_mtus=[247, 185],
    )
    selected = FakeDevice("Controller", "AA:01")
    FakeScanner.devices = [selected]
    events = []
    transport = _transport(selected)
    transport.set_timing_sink(lambda event, **fields: events.append((event, fields)))
    try:
        assert transport.connect()
        transport.disconnect()
        assert transport.connect()
        resolutions = _resolved_events(events)
        assert [
            (item["generation"], item["mtu"], item["final_size"])
            for item in resolutions
        ] == [(1, 247, 244), (2, 185, 182)]
        assert len(FakeClient.instances) == 2
        assert all(client._write_size_reads == 1 for client in FakeClient.instances)
    finally:
        transport.close()


def test_stale_bluez_mtu_completion_cannot_publish_into_new_generation(monkeypatch):
    FakeDevice, _FakeScanner, FakeClient = _install_fake_ble(
        monkeypatch,
        [[20], [20]],
        bluez_mtus=[247, 185],
    )
    selected = FakeDevice("Controller", "AA:01")
    events = []
    transport = _transport(selected)
    transport.set_timing_sink(lambda event, **fields: events.append((event, fields)))
    holder = {}
    try:
        first, generation = transport._begin_connection(selected)
        first.is_connected = True

        def replace_during_mtu(client, _mtu):
            if client is first:
                second, second_generation = transport._begin_connection(selected)
                second.is_connected = True
                holder["client"] = second
                holder["generation"] = second_generation

        FakeClient.on_mtu_acquire = replace_during_mtu
        assert not asyncio.run(
            transport._resolve_write_size_async(first, generation)
        )
        assert holder["generation"] == 2
        assert transport._active_generation == 2
        assert transport._client is holder["client"]
        assert transport._write_size_generation is None
        assert transport._write_size_bytes is None
        aborted = _aborted_events(events)
        assert aborted[-1]["source"] == "bluez_mtu"
        assert aborted[-1]["reason"] == "connection_changed"
    finally:
        transport.close()


def test_disconnect_during_bluez_mtu_probe_does_not_publish_state(monkeypatch):
    FakeDevice, FakeScanner, FakeClient = _install_fake_ble(
        monkeypatch,
        [[20]],
        bluez_mtus=[247],
    )
    selected = FakeDevice("Controller", "AA:01")
    FakeScanner.devices = [selected]
    events = []

    def disconnect_during_mtu(client, _mtu):
        client.remote_disconnect()

    FakeClient.on_mtu_acquire = disconnect_during_mtu
    transport = _transport(selected)
    transport.set_timing_sink(lambda event, **fields: events.append((event, fields)))
    try:
        assert not transport.connect()
        assert not transport.is_connected
        assert _resolved_events(events) == []
        assert transport._write_size_generation is None
        assert transport._write_size_bytes is None
        aborted = _aborted_events(events)
        assert aborted[-1]["source"] == "bluez_mtu"
        assert aborted[-1]["reason"] == "connection_changed"
    finally:
        transport.close()


def test_bluez_mtu_247_chunks_330_bytes_as_244_plus_86(monkeypatch):
    FakeDevice, FakeScanner, FakeClient = _install_fake_ble(
        monkeypatch,
        [[20]],
        bluez_mtus=[247],
    )
    selected = FakeDevice("Controller", "AA:01")
    FakeScanner.devices = [selected]
    transport = _transport(selected)
    try:
        assert transport.connect()
        payload = bytes(index % 251 for index in range(330))
        transport.write(payload)
        writes = FakeClient.instances[0].writes
        assert [len(data) for _uuid, data, _response in writes] == [244, 86]
        assert b"".join(data for _uuid, data, _response in writes) == payload
        assert all(response is False for _uuid, _data, response in writes)
    finally:
        transport.close()
