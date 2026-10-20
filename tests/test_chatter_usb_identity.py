from queue import Empty, Queue
from types import SimpleNamespace
import time

import pytest

from serialterminal.profiles import GENERIC_PROFILE, SendLine
from serialterminal.profiles.chatter import CHATTER_PROFILE
from serialterminal.profiles.chatter.profile import ChatterProfile
from serialterminal.profiles.chatter.tui import ChatterTuiPanel
from serialterminal.terminal import TerminalSession
from serialterminal.transports.base import Transport
from serialterminal.transports.serial import SerialTransport
from serialterminal.tui import TerminalTui


NODE = "LoRa-Chatter-1B44"


class FakeUsb(SerialTransport):
    def __init__(self, *, pending_input="", drop_first=False, respond=True):
        super().__init__(device="/dev/ttyUSB-IDENTITY-TEST")
        self.connected = False
        self.pending_input = pending_input
        self.drop_first = drop_first
        self.respond = respond
        self.commands = []
        self.writes = []
        self.rx = Queue()

    @property
    def is_connected(self):
        return self.connected

    def connect(self):
        self.connected = True
        return True

    def disconnect(self):
        self.connected = False

    def write(self, data):
        self.writes.append(data)
        self.pending_input += data.decode("ascii")
        while "\n" in self.pending_input:
            command, self.pending_input = self.pending_input.split("\n", 1)
            self.commands.append(command)
            if self.drop_first:
                self.drop_first = False
                continue
            if command == "/id" and self.respond:
                self.rx.put(f"[SYS] CHATTER NODE {NODE}\n".encode())

    def read(self, size=512):
        try:
            return self.rx.get(timeout=0.01)
        except Empty:
            return b""


def wait_until(predicate):
    deadline = time.monotonic() + 1
    while not predicate():
        assert time.monotonic() < deadline
        time.sleep(0.005)


@pytest.fixture
def usb_tui(tmp_path, monkeypatch):
    monkeypatch.setattr(ChatterProfile, "make_binary_user_transport", lambda *a, **k: None)
    sessions = []

    def build(transport, profile=CHATTER_PROFILE):
        tui = TerminalTui(
            transport=transport, log_path=str(tmp_path / f"run-{len(sessions)}.log"),
            line_ending="\n", reconnect_delay=0.01,
            selector=SimpleNamespace(choose_transport_menu=lambda: None),
            profile=profile,
        )
        sessions.append(tui.session)
        return tui

    yield build
    for session in sessions:
        session.stop()
        session.close_logs()


@pytest.mark.parametrize("cause", ["stale_input", "lost_first_request"])
def test_real_session_usb_startup_recovers_identity_without_manual_input(usb_tui, cause):
    transport = FakeUsb(pending_input="gB" if cause == "stale_input" else "",
                        drop_first=cause == "lost_first_request")
    tui = usb_tui(transport)
    now = [0.0]
    tui.panel._clock = lambda: now[0]
    tui.session.start()
    wait_until(tui.session.connected_event.is_set)
    assert transport.writes[0] == b"/id\n"
    assert tui.panel.node == "?"

    tui._run_connected_actions()
    now[0] = 1.0
    tui._run_connected_actions()
    wait_until(lambda: tui.panel.node == NODE)
    wait_until(lambda: tui.session.outgoing.unfinished_tasks == 0)

    assert transport.writes.count(b"/id\n") == 2
    if cause == "stale_input":
        assert transport.commands[0] == "gB/id"
    now[0] = 100.0
    tui._run_connected_actions()
    assert tui.session.outgoing.unfinished_tasks == 0
    assert transport.writes.count(b"/id\n") == 2


def test_fast_initial_identity_stops_retries_before_first_ui_tick(usb_tui):
    transport = FakeUsb()
    tui = usb_tui(transport)
    tui.session.start()
    wait_until(lambda: tui.panel.node == NODE)
    tui._run_connected_actions()
    wait_until(lambda: tui.session.outgoing.unfinished_tasks == 0)
    tui.panel._clock = lambda: 1000000000.0
    tui._run_connected_actions()
    assert transport.writes.count(b"/id\n") == 1


