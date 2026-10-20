import asyncio
from dataclasses import replace
import json
import threading
from types import SimpleNamespace

import pytest

from serialterminal import ble_discovery
from serialterminal.agent import AgentError, AgentProtocol, SessionManager
from serialterminal.cli import DeviceSelector
from serialterminal.profiles.chatter import CHATTER_PROFILE
from serialterminal.runlog import RunLog
from serialterminal.transports import ble_nus, bluez_devices, bluez_release
from test_ble_nus import _install_fake_ble


ADDRESS = "AA:BB:CC:DD:EE:FF"
PATH = "/org/bluez/hci1/dev_AA_BB_CC_DD_EE_FF"
OTHER = "/org/bluez/hci1/dev_11_22_33_44_55_66"


def device_props(address, name=None, *, connected=True, alias=None):
    props = {
        "Address": SimpleNamespace(value=address),
        "Connected": SimpleNamespace(value=connected),
    }
    if name is not None:
        props["Name"] = SimpleNamespace(value=name)
    if alias is not None:
        props["Alias"] = SimpleNamespace(value=alias)
    return {"org.bluez.Device1": props}


class Bus:
    def __init__(self):
        self.objects = {PATH: device_props(ADDRESS, "Нода"),
                        OTHER: device_props("11:22:33:44:55:66", "Other")}
        self.calls = []
        self.timeline = []
        self.closed = 0
        self.mode = "normal"

    async def call(self, message):
        from dbus_fast.constants import MessageType

        self.calls.append(message)
        self.timeline.append(message.member)
        error = None
        if self.mode == "unavailable":
            error = "org.freedesktop.DBus.Error.ServiceUnknown"
        elif message.member == "GetManagedObjects":
            if self.mode == "scan_hang":
                await asyncio.Event().wait()
            return SimpleNamespace(message_type=MessageType.METHOD_RETURN,
                                   body=[self.objects])
        elif message.path not in self.objects:
            error = "org.freedesktop.DBus.Error.UnknownObject"
        elif message.member == "Disconnect":
            if self.mode == "denied":
                error = "org.bluez.Error.NotAuthorized"
            elif self.mode == "hang":
                await asyncio.Event().wait()
            elif self.mode != "unchanged":
                self.set_connected(message.path, False)
        if error:
            return SimpleNamespace(message_type=MessageType.ERROR,
                                   error_name=error, body=["test error"])
        body = [self.objects[message.path]["org.bluez.Device1"]["Connected"]] if message.member == "Get" else []
        return SimpleNamespace(message_type=MessageType.METHOD_RETURN, body=body)

    def set_connected(self, path, value):
        self.objects[path]["org.bluez.Device1"]["Connected"].value = value

    def connected(self, path=PATH):
        return self.objects[path]["org.bluez.Device1"]["Connected"].value

    def disconnect(self):
        self.closed += 1

    async def wait_for_disconnect(self):
        pass


