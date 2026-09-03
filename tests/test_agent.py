from dataclasses import dataclass
import io
import json
import queue
import threading
import time

import pytest

from serialterminal.agent import AgentError, AgentProtocol, SessionManager, run_agent
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


class _QueueInput:
    def __init__(self):
        self._lines = queue.Queue()

    def put(self, line):
        self._lines.put(line)

    def close(self):
        self._lines.put(None)

    def __iter__(self):
        return self

    def __next__(self):
        line = self._lines.get()
        if line is None:
            raise StopIteration
        return line


class _BlockingWaitManager:
    def __init__(self, **kwargs):
        self.wait_started = threading.Event()
        self.wait_release = threading.Event()
        self.cancelled = threading.Event()

    def wait_events(self, cursors, *, timeout_ms=0, streams=None, kinds=None):
        self.wait_started.set()
        self.wait_release.wait(timeout=2.0)
        if self.cancelled.is_set():
            raise AgentError("agent_stopping", "agent process is stopping")
        return {
            "events": [],
            "cursors": dict(cursors),
            "timed_out": True,
        }

    def status(self, session_id):
        return {
            "session": session_id,
            "connected": True,
            "state": "connected",
        }

    def cancel_waits(self):
        self.cancelled.set()
        self.wait_release.set()

    def close_all(self):
        pass