def test_unknown_usb_identity_retry_is_bounded_and_restarts_per_generation():
    now = [0.0]
    panel = ChatterTuiPanel(clock=lambda: now[0])
    transport = FakeUsb()

    def poll(generation=1, connected=True):
        return panel.poll_actions(transport, connected=connected,
                                  connection_generation=generation)

    assert poll() == ()
    for stamp in (0.99, 1.0, 1.5, 2.0, 3.0, 4.0, 100.0):
        now[0] = stamp
        assert poll() == ((SendLine("/id"),) if stamp in (1.0, 2.0, 3.0) else ())
    assert panel.node == "?"
    assert poll(generation=2) == ()
    now[0] = 101.0
    assert poll(generation=2) == (SendLine("/id"),)
    assert poll(generation=2, connected=False) == ()
    now[0] = 200.0
    assert poll(generation=3, connected=False) == ()
    assert poll(generation=3) == ()
    now[0] = 201.0
    assert poll(generation=3) == (SendLine("/id"),)


@pytest.mark.parametrize("label", [None, "LoRa-Chatter-advertised"])
def test_ble_and_other_transports_do_not_get_usb_identity_queries(label):
    class OtherTransport(Transport):
        is_connected = True
        description = "ble-or-spp"
        def connect(self): return True
        def disconnect(self): pass
        def read(self, size=512): return b""
        def write(self, data): pytest.fail("no transport I/O from panel")

    now = [0.0]
    panel = ChatterTuiPanel(clock=lambda: now[0])
    panel.set_transport_identity(label)
    for stamp in (0.0, 1.0, 3.0, 100.0):
        now[0] = stamp
        assert panel.poll_actions(OtherTransport(), connected=True,
                                  connection_generation=1) == ()


def test_generic_usb_startup_sends_no_identity_commands(usb_tui):
    transport = FakeUsb()
    tui = usb_tui(transport, GENERIC_PROFILE)
    tui.session.start()
    wait_until(tui.session.connected_event.is_set)
    tui._run_connected_actions()
    assert transport.writes == []


def test_tui_f2_seeds_identity_before_fast_response(monkeypatch):
    tui = object.__new__(TerminalTui)
    tui.panel = ChatterTuiPanel()
    tui._file_transfer_active = lambda: False
    transport = FakeUsb()

    def change_device(*, before_resume=None):
        if before_resume is not None:
            before_resume(transport)
        tui.panel.consume_line("main", f"[SYS] CHATTER NODE {NODE}")

    tui.session = SimpleNamespace(_change_device=change_device,
                                  _current_transport=lambda: transport)
    monkeypatch.setattr("serialterminal.tui_core.curses.endwin", lambda: None)
    tui._choose_device(SimpleNamespace(refresh=lambda: None))
    assert tui.panel.node == NODE


def test_device_seed_callback_runs_while_receive_is_paused(tmp_path):
    transport = FakeUsb()
    session = TerminalSession(transport, log_path=tmp_path / "choose.log",
                              device_chooser=lambda: None, screen_writer=lambda text: None)
    seen = []
    try:
        def seed(current):
            assert current is transport
            assert session.connection_paused.is_set()
            seen.append(current)
        session._change_device(before_resume=seed)
        assert seen == [transport]
        assert not session.connection_paused.is_set()
    finally:
        session.stop()
        session.close_logs()


def test_failed_device_seed_callback_releases_pause(tmp_path):
    session = TerminalSession(FakeUsb(), log_path=tmp_path / "choose.log",
                              device_chooser=lambda: None, screen_writer=lambda text: None)
    try:
        def seed(current):
            raise RuntimeError("seed failed")
        with pytest.raises(RuntimeError, match="seed failed"):
            session._change_device(before_resume=seed)
        assert not session.connection_paused.is_set()
    finally:
        session.stop()
        session.close_logs()