@pytest.fixture
def lab(monkeypatch, tmp_path):
    monkeypatch.setattr(bluez_devices.sys, "platform", "linux")
    monkeypatch.setenv("SERIALTERMINAL_CACHE_FILE", str(tmp_path / "cache.json"))
    bus = Bus()

    async def system_bus():
        return bus

    monkeypatch.setattr(bluez_devices, "_system_bus", system_bus)
    monkeypatch.setattr(bluez_release, "_system_bus", system_bus)
    Device, Scanner, Client = _install_fake_ble(monkeypatch)
    device = Device("Нода", ADDRESS)
    Scanner.devices = [device]
    Client.max_write_without_response_size = 244

    async def discover(timeout=3.0, **kwargs):
        bus.timeline.append("scan")
        return [] if bus.connected() else [device]

    async def find(address, timeout=3.0):
        bus.timeline.append("find")
        assert address.lower() == ADDRESS.lower()
        assert not bus.connected(), "lookup должен идти после подтверждённого release"
        return next((item for item in Scanner.devices if item.address == ADDRESS), None)

    original_init = Client.__init__
    original_connect = Client.connect
    original_disconnect = Client.disconnect
    backend_type = type("FakeBluezBackend", (), {"__module__": "bleak.backends.bluezdbus.client"})

    def init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self._backend = backend_type()
        self._backend._device_path = PATH

    async def connect(self):
        bus.timeline.append("connect")
        assert not bus.connected()
        await original_connect(self)
        bus.set_connected(PATH, True)

    async def disconnect(self):
        await original_disconnect(self)
        bus.set_connected(PATH, False)

    monkeypatch.setattr(Scanner, "discover", discover)
    monkeypatch.setattr(Scanner, "find_device_by_address", find)
    monkeypatch.setattr(Client, "__init__", init)
    monkeypatch.setattr(Client, "connect", connect)
    monkeypatch.setattr(Client, "disconnect", disconnect)
    monkeypatch.setattr(ble_nus, "DEFAULTS", replace(
        ble_nus.DEFAULTS,
        ble_cleanup=replace(ble_nus.DEFAULTS.ble_cleanup, bluez_timeout_s=.04),
    ))
    transports = []

    def make_transport(*, busy=True):
        transport = ble_nus.BleNusTransport(
            ble_nus.BleDeviceIdentity("Нода", ADDRESS, PATH if busy else None),
            scan_timeout=.02, connect_timeout=.1,
        )
        transports.append(transport)
        return transport

    yield SimpleNamespace(bus=bus, Scanner=Scanner, Client=Client,
                          make_transport=make_transport)
    for transport in transports:
        transport.close()
        assert not transport._loop_thread.is_alive()


def test_bluez_snapshot_filters_connected_objects_and_uses_alias(lab):
    lab.bus.objects[PATH] = device_props(ADDRESS, "Name", alias="Alias")
    lab.bus.objects["/org/bluez/hci1/dev_00_00_00_00_00_01"] = device_props("00:00:00:00:00:01", connected=False)
    lab.bus.objects["/org/bluez/hci1/dev_BAD"] = device_props("BAD", "Invalid")
    lab.bus.objects["/org/bluez/hci1"] = {"org.bluez.Adapter1": {}}
    found = asyncio.run(bluez_devices.connected_devices())
    assert [(item.path, item.address, item.name) for item in found] == [
        (OTHER, "11:22:33:44:55:66", "Other"), (PATH, ADDRESS, "Alias"),
    ]
    message, = lab.bus.calls
    assert (message.destination, message.path, message.interface, message.member) == (
        "org.bluez", "/", "org.freedesktop.DBus.ObjectManager", "GetManagedObjects",
    )
    assert lab.bus.closed == 1
    assert lab.bus.connected() and lab.bus.connected(OTHER)


def test_bluez_unnamed_device_remains_visible(lab):
    lab.bus.objects = {PATH: device_props(ADDRESS)}
    assert asyncio.run(bluez_devices.connected_devices())[0].name == "<unnamed>"


def test_duplicate_address_on_two_adapters_keeps_one_stable_target(lab):
    first_path = PATH.replace("hci1", "hci0")
    lab.bus.objects[first_path] = device_props(ADDRESS, "First adapter")
    found = ble_discovery.discover_terminal_ble_devices(.01)
    selected, = [item for item in found if item.address == ADDRESS]
    assert selected.bluez_path == first_path
    assert len(found) == 2
    assert {call.member for call in lab.bus.calls} == {"GetManagedObjects"}


@pytest.mark.parametrize("mode,error", [("unavailable", RuntimeError), ("scan_hang", asyncio.TimeoutError)])
def test_bluez_enumeration_failure_closes_bus(lab, mode, error):
    lab.bus.mode = mode
    with pytest.raises(error):
        asyncio.run(bluez_devices.connected_devices(timeout=.01))
    assert lab.bus.closed == 1
    assert all(call.member == "GetManagedObjects" for call in lab.bus.calls)


