import asyncio
from dataclasses import replace
import io
import json
import threading
import time
from types import SimpleNamespace

import pytest

from serialterminal.application_log import ApplicationLog
from serialterminal.transports import ble_nus, bluez_release
from serialterminal.session import ManagedSession
from serialterminal.runlog import RunLog
from serialterminal.agent import SessionManager
from test_ble_nus import _install_fake_ble
from test_agent import FakeSelectorFactory

PATH = "/org/bluez/hci1/dev_AA_BB_CC_DD_EE_FF"
OTHER = "/org/bluez/hci1/dev_11_22_33_44_55_66"


class FakeBus:
    def __init__(self, *, connected=True, mode="normal"):
        self.devices = {PATH: connected, OTHER: True}
        self.mode = mode
        self.calls = []
        self.closed = False

    async def call(self, message):
        from dbus_fast.constants import MessageType
        self.calls.append((message.path, message.interface, message.member, message.body))
        error = None
        if self.mode == "unavailable":
            error = "org.freedesktop.DBus.Error.ServiceUnknown"
        elif self.mode == "missing":
            error = "org.freedesktop.DBus.Error.UnknownObject"
        elif message.member == "Disconnect":
            if self.mode == "denied":
                error = "org.bluez.Error.NotAuthorized"
            elif self.mode == "hang":
                await asyncio.Event().wait()
            elif self.mode != "unchanged":
                self.devices[message.path] = False
        if error:
            return SimpleNamespace(message_type=MessageType.ERROR, error_name=error, body=["test error"])
        body = [SimpleNamespace(value=self.devices[message.path])] if message.member == "Get" else []
        return SimpleNamespace(message_type=MessageType.METHOD_RETURN, body=body)

    def disconnect(self):
        self.closed = True

    async def wait_for_disconnect(self):
        return


def install_bus(monkeypatch, bus):
    pytest.importorskip("dbus_fast")
    async def connect():
        return bus
    monkeypatch.setattr(bluez_release, "_system_bus", connect)


@pytest.mark.parametrize("mode,connected,result,forced", [
    ("normal", False, "disconnected", False),
    ("normal", True, "disconnected", True),
    ("missing", True, "disconnected", False),
    ("denied", True, "failed", True),
    ("unchanged", True, "failed", True),
    ("hang", True, "unknown", True),
    ("unavailable", True, "unknown", False),
])
def test_actual_bluez_messages_and_postcondition(monkeypatch, mode, connected, result, forced):
    pytest.importorskip("dbus_fast")
    bus = FakeBus(connected=connected, mode=mode)
    install_bus(monkeypatch, bus)
    start = time.monotonic()
    report = asyncio.run(bluez_release.verify_release(PATH, force_allowed=True, timeout=.04))
    assert report["result"] == result
    assert report["forced"] is forced
    assert all(call[0] == PATH for call in bus.calls)
    assert bus.devices[OTHER] is True
    assert bus.closed
    assert time.monotonic() - start < 1
    disconnects = [c for c in bus.calls if c[2] == "Disconnect"]
    assert len(disconnects) == int(forced)
    if forced:
        assert bus.calls[-1][2] == "Get" or mode == "hang"


def test_no_force_for_already_disconnected_client_even_if_host_is_connected(monkeypatch):
    bus = FakeBus();install_bus(monkeypatch, bus)
    report = asyncio.run(bluez_release.verify_release(PATH, force_allowed=False, timeout=.04))
    assert report["result"] == "failed"
    assert report["connected_after"] is True
    assert [c[2] for c in bus.calls] == ["Get"]


@pytest.mark.parametrize("path", [None, "", "/org/bluez", "/org/bluez/hci1", "/org/bluez/hci1/dev_BAD"])
def test_no_guessing_or_enumeration_when_device_path_missing(monkeypatch, path):
    async def forbidden():
        pytest.fail("must not access host without a client's exact path")
    monkeypatch.setattr(bluez_release, "_system_bus", forbidden)
    report = asyncio.run(bluez_release.verify_release(path, force_allowed=True))
    assert report["result"] == "unknown"
    assert not report["forced"]


