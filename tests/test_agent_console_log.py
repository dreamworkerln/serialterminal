from dataclasses import dataclass
import io
import json
import queue
import time

from serialterminal.agent import SessionManager, run_agent
from serialterminal.runlog import RunLog
from serialterminal.transports.base import ReceivedChunk, Transport, TransportError


@dataclass(frozen=True)
class _Candidate:
    kind: str
    key: str
    label: str
    detail: str
    identity: object = None


class _Transport(Transport):
    def __init__(self, key, streams):
        self.key = key
        self.streams = streams
        self.connected = False
        self.reads = queue.Queue()
        self.writes = []

    @property
    def is_connected(self):
        return self.connected

    @property
    def device_key(self):
        return self.key

    @property
    def description(self):
        return f"fake:{self.key}"

    @property
    def stream_capabilities(self):
        return self.streams

    def connect(self):
        self.connected = True
        return True

    def disconnect(self):
        self.connected = False

    def read_chunk(self, size=512):
        if not self.connected:
            raise TransportError("not connected")
        try:
            return self.reads.get(timeout=0.02)
        except queue.Empty:
            return ReceivedChunk(self.streams[0], b"")

    def read(self, size=512):
        return self.read_chunk(size).data

    def write(self, data):
        if not self.connected:
            raise TransportError("not connected")
        self.writes.append(bytes(data))


class _Selector:
    def __init__(self, owner):
        self.owner = owner

    def discover(self):
        return list(self.owner.candidates)

    def make_transport(self, candidate):
        streams = ("chat", "telemetry") if candidate.kind == "ble" else ("main",)
        transport = _Transport(candidate.key, streams)
        self.owner.transports[candidate.key] = transport
        return transport


class _SelectorFactory:
    def __init__(self):
        self.candidates = [
            _Candidate("ble", "ble:a", "BLE A", "AA"),
            _Candidate("serial", "serial:b", "SERIAL B", "/dev/fake"),
        ]
        self.transports = {}

    def __call__(self, scope, baud, scan_seconds):
        return _Selector(self)


def _wait_until(predicate, timeout=1.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def test_agent_runlog_creates_companion_console_file(tmp_path):
    raw_path = tmp_path / "serialterminal-test.log"
    with RunLog(raw_path) as run_log:
        assert run_log.console_path == tmp_path / "serialterminal-test.console.log"
        assert run_log.console_path.exists()


def test_agent_ready_metadata_records_both_log_paths(tmp_path):
    raw_path = tmp_path / "agent.log"
    assert run_agent(
        log_path=str(raw_path),
        stdin=io.StringIO(""),
        stdout=io.StringIO(),
    ) == 0

    ready = None
    for line in raw_path.read_text().splitlines():
        if "[AGENT] " in line:
            ready = json.loads(line.split("[AGENT] ", 1)[1])
            break
    assert ready == {
        "console_log_path": str(tmp_path / "agent.console.log"),
        "event": "ready",
        "log_path": str(raw_path),
    }


def test_console_log_tracks_send_line_and_chunked_human_rx_but_not_ble_telemetry(tmp_path):
    factory = _SelectorFactory()
    raw_path = tmp_path / "agent.log"
    with RunLog(raw_path) as run_log:
        manager = SessionManager(
            run_log=run_log,
            selector_factory=factory,
            reconnect_delay=0.01,
        )
        try:
            manager.discover()
            opened = manager.open("ble:a", auto_id=False, wait_connected_ms=500)
            session_id = opened["session"]
            transport = factory.transports["ble:a"]

            manager.send_line(session_id, "/both")
            transport.reads.put(ReceivedChunk("chat", b"[SYS] OUT"))
            transport.reads.put(ReceivedChunk("chat", b"PUT BOTH\n"))
            transport.reads.put(ReceivedChunk("telemetry", b"MACHINE ONLY\n"))
            transport.reads.put(ReceivedChunk("chat", b"RX ACK visible-in-both\n"))
            transport.reads.put(ReceivedChunk("chat", b"> radio-check-1B44-780\n"))
            transport.reads.put(
                ReceivedChunk("chat", b"< [-13/+10 Q100] radio-check-1B44-780\n")
            )

            assert _wait_until(
                lambda: "< [-13/+10 Q100] radio-check-1B44-780"
                in run_log.console_path.read_text()
            )
        finally:
            manager.close_all()

    console = raw_path.with_name("agent.console.log").read_text()
    assert f"[{session_id}] [I] /both" in console
    assert f"[{session_id}] [O] [SYS] OUTPUT BOTH" in console
    assert f"[{session_id}] [O] RX ACK visible-in-both" in console
    assert f"[{session_id}] [O] > radio-check-1B44-780" in console
    assert f"[{session_id}] [O] < [-13/+10 Q100] radio-check-1B44-780" in console
    assert "MACHINE ONLY" not in console

    forensic = raw_path.read_text()
    assert "[RX chat]" in forensic
    assert "[RX telemetry]" in forensic
    assert "[RX LINE " not in forensic
    assert "[RX PARTIAL " not in forensic


def test_console_log_keeps_session_ids_and_common_chronological_file(tmp_path):
    factory = _SelectorFactory()
    raw_path = tmp_path / "agent.log"
    with RunLog(raw_path) as run_log:
        manager = SessionManager(
            run_log=run_log,
            selector_factory=factory,
            reconnect_delay=0.01,
        )
        try:
            manager.discover()
            first = manager.open("ble:a", auto_id=False, wait_connected_ms=500)
            second = manager.open("serial:b", auto_id=False, wait_connected_ms=500)
            s1 = first["session"]
            s2 = second["session"]

            manager.send_line(s1, "one")
            manager.send_line(s2, "two")
            factory.transports["serial:b"].reads.put(ReceivedChunk("main", b"reply-two\n"))
            factory.transports["ble:a"].reads.put(ReceivedChunk("chat", b"reply-one\n"))
            assert _wait_until(
                lambda: "reply-one" in run_log.console_path.read_text()
                and "reply-two" in run_log.console_path.read_text()
            )
        finally:
            manager.close_all()

    lines = raw_path.with_name("agent.console.log").read_text().splitlines()
    assert any(f"[{s1}] [I] one" in line for line in lines)
    assert any(f"[{s2}] [I] two" in line for line in lines)
    assert any(f"[{s1}] [O] reply-one" in line for line in lines)
    assert any(f"[{s2}] [O] reply-two" in line for line in lines)