def test_bluez_enumeration_cancellation_closes_bus(lab):
    lab.bus.mode = "scan_hang"

    async def scenario():
        task = asyncio.create_task(bluez_devices.connected_devices())
        while not lab.bus.calls:
            await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())
    assert lab.bus.closed == 1


def test_non_linux_discovery_never_opens_system_bus(monkeypatch):
    monkeypatch.setattr(bluez_devices.sys, "platform", "darwin")

    async def forbidden():
        pytest.fail("non-Linux discovery must not use BlueZ")

    monkeypatch.setattr(bluez_devices, "_system_bus", forbidden)
    assert asyncio.run(bluez_devices.connected_devices()) == []


def test_discovery_includes_non_advertising_bluez_devices_without_disconnect(lab):
    found = ble_discovery.discover_terminal_ble_devices(.01)
    assert {item.address for item in found} == {ADDRESS, "11:22:33:44:55:66"}
    assert all(item.busy for item in found)
    assert {call.member for call in lab.bus.calls} == {"GetManagedObjects"}
    assert not lab.Client.instances


def test_scan_and_bluez_deduplicate_case_insensitive_address(lab, monkeypatch):
    async def scan(timeout):
        return [ble_discovery.BleDiscoveryItem(ble_nus.BleDeviceIdentity("Advertised", ADDRESS.lower()))]

    monkeypatch.setattr(ble_discovery, "scan_all_ble_devices", scan)
    found = ble_discovery.discover_terminal_ble_devices(.01)
    selected = [item for item in found if item.key == f"ble-address:{ADDRESS.lower()}"]
    assert selected == [ble_nus.BleDeviceIdentity("Нода", ADDRESS, PATH)]
    assert len(found) == 2


def test_scan_failure_still_returns_bluez_devices_and_logs(lab, monkeypatch):
    errors = []

    async def scan(timeout):
        raise RuntimeError("scan failed")

    monkeypatch.setattr(ble_discovery, "scan_all_ble_devices", scan)
    monkeypatch.setattr(ble_discovery, "report_exception", lambda exc, context: errors.append(str(exc)))
    assert len(ble_discovery.discover_terminal_ble_devices(.01)) == 2
    assert errors == ["scan failed"]


def test_scan_failure_is_not_hidden_when_bluez_has_no_devices(lab, monkeypatch):
    lab.bus.objects = {}

    async def scan(timeout):
        raise RuntimeError("scan failed")

    monkeypatch.setattr(ble_discovery, "scan_all_ble_devices", scan)
    with pytest.raises(RuntimeError, match="scan failed"):
        ble_discovery.discover_terminal_ble_devices(.01)


def test_bluez_failure_keeps_scan_results_and_logs(lab, monkeypatch):
    lab.bus.set_connected(PATH, False)
    lab.bus.mode = "unavailable"
    errors = []
    monkeypatch.setattr(ble_discovery, "report_exception", lambda exc, context: errors.append(str(exc)))
    found = ble_discovery.discover_terminal_ble_devices(.01)
    assert found == [ble_nus.BleDeviceIdentity("Нода", ADDRESS)]
    assert len(errors) == 1 and "ServiceUnknown" in errors[0]


def test_known_menu_refreshes_busy_without_active_scan(lab):
    selector = DeviceSelector("ble")
    candidate = selector._ble_candidate(ble_nus.BleDeviceIdentity("Нода", ADDRESS))
    selector._remember_candidates([candidate])
    found = selector.known_candidates()
    assert len(found) == 2
    assert all(item.busy and item.label.endswith(" (busy)") for item in found)
    assert "scan" not in lab.bus.timeline
    lab.bus.set_connected(PATH, False)
    found = selector.known_candidates()
    selected, = [item for item in found if item.key == candidate.key]
    assert not selected.busy and selected.label == "BLE  Нода"


def test_known_menu_read_failure_preserves_previous_busy_marker(lab):
    selector = DeviceSelector("ble")
    busy = selector._ble_candidate(ble_nus.BleDeviceIdentity("Нода", ADDRESS, PATH))
    selector._remember_candidates([busy])
    lab.bus.mode = "unavailable"
    assert selector.known_candidates() == [busy]


