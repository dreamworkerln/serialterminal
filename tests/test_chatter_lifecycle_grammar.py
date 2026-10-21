"""Локальные boot/reset proof и USER presentation через production adapters."""
import struct
import time

import pytest

from serialterminal.file_transfer.transport import BinaryUserError
from serialterminal.profiles.chatter.binary_user import ChatterBinaryUserAdapter
from serialterminal.profiles.chatter.machine_client import ChatterMachineClient
from serialterminal.profiles.chatter.machine_codec import Frame, Kind, decode, encode
from serialterminal.profiles.chatter.presentation import ChatterPresentation
from serialterminal.profiles.chatter.radio_timing import RadioTiming
from serialterminal.session import SessionLine
from serialterminal.tui import TerminalTui


BOOT_LINES = (
    "ESP-ROM:esp32s3-20210327",
    "rst:0x3 (SW_RESET),boot:0x8",
    "[SYS] RADIO FATAL RX_RESTART (-16), rebooting",
    "[SYS] CHATTER READY",
)
USER_LINES = ["first:"] + [prefix + text for prefix in (
    "< [-30/8 Q0] ", "> ", "log says ", "  ",
) for text in ("first:", *BOOT_LINES)] + [
    "[SYS] CHATTER READY trailing text",
    "rst:0x3 invalid reset quotation",
]


class AcceptedNode:
    def __init__(self):
        self.epoch = 41
        self.client = None
        self.frames = []
        self.outstanding = set()

    def emit(self, kind, request, payload=b""):
        self.client.feed_line("chat", encode(Frame(kind, self.epoch, request, payload)).decode())

    def send(self, text):
        frame = decode(text.lstrip("\n"))
        self.frames.append(frame)
        if frame.kind == Kind.HELLO:
            self.emit(Kind.WELCOME, frame.request, frame.payload + b"\x02" + struct.pack("<H", 243))
        elif frame.kind == Kind.SUBMIT:
            self.outstanding.add(frame.request)
            self.emit(Kind.ACCEPTED, frame.request)
        elif frame.kind == Kind.QUERY:
            self.emit(Kind.ACCEPTED, frame.request)
        elif frame.kind == Kind.CLOSE:
            self.emit(Kind.CLOSED, frame.request)
        return {"tx_id": len(self.frames)}


def accepted_client():
    node = AcceptedNode()
    client = ChatterMachineClient(node.send, presentation_timeout_s=.03)
    node.client = client
    ticket = client.submit_binary(b"already admitted FT1 message")
    assert ticket.outcome == Kind.ACCEPTED
    return client, node, ticket


@pytest.mark.parametrize("line", USER_LINES)
def test_chat_and_echo_cannot_invalidate_machine_ticket(line):
    client, node, ticket = accepted_client()
    try:
        before = client.controller_status()
        client.feed_line("chat", line)
        assert client.controller_status() == before
        assert client.pending[ticket.request] is ticket
        assert list(client.order) == [ticket.request]
        client.timing_budget_s = lambda purpose: .005
        with pytest.raises(BinaryUserError) as caught:
            client.discard_binary_pipeline()
        assert caught.value.code == "local_tx_unsettled"
        assert client.pending[ticket.request] is ticket
        assert node.epoch == 41 and node.outstanding == {ticket.request}
        # Незавершённый ticket принимает настоящий terminal outcome той же identity.
        node.outstanding.remove(ticket.request)
        node.emit(Kind.LINK_OK, ticket.request)
        client.settle_binary(ticket)
        assert not client.pending
        assert sum(frame.kind == Kind.SUBMIT for frame in node.frames) == 1
    finally:
        client.close()


@pytest.mark.parametrize("line", BOOT_LINES)
def test_real_local_boot_boundary_still_invalidates_old_epoch(line):
    client, node, ticket = accepted_client()
    try:
        node.epoch += 1
        node.outstanding.clear()
        client.feed_line("chat", line)
        assert client.mode == "failed"
        assert client.error.code == "local_controller_reset"
        client.discard_binary_pipeline()
        assert not client.pending
        client.feed_line("chat", "[SYS] CHATTER READY")
        client.prepare_binary(deadline=time.monotonic() + .2)
        assert client.mode == "machine" and client.epoch == node.epoch
        assert sum(frame.kind == Kind.SUBMIT for frame in node.frames) == 1
    finally:
        client.close()


@pytest.mark.parametrize("line", USER_LINES)
def test_user_text_preserves_legacy_lifecycle_phy_and_human_pending(line):
    adapter = ChatterBinaryUserAdapter(lambda text: None, radio_timing=True)
    reader = adapter._radio_timing
    reader.snapshot = reader.last_snapshot = RadioTiming(7, 500000)
    reader.identity = (0, 1)
    before = adapter.controller_status(), reader.snapshot, reader.identity, reader.revision
    tracker = ChatterPresentation()
    assert tracker.submit_payload("owned message")
    tracker.mark_sent("owned message")
    adapter.feed_line("chat", line)
    assert (adapter.controller_status(), reader.snapshot, reader.identity, reader.revision) == before
    assert tracker.consume_firmware_line(line) is None
    assert tracker.pending_count() == 1