def _wait_until(predicate, timeout=1.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def _jsonl_responses(output):
    return [
        json.loads(line)
        for line in output.getvalue().splitlines()
        if line.strip()
    ]


def _start_blocking_agent(monkeypatch, tmp_path):
    import serialterminal.agent as agent_module

    holder = {}

    def manager_factory(**kwargs):
        manager = _BlockingWaitManager(**kwargs)
        holder["manager"] = manager
        return manager

    monkeypatch.setattr(agent_module, "SessionManager", manager_factory)
    input_stream = _QueueInput()
    output_stream = io.StringIO()
    thread = threading.Thread(
        target=run_agent,
        kwargs={
            "log_path": str(tmp_path / "agent.log"),
            "stdin": input_stream,
            "stdout": output_stream,
        },
    )
    thread.start()
    assert _wait_until(lambda: "manager" in holder)
    return holder["manager"], input_stream, output_stream, thread


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


def test_wait_events_wakes_for_one_session():
    factory = FakeSelectorFactory()
    manager = SessionManager(selector_factory=factory, reconnect_delay=0.01)
    try:
        manager.discover()
        opened = manager.open("ble:a", auto_id=False, wait_connected_ms=500)
        session_id = opened["session"]
        cursor = opened["latest_seq"]
        result = {}

        def wait_for_rx():
            result.update(
                manager.wait_events(
                    {session_id: cursor},
                    timeout_ms=500,
                    kinds=["rx"],
                )
            )

        waiter = threading.Thread(target=wait_for_rx)
        waiter.start()
        factory.transports["ble:a"].reads.put(ReceivedChunk("chat", b"echo\n"))
        waiter.join(timeout=1.0)

        assert not waiter.is_alive()
        assert result["timed_out"] is False
        assert result["events"][0]["session"] == session_id
        assert result["events"][0]["kind"] == "rx"
        assert result["events"][0]["text"] == "echo\n"
        assert result["cursors"][session_id] == result["events"][0]["seq"]
    finally:
        manager.close_all()


def test_wait_events_wakes_for_either_of_two_sessions():
    factory = FakeSelectorFactory()
    manager = SessionManager(selector_factory=factory, reconnect_delay=0.01)
    try:
        manager.discover()
        first = manager.open("ble:a", auto_id=False, wait_connected_ms=500)
        second = manager.open("serial:b", auto_id=False, wait_connected_ms=500)
        cursors = {
            first["session"]: first["latest_seq"],
            second["session"]: second["latest_seq"],
        }
        result = {}

        def wait_for_rx():
            result.update(
                manager.wait_events(cursors, timeout_ms=500, kinds=["rx"])
            )

        waiter = threading.Thread(target=wait_for_rx)
        waiter.start()
        factory.transports["serial:b"].reads.put(ReceivedChunk("main", b"from-b\n"))
        waiter.join(timeout=1.0)

        assert not waiter.is_alive()
        assert result["timed_out"] is False
        assert [event["session"] for event in result["events"]] == [second["session"]]
        assert result["events"][0]["text"] == "from-b\n"
        assert result["cursors"][first["session"]] == cursors[first["session"]]
        assert result["cursors"][second["session"]] > cursors[second["session"]]
    finally:
        manager.close_all()


def test_wait_events_filters_but_advances_cursor_through_inspected_events():
    factory = FakeSelectorFactory()
    manager = SessionManager(selector_factory=factory, reconnect_delay=0.01)
    try:
        manager.discover()
        opened = manager.open("serial:b", auto_id=False, wait_connected_ms=500)
        session_id = opened["session"]
        cursor = opened["latest_seq"]

        manager.send_line(session_id, "hello")
        assert _wait_until(lambda: factory.transports["serial:b"].writes == [b"hello\n"])
        session = manager._get_session(session_id)
        latest = session.latest_event_seq()
        assert latest > cursor

        result = manager.wait_events(
            {session_id: cursor},
            timeout_ms=0,
            kinds=["rx"],
        )

        assert result == {
            "events": [],
            "cursors": {session_id: latest},
            "timed_out": False,
        }
    finally:
        manager.close_all()


def test_wait_events_timeout_and_session_specific_cursor_errors():
    factory = FakeSelectorFactory()
    manager = SessionManager(selector_factory=factory, reconnect_delay=0.01)
    try:
        manager.discover()
        opened = manager.open("serial:b", auto_id=False, wait_connected_ms=500)
        session_id = opened["session"]
        cursor = opened["latest_seq"]

        timed_out = manager.wait_events({session_id: cursor}, timeout_ms=30, kinds=["rx"])
        assert timed_out["events"] == []
        assert timed_out["timed_out"] is True
        assert timed_out["cursors"] == {session_id: cursor}

        session = manager._get_session(session_id)
        for index in range(4100):
            session._record_event("state", state=f"test-{index}")

        with pytest.raises(AgentError) as expired:
            manager.wait_events({session_id: 0})
        assert expired.value.code == "cursor_expired"
        assert expired.value.details["session"] == session_id
        assert expired.value.details["requested_seq"] == 0
        assert expired.value.details["oldest_seq"] > 1

        with pytest.raises(AgentError) as missing:
            manager.wait_events({"missing": 0})
        assert missing.value.code == "unknown_session"
        assert missing.value.details == {"session": "missing"}
    finally:
        manager.close_all()


def test_protocol_dispatches_wait_events(tmp_path):
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
            manager.discover()
            opened = manager.open("ble:a", auto_id=False, wait_connected_ms=500)
            session_id = opened["session"]
            response = json.loads(
                protocol.process_line(
                    json.dumps(
                        {
                            "id": 19,
                            "op": "wait_events",
                            "cursors": {session_id: opened["latest_seq"]},
                            "timeout_ms": 0,
                        }
                    )
                    + "\n"
                )
            )
            assert response == {
                "id": 19,
                "ok": True,
                "result": {
                    "events": [],
                    "cursors": {session_id: opened["latest_seq"]},
                    "timed_out": False,
                },
            }

            missing_id = json.loads(
                protocol.process_line(
                    json.dumps(
                        {
                            "op": "wait_events",
                            "cursors": {session_id: opened["latest_seq"]},
                        }
                    )
                    + "\n"
                )
            )
            assert missing_id["ok"] is False
            assert missing_id["error"]["code"] == "invalid_request"
        finally:
            manager.close_all()


def test_agent_accepts_command_while_wait_events_is_pending(monkeypatch, tmp_path):
    manager, input_stream, output_stream, thread = _start_blocking_agent(
        monkeypatch, tmp_path
    )
    try:
        input_stream.put(
            '{"id":100,"op":"wait_events","cursors":{"s1":0},"timeout_ms":5000}\n'
        )
        assert manager.wait_started.wait(timeout=1.0)

        input_stream.put('{"id":101,"op":"status","session":"s1"}\n')
        assert _wait_until(
            lambda: any(
                response.get("id") == 101
                for response in _jsonl_responses(output_stream)
            )
        )

        responses = _jsonl_responses(output_stream)
        assert [response["id"] for response in responses] == [101]

        manager.wait_release.set()
        assert _wait_until(lambda: len(_jsonl_responses(output_stream)) == 2)
        responses = _jsonl_responses(output_stream)
        assert [response["id"] for response in responses] == [101, 100]
        assert responses[0]["result"]["state"] == "connected"
        assert responses[1]["ok"] is True
    finally:
        manager.wait_release.set()
        input_stream.close()
        thread.join(timeout=1.0)
        assert not thread.is_alive()


def test_agent_rejects_request_id_reused_by_pending_wait(monkeypatch, tmp_path):
    manager, input_stream, output_stream, thread = _start_blocking_agent(
        monkeypatch, tmp_path
    )
    try:
        input_stream.put(
            '{"id":7,"op":"wait_events","cursors":{"s1":0},"timeout_ms":5000}\n'
        )
        assert manager.wait_started.wait(timeout=1.0)

        input_stream.put('{"id":7,"op":"status","session":"s1"}\n')
        assert _wait_until(
            lambda: any(
                response.get("error", {}).get("code") == "request_id_busy"
                for response in _jsonl_responses(output_stream)
            )
        )

        busy = _jsonl_responses(output_stream)[0]
        assert busy["id"] == 7
        assert busy["ok"] is False
        assert busy["error"]["code"] == "request_id_busy"
        assert busy["error"]["details"] == {"id": 7}

        manager.wait_release.set()
        assert _wait_until(lambda: len(_jsonl_responses(output_stream)) == 2)
        responses = _jsonl_responses(output_stream)
        assert responses[1]["id"] == 7
        assert responses[1]["ok"] is True
    finally:
        manager.wait_release.set()
        input_stream.close()
        thread.join(timeout=1.0)
        assert not thread.is_alive()


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