@pytest.mark.parametrize("tty", [False, True])
def test_busy_suffix_is_yellow_only_on_human_tty(lab, monkeypatch, capsys, tty):
    candidate = DeviceSelector._ble_candidate(ble_nus.BleDeviceIdentity("Нода", ADDRESS, PATH))
    monkeypatch.setattr("sys.stdout.isatty", lambda: tty)
    DeviceSelector._print_menu([candidate])
    output = capsys.readouterr().out
    assert "Нода" in output and ADDRESS in output
    if tty:
        assert "BLE  Нода \033[33m(busy)\033[0m\n" in output
    else:
        assert "BLE  Нода (busy)\n" in output and "\033" not in output
    assert candidate.label == "BLE  Нода (busy)"
    assert not lab.bus.calls


@pytest.mark.parametrize("busy", [False, True])
def test_single_busy_target_requires_explicit_selection(lab, monkeypatch, busy):
    selector = DeviceSelector("ble")
    identity = ble_nus.BleDeviceIdentity("Нода", ADDRESS, PATH if busy else None)
    candidate = selector._ble_candidate(identity)
    reads = []
    monkeypatch.setattr(selector, "_read_menu_answer", lambda *args: reads.append(args) or "1")
    assert selector.choose_from([candidate], auto_single=True, allow_cancel=False) is candidate
    assert len(reads) == int(busy)
    assert not lab.bus.calls and not lab.Client.instances


def test_cancel_busy_selection_or_close_unused_transport_has_no_side_effects(lab, monkeypatch):
    selector = DeviceSelector("ble")
    candidate = selector._ble_candidate(ble_nus.BleDeviceIdentity("Нода", ADDRESS, PATH))
    monkeypatch.setattr(selector, "_read_menu_answer", lambda *args: "")
    assert selector.choose_from([candidate], auto_single=False, allow_cancel=True) is None
    transport = selector.make_transport(candidate)
    transport.close()
    assert not lab.bus.calls and not lab.Client.instances
    assert not transport._loop_thread.is_alive()


def test_takeover_verifies_disconnect_before_lookup_and_connect(lab):
    transport = lab.make_transport()
    assert not lab.bus.calls
    assert transport.connect()
    assert lab.bus.timeline == ["Get", "Disconnect", "Get", "find", "connect"]
    assert transport.pending_bluez_takeover is None
    assert lab.bus.connected(OTHER)
    assert all(call.path == PATH for call in lab.bus.calls)
    assert transport.connect_error is None


@pytest.mark.parametrize("mode", ["denied", "unchanged", "hang", "unavailable"])
def test_failed_takeover_never_starts_scan_or_client_and_can_retry(lab, mode):
    transport = lab.make_transport()
    lab.bus.mode = mode
    assert not transport.connect()
    assert "cannot release selected busy BLE device" in transport.connect_error
    assert transport.pending_bluez_takeover == PATH
    assert "find" not in lab.bus.timeline and "connect" not in lab.bus.timeline
    assert not lab.Client.instances and lab.bus.connected(OTHER)
    lab.bus.mode = "normal"
    assert transport.connect()
    assert transport.pending_bluez_takeover is None and transport.connect_error is None


def test_already_released_busy_snapshot_does_not_issue_disconnect(lab):
    lab.bus.set_connected(PATH, False)
    transport = lab.make_transport()
    assert transport.connect()
    assert lab.bus.timeline == ["Get", "find", "connect"]


def test_non_busy_connect_does_not_attempt_takeover(lab):
    lab.bus.set_connected(PATH, False)
    assert lab.make_transport(busy=False).connect()
    assert lab.bus.timeline == ["find", "connect"]