def test_bus_connect_timeout_is_unknown_not_disconnected(monkeypatch):
    async def stalled():
        await asyncio.Event().wait()
    monkeypatch.setattr(bluez_release, "_system_bus", stalled)
    report = asyncio.run(bluez_release.verify_release(PATH, force_allowed=True, timeout=.01))
    assert report["result"] == "unknown"
    assert report["connected_after"] is None


def make_transport(monkeypatch, *, mode="stuck", bluez=True):
    FakeDevice, Scanner, Client = _install_fake_ble(monkeypatch)
    device = FakeDevice("Any NUS controller", "AA:BB:CC:DD:EE:FF")
    Scanner.devices = [device]
    Client.max_write_without_response_size = 244
    bus = FakeBus();install_bus(monkeypatch, bus)
    original_init = Client.__init__
    original_connect = Client.connect
    backend = type("FakeBlueZ", (), {"__module__": "bleak.backends.bluezdbus.client"})

    def init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        if bluez:
            self._backend = backend()
            self._backend._device_path = PATH

    async def connect(self):
        await original_connect(self)
        bus.devices[PATH] = True

    async def disconnect(self):
        if mode == "hang":
            await asyncio.Event().wait()
        if mode == "error":
            raise RuntimeError("disconnect failed")
        self.is_connected = False
        if mode == "normal":
            bus.devices[PATH] = False

    monkeypatch.setattr(Client, "__init__", init)
    monkeypatch.setattr(Client, "connect", connect)
    monkeypatch.setattr(Client, "disconnect", disconnect)
    defaults = replace(ble_nus.DEFAULTS, ble_cleanup=replace(
        ble_nus.DEFAULTS.ble_cleanup, notify_timeout_s=.03,
        disconnect_timeout_s=.03, bluez_timeout_s=.05, shutdown_timeout_s=1,
    ))
    monkeypatch.setattr(ble_nus, "DEFAULTS", defaults)
    transport = ble_nus.BleNusTransport(ble_nus.BleDeviceIdentity(device.name, device.address),
                                       scan_timeout=.02, connect_timeout=.02)
    return transport, Client, bus


@pytest.mark.parametrize("mode", ["normal", "stuck", "error", "hang"])
def test_graceful_close_verifies_host_even_when_bleak_lies_or_fails(monkeypatch, tmp_path, mode):
    transport, Client, bus = make_transport(monkeypatch, mode=mode)
    events = [];transport.set_timing_sink(lambda event, **fields: events.append((event, fields)))
    with ApplicationLog(tmp_path / "app.log"):
        assert transport.connect()
        transport.close()
        report = transport.release_report
        assert report["result"] == "disconnected"
        assert report["forced"] is (mode != "normal")
        assert bus.devices[PATH] is False and bus.devices[OTHER] is True
        assert not transport._loop_thread.is_alive()
        assert not transport.connect()
        count = len(bus.calls)
        transport.close()
        assert len(bus.calls) == count
        assert transport.release_report == report
    assert any(event == "ble_release" for event, fields in events)
    assert '"result": "disconnected"' in (tmp_path / "app.log").read_text()


def test_stalled_notifications_cannot_prevent_release(monkeypatch):
    transport, Client, bus = make_transport(monkeypatch)
    async def stalled(self, uuid):
        await asyncio.Event().wait()
    monkeypatch.setattr(Client, "stop_notify", stalled)
    assert transport.connect()
    transport.close()
    assert transport.release_report["result"] == "disconnected"
    assert "stop_notify: TimeoutError" in transport.release_report["cleanup_errors"]
    assert not bus.devices[PATH]


def test_host_denial_is_preserved_in_application_log_and_session_events(monkeypatch, tmp_path, capsys):
    transport, Client, bus = make_transport(monkeypatch)
    bus.mode = "denied"
    session = ManagedSession(transport)
    with ApplicationLog(tmp_path / "app.log") as log:
        assert transport.connect()
        session.stop()
        assert transport.release_report["result"] == "failed"
        assert bus.devices[PATH]
        assert log.error_count == 1
    errors = [e for e in session.events_after(0) if e.kind == "error"]
    assert errors[-1].state == "transport-release"
    assert json.loads(errors[-1].text)["result"] == "failed"
    assert "BLE release unconfirmed" in (tmp_path / "app.log").read_text()
    assert "ST BLE release unconfirmed" in capsys.readouterr().err


