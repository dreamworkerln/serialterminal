from dataclasses import dataclass
import json
import queue
import time

import pytest

from serialterminal.agent import AgentError, AgentProtocol, SessionManager
from serialterminal.runlog import RunLog, default_log_path
from serialterminal.transports.base import ReceivedChunk, Transport, TransportError


@dataclass(frozen=True)
class FakeCandidate:
    kind: str
    key: str
    label: str
    detail: str
    identity: object = None


class FakeTransport(Transport):
    def __init__(self, key, streams=("main",)):
        self.key = key
        self.streams = streams
        self.connected = False
        self.writes = []
        self.reads = queue.Queue()

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


class FakeSelector:
    def __init__(self, owner, scope, baud, scan_seconds):
        self.owner = owner
        self.scope = scope
        self.baud = baud
        self.scan_seconds = scan_seconds

    def discover(self):
        return list(self.owner.candidates)

    def make_transport(self, candidate):
        streams = ("chat", "telemetry") if candidate.kind == "ble" else ("main",)
        transport = FakeTransport(candidate.key, streams=streams)
        self.owner.transports[candidate.key] = transport
        return transport


class FakeSelectorFactory:
    def __init__(self):
        self.candidates = [
            FakeCandidate("ble", "ble:a", "BLE A", "AA"),
            FakeCandidate("serial", "serial:b", "SERIAL B", "/dev/fake"),
        ]
        self.transports = {}

    def __call__(self, scope, baud, scan_seconds):
        return FakeSelector(self, scope, baud, scan_seconds)


def _wait_until(predicate, timeout=1.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def test_manager_discovers_opens_multiple_sessions_and_auto_ids():
    factory = FakeSelectorFactory()
    manager = SessionManager(selector_factory=factory, reconnect_delay=0.01)
    try:
        discovered = manager.discover()
        assert [item["key"] for item in discovered["devices"]] == [
            "ble:a",
            "serial:b",
        ]

        first = manager.open("ble:a", wait_connected_ms=500)
        second = manager.open("serial:b", wait_connected_ms=500)
        assert first["session"] != second["session"]
        assert first["state"] == "connected"
        assert first["streams"] == ["chat", "telemetry"]
        assert second["streams"] == ["main"]

        assert _wait_until(lambda: factory.transports["ble:a"].writes == [b"/id\n"])
        assert _wait_until(lambda: factory.transports["serial:b"].writes == [b"/id\n"])
        assert len(manager.list_sessions()["sessions"]) == 2

        with pytest.raises(AgentError) as caught:
            manager.open("ble:a", wait_connected_ms=0)
        assert caught.value.code == "device_busy"
    finally:
        manager.close_all()


def test_send_line_raw_bytes_and_cursor_rx_events():
    factory = FakeSelectorFactory()
    manager = SessionManager(selector_factory=factory, reconnect_delay=0.01)
    try:
        manager.discover()
        opened = manager.open("ble:a", wait_connected_ms=500)
        session_id = opened["session"]
        cursor = opened["latest_seq"]
        transport = factory.transports["ble:a"]

        line = manager.send_line(session_id, "hello")
        raw = manager.send_bytes(session_id, b"\x14\x31")
        assert _wait_until(
            lambda: transport.writes[-2:] == [b"hello\n", b"\x14\x31"]
        )
        assert line["tx_id"] != raw["tx_id"]

        transport.reads.put(ReceivedChunk("chat", "привет\n".encode("utf-8")))
        received = manager.events(
            session_id,
            after_seq=cursor,
            timeout_ms=500,
            streams=["chat"],
            kinds=["rx"],
        )
        assert received["timed_out"] is False
        assert len(received["events"]) == 1
        event = received["events"][0]
        assert event["stream"] == "chat"
        assert event["text"] == "привет\n"
        assert event["data_b64"] == "0L/RgNC40LLQtdGCCg=="

        after = event["seq"]
        timeout_result = manager.events(
            session_id,
            after_seq=after,
            timeout_ms=30,
            kinds=["rx"],
        )
        assert timeout_result["events"] == []
        assert timeout_result["timed_out"] is True
    finally:
        manager.close_all()


def test_protocol_returns_structured_errors_and_logs_json(tmp_path):
    factory = FakeSelectorFactory()
    log_path = tmp_path / "agent.log"
    with RunLog(log_path) as run_log:
        manager = SessionManager(
            selector_factory=factory,
            run_log=run_log,
            reconnect_delay=0.01,
        )
        protocol = AgentProtocol(manager, run_log=run_log)
        try:
            invalid_json = json.loads(protocol.process_line("{bad json\n"))
            assert invalid_json["ok"] is False
            assert invalid_json["error"]["code"] == "invalid_json"

            unknown = json.loads(
                protocol.process_line('{"id":7,"op":"does_not_exist"}\n')
            )
            assert unknown == {
                "error": {
                    "code": "unknown_operation",
                    "message": "unknown operation: does_not_exist",
                },
                "id": 7,
                "ok": False,
            }

            discovered = json.loads(
                protocol.process_line('{"id":8,"op":"discover"}\n')
            )
            assert discovered["ok"] is True
            assert len(discovered["result"]["devices"]) == 2
        finally:
            manager.close_all()

    transcript = log_path.read_text()
    assert "[AGENT REQUEST]" in transcript
    assert "[AGENT RESPONSE]" in transcript
    assert '"op":"discover"' in transcript


def test_session_events_are_written_to_same_agent_log(tmp_path):
    factory = FakeSelectorFactory()
    log_path = tmp_path / "agent.log"
    with RunLog(log_path) as run_log:
        manager = SessionManager(
            selector_factory=factory,
            run_log=run_log,
            reconnect_delay=0.01,
        )
        try:
            manager.discover()
            opened = manager.open("ble:a", wait_connected_ms=500)
            session_id = opened["session"]
            transport = factory.transports["ble:a"]
            manager.send_line(session_id, "hello")
            transport.reads.put(ReceivedChunk("chat", b"reply\n"))
            assert _wait_until(lambda: "reply" in log_path.read_text())
        finally:
            manager.close_all()

    transcript = log_path.read_text()
    assert "[STATE]" in transcript
    assert "[TX]" in transcript
    assert "[RX chat]" in transcript
    assert "reply\\n" in transcript


def test_default_log_paths_are_unique_and_live_under_requested_log_dir(tmp_path):
    log_dir = tmp_path / "logs"
    first = default_log_path(log_dir=log_dir)
    second = default_log_path(log_dir=log_dir)

    assert first.parent == log_dir
    assert second.parent == log_dir
    assert first != second
    assert first.name.startswith("serialterminal-")