@pytest.mark.parametrize("line", [
    "< [-30/8 Q0] [SYS] CHATTER READY",
    "> [SYS] OUTPUT CHAT",
    "log says [SYS] current=CHAT",
    "< [-30/8 Q0] [SYS] current=CHAT echo=OFF",
])
def test_user_ready_or_output_quote_cannot_end_local_reset(line):
    adapter = ChatterBinaryUserAdapter(lambda text: None)
    adapter.feed_line("chat", BOOT_LINES[0])
    before = adapter.controller_status()
    adapter.feed_line("chat", line)
    assert adapter.controller_status() == before
    assert adapter._output_mode is None
    adapter.feed_line("chat", "[SYS]   current=CHAT echo=OFF")
    assert adapter.controller_status()["state"] == "ready"
    assert adapter._output_mode == "CHAT"


@pytest.mark.parametrize("line", USER_LINES)
def test_tui_forwards_user_lines_without_releasing_machine_ownership(line):
    client, node, ticket = accepted_client()
    tui = object.__new__(TerminalTui)
    tui.panel = None
    tui._binary_adapter = client
    try:
        tui._observe_line(SessionLine(stream="main", seq_first=1, seq_last=1,
                                      text=line, timestamp=1.0))
        assert client.mode == "machine"
        assert client.pending[ticket.request] is ticket
        assert node.outstanding == {ticket.request}
    finally:
        client.close()


@pytest.mark.parametrize("line", BOOT_LINES)
def test_real_local_lifecycle_invalidates_phy_and_reveals_sent_text(line):
    adapter = ChatterBinaryUserAdapter(lambda text: None, radio_timing=True)
    reader = adapter._radio_timing
    reader.snapshot = reader.last_snapshot = RadioTiming(7, 500000)
    reader.identity = (0, 1)
    tracker = ChatterPresentation()
    assert tracker.submit_payload("old epoch")
    tracker.mark_sent("old epoch")
    adapter.feed_line("chat", line)
    assert reader.snapshot is None and reader.identity is None
    assert tracker.consume_firmware_line(line) == "old epoch"
    assert tracker.pending_count() == 0


def test_agent_session_forwards_chat_without_releasing_machine_ownership(monkeypatch, tmp_path):
    from types import SimpleNamespace
    import threading
    from serialterminal import agent_core
    from serialterminal.transports.base import ReceivedChunk
    from test_agent_console_log import _SelectorFactory

    client, node, ticket = accepted_client()
    # Уже принятый ticket передаётся настоящему application holder. Background
    # bootstrap здесь не нужен: проверяем RX notifier после законченного HELLO.
    monkeypatch.setattr(client, "start", lambda: None)
    profile = SimpleNamespace(name="chatter", connect_preamble=lambda: (),
                              human_console_streams=lambda: ("main", "chat"),
                              make_binary_user_transport=lambda *args, **kwargs: client)
    monkeypatch.setattr(agent_core, "resolve_profile", lambda name: profile)
    reached = threading.Event()
    feed = client.feed_line

    def observe(stream, line):
        feed(stream, line)
        if line == "end of injected chat":
            reached.set()

    monkeypatch.setattr(client, "feed_line", observe)
    factory = _SelectorFactory()
    manager = agent_core.SessionManager(selector_factory=factory, receive_dir=tmp_path,
                                        reconnect_delay=.01)
    try:
        manager.discover()
        opened = manager.open("ble:a", profile="chatter", wait_connected_ms=500)
        before = client.controller_status()
        transport = factory.transports["ble:a"]
        for line in [*USER_LINES, "end of injected chat"]:
            transport.reads.put(ReceivedChunk("chat", (line + "\n").encode()))
        assert reached.wait(1)
        assert client.controller_status() == before
        assert client.pending[ticket.request] is ticket
        assert node.outstanding == {ticket.request}
        assert manager.status(opened["session"])["file_transfer_supported"] is True
    finally:
        manager.close_all()
        client.close()


def test_lifecycle_regressions_remain_in_full_local_and_workflow_collection(pytestconfig):
    import fnmatch
    from pathlib import Path
    import re

    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github/workflows/ci.yml").read_text()
    assert re.search(r"- name: Tests\n\s+run: pytest -q(?:\n|$)", workflow)
    assert pytestconfig.getini("testpaths") == ["tests"]
    assert any(fnmatch.fnmatch(Path(__file__).name, pattern)
               for pattern in pytestconfig.getini("python_files"))
    assert not pytestconfig.getini("addopts")