def test_non_bluez_and_never_connected_close_need_no_system_bus(monkeypatch):
    transport, Client, bus = make_transport(monkeypatch, bluez=False)
    transport.close()
    assert not bus.calls and transport.release_report is None
    transport, Client, bus = make_transport(monkeypatch, bluez=False)
    assert transport.connect()
    transport.close()
    assert transport.release_report["backend"] == "bleak"
    assert transport.release_report["result"] == "disconnected"
    assert not bus.calls


def test_close_during_connect_retires_client_and_prevents_late_publication(monkeypatch):
    transport, Client, bus = make_transport(monkeypatch)
    entered = threading.Event()
    async def delayed_connect(self):
        self.is_connected = True
        entered.set()
        await asyncio.Event().wait()
    monkeypatch.setattr(Client, "connect", delayed_connect)
    result = []
    worker = threading.Thread(target=lambda: result.append(transport.connect()))
    worker.start()
    assert entered.wait(1)
    transport.close()
    worker.join(1)
    assert not worker.is_alive() and result == [False]
    assert not transport.is_connected and not transport._loop_thread.is_alive()
    assert transport.release_report["result"] == "disconnected"
    assert not bus.devices[PATH]
    assert not transport.connect()


def test_agent_close_and_eof_record_generic_release_report(monkeypatch, tmp_path):
    from test_agent import FakeTransport
    report = {"backend": "fake", "result": "failed", "forced": True}
    monkeypatch.setattr(FakeTransport, "release_report", property(lambda self: dict(report)))
    factory = FakeSelectorFactory()
    with RunLog(tmp_path / "agent.log") as run_log:
        manager = SessionManager(selector_factory=factory, reconnect_delay=.01, run_log=run_log)
        manager.discover()
        first = manager.open("ble:a", wait_connected_ms=500)
        manager.open("serial:b", wait_connected_ms=500)
        closed = manager.close(first["session"])
        assert closed["state"] == "closed" and closed["transport_release"] == report
        # EOF runner использует этот же close_all; ошибка release первой ноды
        # остаётся evidence, а следующая session всё равно освобождается.
        manager.close_all()
        assert manager.list_sessions()["sessions"] == []
        assert not factory.transports["serial:b"].is_connected
    text = (tmp_path / "agent.log").read_text()
    records = [json.loads(line.split("] ", 1)[1]) for line in text.splitlines()]
    releases = [r for r in records if r.get("state") == "transport-release"]
    assert len(releases) == 2
    assert all(r["kind"] == "error" for r in releases)


@pytest.mark.parametrize("result", ["disconnected", "unknown"])
def test_real_agent_eof_flushes_release_before_run_stop(monkeypatch, tmp_path, result):
    import serialterminal.agent as agent_module
    from test_agent import FakeTransport
    report = {"backend": "fake", "result": result, "forced": False}
    monkeypatch.setattr(FakeTransport, "release_report", property(lambda self: dict(report)))
    factory = FakeSelectorFactory()
    original = agent_module.SessionManager
    def manager_factory(**kwargs):
        return original(selector_factory=factory, reconnect_delay=.01, **kwargs)
    monkeypatch.setattr(agent_module, "SessionManager", manager_factory)
    commands = [
        {"id": 1, "op": "discover"},
        {"id": 2, "op": "open", "device_key": "ble:a", "wait_connected_ms": 500},
    ]
    output = io.StringIO()
    assert agent_module.run_agent(log_path=str(tmp_path / "eof.log"),
        stdin=io.StringIO("".join(json.dumps(c)+"\n" for c in commands)), stdout=output) == 0
    records = [json.loads(line.split("] ", 1)[1]) for line in (tmp_path / "eof.log").read_text().splitlines()]
    release = next(r for r in records if r.get("state") == "transport-release")
    assert json.loads(release["text"]) == report
    assert release["kind"] == ("state" if result == "disconnected" else "error")
    assert records[-1]["event"] == "stop"
    assert not factory.transports["ble:a"].is_connected