def test_takeover_is_consumed_even_when_following_scan_misses_device(lab):
    transport = lab.make_transport()
    lab.Scanner.devices = []
    assert not transport.connect()
    assert transport.pending_bluez_takeover is None
    assert [call.member for call in lab.bus.calls] == ["Get", "Disconnect", "Get"]
    lab.Scanner.devices = [SimpleNamespace(name="Нода", address=ADDRESS)]
    lab.bus.calls.clear()
    assert transport.connect()
    assert not lab.bus.calls


def test_normal_reconnect_does_not_replay_takeover(lab):
    transport = lab.make_transport()
    assert transport.connect()
    lab.Client.last.remote_disconnect()
    lab.bus.set_connected(PATH, False)
    lab.bus.calls.clear()
    assert transport.connect()
    assert not any(call.member == "Disconnect" for call in lab.bus.calls)
    assert len(lab.Client.instances) == 2


def test_profile_recreation_keeps_pending_takeover(lab):
    original = lab.make_transport()
    replacement = DeviceSelector("ble").recreate_transport(original, CHATTER_PROFILE)
    try:
        assert replacement.pending_bluez_takeover == PATH
        assert replacement.device_key == original.device_key
        assert not lab.bus.calls
    finally:
        replacement.close()


def test_close_cancels_pending_takeover_without_late_connection(lab, monkeypatch):
    transport = lab.make_transport()
    entered = threading.Event()

    async def stalled(*args, **kwargs):
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(ble_nus, "verify_release", stalled)
    result = []
    worker = threading.Thread(target=lambda: result.append(transport.connect()))
    worker.start()
    try:
        assert entered.wait(1)
        transport.close()
        worker.join(1)
        assert not worker.is_alive() and result == [False]
        assert not lab.Client.instances and not transport.is_connected
        assert not transport.connect()
    finally:
        transport.close()
        worker.join(1)


def test_agent_discover_and_open_use_real_selector_and_takeover(lab, tmp_path):
    run_log = RunLog(tmp_path / "agent.log")
    manager = SessionManager(receive_dir=tmp_path, reconnect_delay=.01)
    protocol = AgentProtocol(manager, run_log=run_log)
    try:
        response = json.loads(protocol.process_line(json.dumps({
            "id": 1, "op": "discover", "scope": "ble", "scan_seconds": .01,
        })))
        assert response["ok"]
        selected, = [item for item in response["result"]["devices"] if item["key"].endswith(ADDRESS.lower())]
        assert selected["busy"] is True and selected["label"] == "BLE  Нода (busy)"
        assert "\033" not in json.dumps(response)
        assert not any(call.member == "Disconnect" for call in lab.bus.calls)
        lab.bus.timeline.clear()
        opened = manager.open(selected["key"], wait_connected_ms=1000)
        assert opened["state"] == "connected"
        assert lab.bus.timeline[:5] == ["Get", "Disconnect", "Get", "find", "connect"]
        before = len(lab.bus.calls)
        with pytest.raises(AgentError) as caught:
            manager.open(selected["key"], wait_connected_ms=0)
        assert caught.value.code == "device_busy" and len(lab.bus.calls) == before
        assert lab.bus.connected(OTHER)
        manager.close(opened["session"])
        assert not lab.bus.connected() and lab.bus.connected(OTHER)
    finally:
        manager.close_all()
        run_log.close()


def test_agent_reports_takeover_failure_as_connect_failed(lab, tmp_path):
    manager = SessionManager(receive_dir=tmp_path, reconnect_delay=.01)
    try:
        selected, = [item for item in manager.discover(scope="ble", scan_seconds=.01)["devices"]
                     if item["key"].endswith(ADDRESS.lower())]
        lab.bus.mode = "denied"
        opened = manager.open(selected["key"], wait_connected_ms=100)
        assert opened["state"] == "reconnecting"
        session = manager._get_session(opened["session"])
        errors = [event for event in session.events_after(0) if event.state == "connect-failed"]
        assert len(errors) == 1 and "NotAuthorized" in errors[0].error
        assert not lab.Client.instances
        assert lab.bus.connected() and lab.bus.connected(OTHER)
    finally:
        manager.close_all()
