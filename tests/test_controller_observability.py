import queue
import threading
from types import SimpleNamespace

from serialterminal.agent import SessionManager
from serialterminal.tui import TerminalTui


class _ControllerAdapter:
    def __init__(self, state="resetting", epoch=3, generation=7):
        self.snapshot = {
            "state": state,
            "epoch": epoch,
            "ready": state == "ready",
            "connection_generation": generation,
            "reset_generation": generation,
        }

    def controller_status(self):
        return dict(self.snapshot)


class _FakeSession:
    def __init__(self):
        self.connected_event = threading.Event()
        self.connected_event.set()
        self.stop_event = threading.Event()
        self.outgoing = queue.Queue()
        self.transport = SimpleNamespace(
            device_key="fake:node",
            description="fake node",
            stream_capabilities=("chat", "telemetry"),
        )

    def _current_transport(self):
        return self.transport

    def latest_event_seq(self):
        return 12


def _manager_with_session(*, connected=True, controller_state="resetting"):
    manager = SessionManager(selector_factory=lambda *_args: None)
    adapter = _ControllerAdapter(state=controller_state)
    session = _FakeSession()
    if not connected:
        session.connected_event.clear()
    file_manager = SimpleNamespace(
        transport=adapter,
        display_snapshot=lambda: None,
    )
    with manager._lock:
        manager._sessions["s1"] = session
        manager._session_profiles["s1"] = "chatter"
        manager._file_managers["s1"] = file_manager
    return manager, adapter


def test_agent_status_exposes_controller_lifecycle_snapshot():
    manager, adapter = _manager_with_session()

    status = manager.status("s1")

    assert status["state"] == "connected"
    assert status["controller"] == adapter.snapshot
    assert status["controller"]["state"] == "resetting"
    assert status["controller"]["epoch"] == 3


def test_agent_distinguishes_transport_reconnect_without_controller_reset():
    manager, adapter = _manager_with_session(
        connected=False,
        controller_state="ready",
    )

    status = manager.status("s1")

    assert status["state"] == "reconnecting"
    assert status["controller"] == adapter.snapshot
    assert status["controller"]["state"] == "ready"
    assert status["controller"]["epoch"] == 3


def test_tui_adds_controller_recovery_row_without_active_transfer():
    tui = TerminalTui.__new__(TerminalTui)
    tui._binary_adapter = _ControllerAdapter(
        state="reconnecting",
        epoch=4,
        generation=9,
    )
    tui._file_transfer = None

    lines = tui._file_status_lines(100)

    assert lines == (
        " Controller reconnecting | epoch 4 | transport generation 9",
    )


def test_tui_hides_controller_row_after_ready():
    tui = TerminalTui.__new__(TerminalTui)
    tui._binary_adapter = _ControllerAdapter(state="ready", epoch=5, generation=10)
    tui._file_transfer = None

    assert tui._file_status_lines(100) == ()