def test_reconnect_waits_for_old_cleanup_and_stale_callback_cannot_disconnect_new(monkeypatch):
    transport, Client, bus = make_transport(monkeypatch)
    assert transport.connect()
    first = Client.last
    started = threading.Event();release = threading.Event()
    original_disconnect = Client.disconnect
    async def delayed_disconnect(self):
        if self is first:
            started.set()
            while not release.is_set():
                await asyncio.sleep(.001)
        await original_disconnect(self)
    monkeypatch.setattr(Client, "disconnect", delayed_disconnect)
    # Увеличиваем только fake cleanup budget, чтобы тест проверял ordering,
    # а не зависел от планировщика внутри искусственного 30 ms timeout.
    monkeypatch.setattr(ble_nus, "DEFAULTS", replace(ble_nus.DEFAULTS,
        ble_cleanup=replace(ble_nus.DEFAULTS.ble_cleanup, disconnect_timeout_s=1)))
    closer = threading.Thread(target=transport.disconnect)
    closer.start();assert started.wait(1)
    result = []
    opener = threading.Thread(target=lambda: result.append(transport.connect()))
    opener.start()
    try:
        assert len(Client.instances) == 1
        release.set();closer.join(1);opener.join(1)
        assert not closer.is_alive() and not opener.is_alive()
        assert result == [True] and len(Client.instances) == 2
        calls = len(bus.calls)
        first.disconnected_callback(first)
        assert transport.is_connected and bus.devices[PATH]
        assert len(bus.calls) == calls
    finally:
        release.set();closer.join(1);opener.join(1);transport.close()


def test_shutdown_during_stale_client_cleanup_does_not_lose_client(monkeypatch):
    transport, Client, bus = make_transport(monkeypatch)
    assert transport.connect()
    # Backend ещё connected, но transport уже перешёл в reconnect: следующий
    # connect сначала обязан освободить старый клиент.
    transport._connected.clear()
    started = threading.Event()
    async def delayed_disconnect(self):
        started.set()
        await asyncio.Event().wait()
    monkeypatch.setattr(Client, "disconnect", delayed_disconnect)
    worker = threading.Thread(target=transport.connect)
    worker.start()
    try:
        assert started.wait(1)
        transport.close()
        worker.join(1)
        assert not worker.is_alive()
        assert transport.release_report is not None
        assert transport.release_report["result"] == "disconnected"
        assert bus.devices[PATH] is False
    finally:
        transport.close();worker.join(1)


def test_cancelled_system_bus_connect_closes_its_socket(monkeypatch):
    aio = pytest.importorskip("dbus_fast.aio")
    bus = SimpleNamespace(closed=False)
    async def connect():
        await asyncio.Event().wait()
    def disconnect():
        bus.closed = True
    bus.connect = connect;bus.disconnect = disconnect
    monkeypatch.setattr(aio, "MessageBus", lambda **kwargs: bus)
    report = asyncio.run(bluez_release.verify_release(PATH, force_allowed=True, timeout=.01))
    assert report["result"] == "unknown"
    assert bus.closed


def test_tui_shutdown_releases_ble_before_flushing_timing(monkeypatch, tmp_path):
    from serialterminal import tui_core
    from serialterminal.profiles import GENERIC_PROFILE
    transport, Client, bus = make_transport(monkeypatch)
    tui = tui_core.TerminalTui(transport=transport, log_path=str(tmp_path / "tui.log"),
        line_ending="\n", reconnect_delay=.01,
        selector=SimpleNamespace(choose_transport_menu=lambda: None), profile=GENERIC_PROFILE)
    assert transport.connect()
    monkeypatch.setattr(tui_core.curses, "curs_set", lambda value: None)
    monkeypatch.setattr(tui_core.curses, "has_colors", lambda: False)
    monkeypatch.setattr(tui, "_set_mouse_capture", lambda value: None)
    tui.running = False
    tui.run(SimpleNamespace(keypad=lambda value: None, timeout=lambda value: None))
    assert transport.release_report["result"] == "disconnected"
    assert not bus.devices[PATH]
    assert tui.session.log_file.closed
    rows = [json.loads(line) for line in tui.session.timing_path.read_text().splitlines()]
    assert next(r for r in rows if r["event"] == "ble_release")["forced"] is True
    assert rows[-1]["event"] == "run_stop"
