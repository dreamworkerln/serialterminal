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
        self.profile = None

    def discover(self):
        return list(self.owner.candidates)

    def make_transport(self, candidate):
        profile_name = getattr(self.profile, "name", "generic")
        streams = (
            ("chat", "telemetry")
            if candidate.kind == "ble" and profile_name == "chatter"
            else ("main",)
        )
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


class _BlockingObserveManager:
    def __init__(self, **kwargs):
        self.observe_started = threading.Event()
        self.observe_release = threading.Event()
        self.cancelled = threading.Event()

    def observe(self, cursors, *, timeout_ms=0, include_events=False):
        self.observe_started.set()
        self.observe_release.wait(timeout=2.0)
        if self.cancelled.is_set():
            raise AgentError("agent_stopping", "agent process is stopping")
        result = {
            "lines": [],
            "cursors": dict(cursors),
            "timed_out": True,
        }
        if include_events:
            result["events"] = []
        return result

    def status(self, session_id):
        return {
            "session": session_id,
            "connected": True,
            "state": "connected",
        }

    def cancel_observes(self):
        self.cancelled.set()
        self.observe_release.set()

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
        manager = _BlockingObserveManager(**kwargs)
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


def test_manager_open_defaults_to_generic_profile_without_preamble():
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
        assert first["streams"] == ["main"]
        assert second["streams"] == ["main"]
        assert first["profile"] == "generic"
        assert second["profile"] == "generic"
        assert "auto_id" not in first
        assert "auto_id" not in second
        assert factory.transports["ble:a"].writes == []
        assert factory.transports["serial:b"].writes == []
        assert len(manager.list_sessions()["sessions"]) == 2

        with pytest.raises(AgentError) as caught:
            manager.open("ble:a", wait_connected_ms=0)
        assert caught.value.code == "device_busy"
    finally:
        manager.close_all()


def test_manager_chatter_profile_preserves_connect_preamble_and_ble_streams():
    factory = FakeSelectorFactory()
    manager = SessionManager(selector_factory=factory, reconnect_delay=0.01)
    try:
        manager.discover()
        first = manager.open("ble:a", profile="chatter", wait_connected_ms=500)
        second = manager.open("serial:b", profile="chatter", wait_connected_ms=500)

        assert first["profile"] == "chatter"
        assert first["streams"] == ["chat", "telemetry"]
        assert "auto_id" not in first
        assert second["profile"] == "chatter"
        assert second["streams"] == ["main"]
        assert "auto_id" not in second
        assert _wait_until(lambda: factory.transports["ble:a"].writes == [b"/id\n"])
        assert _wait_until(lambda: factory.transports["serial:b"].writes == [b"/id\n"])
        assert manager.status(first["session"])["profile"] == "chatter"
        assert manager.status(second["session"])["profile"] == "chatter"
    finally:
        manager.close_all()


def test_protocol_rejects_removed_auto_id_field(tmp_path):
    factory = FakeSelectorFactory()
    log_path = tmp_path / "agent.log"
    with RunLog(log_path) as run_log:
        manager = SessionManager(
            selector_factory=factory,
            run_log=run_log,
            reconnect_delay=0.01,
        )
        protocol = AgentProtocol(manager, run_log=run_log)
        manager.discover()
        response = protocol.handle(
            {
                "id": 3,
                "op": "open",
                "device_key": "ble:a",
                "profile": "chatter",
                "auto_id": False,
            }
        )
        assert response["ok"] is False
        assert response["error"]["code"] == "invalid_request"



def test_observe_one_session_defaults_to_lines_and_can_include_raw_events():
    factory = FakeSelectorFactory()
    manager = SessionManager(selector_factory=factory, reconnect_delay=0.01)
    try:
        manager.discover()
        opened = manager.open(
            "ble:a",
            profile="chatter",
            wait_connected_ms=500,
        )
        session_id = opened["session"]
        cursor = opened["latest_seq"]
        transport = factory.transports["ble:a"]
        payload = "привет\n".encode("utf-8")
        transport.reads.put(ReceivedChunk("chat", payload))

        observed = manager.observe({session_id: cursor}, timeout_ms=500)

        assert observed["timed_out"] is False
        assert "events" not in observed
        assert len(observed["lines"]) == 1
        line = observed["lines"][0]
        assert line["session"] == session_id
        assert line["stream"] == "chat"
        assert line["text"] == "привет"
        assert observed["cursors"][session_id] == line["seq_last"]

        forensic = manager.observe(
            {session_id: cursor},
            timeout_ms=0,
            include_events=True,
        )
        assert len(forensic["events"]) == 1
        event = forensic["events"][0]
        assert event["session"] == session_id
        assert event["kind"] == "rx"
        assert event["stream"] == "chat"
        assert event["text"] == "привет\n"
        assert event["data_b64"] == "0L/RgNC40LLQtdGCCg=="
        assert forensic["lines"] == observed["lines"]
        assert forensic["cursors"] == observed["cursors"]
    finally:
        manager.close_all()


def test_observe_two_sessions_wakes_for_either_session():
    factory = FakeSelectorFactory()
    manager = SessionManager(selector_factory=factory, reconnect_delay=0.01)
    try:
        manager.discover()
        first = manager.open(
            "ble:a",
            profile="chatter",
            wait_connected_ms=500,
        )
        second = manager.open("serial:b", wait_connected_ms=500)
        cursors = {
            first["session"]: first["latest_seq"],
            second["session"]: second["latest_seq"],
        }
        result = {}

        def observe():
            result.update(manager.observe(cursors, timeout_ms=500))

        observer = threading.Thread(target=observe)
        observer.start()
        factory.transports["serial:b"].reads.put(ReceivedChunk("main", b"from-b\n"))
        observer.join(timeout=1.0)

        assert not observer.is_alive()
        assert result["timed_out"] is False
        assert "events" not in result
        assert result["lines"] == [
            {
                "session": second["session"],
                "stream": "main",
                "seq_first": result["lines"][0]["seq_first"],
                "seq_last": result["lines"][0]["seq_last"],
                "text": "from-b",
            }
        ]
        assert result["cursors"][first["session"]] == cursors[first["session"]]
        assert result["cursors"][second["session"]] > cursors[second["session"]]
    finally:
        manager.close_all()


def test_observe_returns_full_line_started_before_input_cursor():
    factory = FakeSelectorFactory()
    manager = SessionManager(selector_factory=factory, reconnect_delay=0.01)
    try:
        manager.discover()
        opened = manager.open("serial:b", wait_connected_ms=500)
        session_id = opened["session"]
        session = manager._get_session(session_id)
        first = session._record_event(
            "rx", stream="main", data=b"DELIVERY WA", text="DELIVERY WA"
        )
        first_result = manager.observe({session_id: opened["latest_seq"]})
        assert "events" not in first_result
        assert first_result["cursors"][session_id] == first.seq
        assert first_result["lines"] == []

        second = session._record_event(
            "rx", stream="main", data=b"IT_ACK\n", text="IT_ACK\n"
        )
        result = manager.observe({session_id: first.seq})

        assert "events" not in result
        assert result["cursors"][session_id] == second.seq
        assert result["lines"] == [
            {
                "session": session_id,
                "stream": "main",
                "seq_first": first.seq,
                "seq_last": second.seq,
                "text": "DELIVERY WAIT_ACK",
            }
        ]
    finally:
        manager.close_all()


def test_observe_timeout_and_session_specific_cursor_errors():
    factory = FakeSelectorFactory()
    manager = SessionManager(selector_factory=factory, reconnect_delay=0.01)
    try:
        manager.discover()
        opened = manager.open("serial:b", wait_connected_ms=500)
        session_id = opened["session"]
        cursor = opened["latest_seq"]

        immediate = manager.observe({session_id: cursor}, timeout_ms=0)
        assert immediate == {
            "lines": [],
            "cursors": {session_id: cursor},
            "timed_out": False,
        }

        timed_out = manager.observe({session_id: cursor}, timeout_ms=30)
        assert timed_out == {
            "lines": [],
            "cursors": {session_id: cursor},
            "timed_out": True,
        }

        forensic_empty = manager.observe(
            {session_id: cursor},
            timeout_ms=0,
            include_events=True,
        )
        assert forensic_empty == {
            "lines": [],
            "cursors": {session_id: cursor},
            "timed_out": False,
            "events": [],
        }

        with pytest.raises(AgentError) as negative:
            manager.observe({session_id: cursor}, timeout_ms=-1)
        assert negative.value.code == "invalid_timeout"

        session = manager._get_session(session_id)
        for index in range(4100):
            session._record_event("state", state=f"test-{index}")

        with pytest.raises(AgentError) as expired:
            manager.observe({session_id: 0})
        assert expired.value.code == "cursor_expired"
        assert expired.value.details["session"] == session_id
        assert expired.value.details["requested_seq"] == 0
        assert expired.value.details["oldest_seq"] > 1

        with pytest.raises(AgentError) as missing:
            manager.observe({"missing": 0})
        assert missing.value.code == "unknown_session"
        assert missing.value.details == {"session": "missing"}
    finally:
        manager.close_all()


def test_protocol_dispatches_observe_and_rejects_old_operations(tmp_path):
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
            opened = manager.open(
                "ble:a",
                profile="chatter",
                wait_connected_ms=500,
            )
            session_id = opened["session"]
            default_response = json.loads(
                protocol.process_line(
                    json.dumps(
                        {
                            "id": 19,
                            "op": "observe",
                            "cursors": {session_id: opened["latest_seq"]},
                            "timeout_ms": 0,
                        }
                    )
                    + "\n"
                )
            )
            assert default_response == {
                "id": 19,
                "ok": True,
                "result": {
                    "lines": [],
                    "cursors": {session_id: opened["latest_seq"]},
                    "timed_out": False,
                },
            }

            forensic_response = json.loads(
                protocol.process_line(
                    json.dumps(
                        {
                            "id": 20,
                            "op": "observe",
                            "cursors": {session_id: opened["latest_seq"]},
                            "timeout_ms": 0,
                            "include_events": True,
                        }
                    )
                    + "\n"
                )
            )
            assert forensic_response["ok"] is True
            assert forensic_response["result"]["events"] == []

            invalid_include_events = json.loads(
                protocol.process_line(
                    json.dumps(
                        {
                            "id": 21,
                            "op": "observe",
                            "cursors": {session_id: opened["latest_seq"]},
                            "include_events": 1,
                        }
                    )
                    + "\n"
                )
            )
            assert invalid_include_events["ok"] is False
            assert invalid_include_events["error"]["code"] == "invalid_request"

            missing_id = json.loads(
                protocol.process_line(
                    json.dumps(
                        {
                            "op": "observe",
                            "cursors": {session_id: opened["latest_seq"]},
                        }
                    )
                    + "\n"
                )
            )
            assert missing_id["ok"] is False
            assert missing_id["error"]["code"] == "invalid_request"

            for old_op in ("events", "wait_events"):
                old = json.loads(
                    protocol.process_line(
                        json.dumps({"id": 30, "op": old_op}) + "\n"
                    )
                )
                assert old["ok"] is False
                assert old["error"]["code"] == "unknown_operation"
        finally:
            manager.close_all()

def test_observe_default_avoids_raw_event_payload_amplification(tmp_path):
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
            opened = manager.open(
                "ble:a",
                profile="chatter",
                wait_connected_ms=500,
            )
            session_id = opened["session"]
            cursor = opened["latest_seq"]
            session = manager._get_session(session_id)

            for _ in range(64):
                session._record_event(
                    "rx",
                    stream="chat",
                    data=b"0123456789abcdef",
                    text="0123456789abcdef",
                )
            session._record_event(
                "rx",
                stream="chat",
                data=b"\n",
                text="\n",
            )

            default_response = protocol.handle(
                {
                    "id": 1,
                    "op": "observe",
                    "cursors": {session_id: cursor},
                }
            )
            forensic_response = protocol.handle(
                {
                    "id": 2,
                    "op": "observe",
                    "cursors": {session_id: cursor},
                    "include_events": True,
                }
            )

            default_bytes = len(
                json.dumps(
                    default_response,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8")
            )
            forensic_bytes = len(
                json.dumps(
                    forensic_response,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8")
            )

            assert "events" not in default_response["result"]
            assert len(forensic_response["result"]["events"]) == 65
            assert default_response["result"]["lines"] == forensic_response["result"]["lines"]
            assert default_response["result"]["cursors"] == forensic_response["result"]["cursors"]
            assert forensic_bytes > default_bytes * 3
        finally:
            manager.close_all()


def test_protocol_open_defaults_generic_and_accepts_chatter_profile(tmp_path):
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
            generic = protocol.handle(
                {
                    "id": 1,
                    "op": "open",
                    "device_key": "serial:b",
                    "wait_connected_ms": 500,
                }
            )
            assert generic["ok"] is True
            assert generic["result"]["profile"] == "generic"
            assert "auto_id" not in generic["result"]
            manager.close(generic["result"]["session"])

            chatter = protocol.handle(
                {
                    "id": 2,
                    "op": "open",
                    "device_key": "serial:b",
                    "profile": "chatter",
                    "wait_connected_ms": 500,
                }
            )
            assert chatter["ok"] is True
            assert chatter["result"]["profile"] == "chatter"
            assert "auto_id" not in chatter["result"]
        finally:
            manager.close_all()


def test_agent_accepts_command_while_observe_is_pending(monkeypatch, tmp_path):
    manager, input_stream, output_stream, thread = _start_blocking_agent(
        monkeypatch, tmp_path
    )
    try:
        input_stream.put(
            '{"id":100,"op":"observe","cursors":{"s1":0},"timeout_ms":5000}\n'
        )
        assert manager.observe_started.wait(timeout=1.0)

        input_stream.put('{"id":101,"op":"status","session":"s1"}\n')
        assert _wait_until(
            lambda: any(
                response.get("id") == 101
                for response in _jsonl_responses(output_stream)
            )
        )

        responses = _jsonl_responses(output_stream)
        assert [response["id"] for response in responses] == [101]

        manager.observe_release.set()
        assert _wait_until(lambda: len(_jsonl_responses(output_stream)) == 2)
        responses = _jsonl_responses(output_stream)
        assert [response["id"] for response in responses] == [101, 100]
        assert responses[0]["result"]["state"] == "connected"
        assert responses[1]["ok"] is True
    finally:
        manager.observe_release.set()
        input_stream.close()
        thread.join(timeout=1.0)
        assert not thread.is_alive()


def test_agent_rejects_request_id_reused_by_pending_observe(monkeypatch, tmp_path):
    manager, input_stream, output_stream, thread = _start_blocking_agent(
        monkeypatch, tmp_path
    )
    try:
        input_stream.put(
            '{"id":7,"op":"observe","cursors":{"s1":0},"timeout_ms":5000}\n'
        )
        assert manager.observe_started.wait(timeout=1.0)

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

        manager.observe_release.set()
        assert _wait_until(lambda: len(_jsonl_responses(output_stream)) == 2)
        responses = _jsonl_responses(output_stream)
        assert responses[1]["id"] == 7
        assert responses[1]["ok"] is True
    finally:
        manager.observe_release.set()
        input_stream.close()
        thread.join(timeout=1.0)
        assert not thread.is_alive()


def test_agent_shutdown_cancels_pending_observe(monkeypatch, tmp_path):
    manager, input_stream, output_stream, thread = _start_blocking_agent(
        monkeypatch, tmp_path
    )
    input_stream.put(
        '{"id":55,"op":"observe","cursors":{"s1":0},"timeout_ms":60000}\n'
    )
    assert manager.observe_started.wait(timeout=1.0)

    input_stream.close()
    thread.join(timeout=1.0)

    assert not thread.is_alive()
    assert manager.cancelled.is_set()
    responses = _jsonl_responses(output_stream)
    assert responses == [
        {
            "id": 55,
            "ok": False,
            "error": {
                "code": "agent_stopping",
                "message": "agent process is stopping",
            },
        }
    ]


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


def test_session_events_are_written_to_same_agent_log_without_line_tags(tmp_path):
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
            opened = manager.open(
                "ble:a",
                profile="chatter",
                wait_connected_ms=500,
            )
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
    assert "[RX LINE " not in transcript
    assert "[RX PARTIAL " not in transcript


def test_default_log_paths_are_unique_and_live_under_requested_log_dir(tmp_path):
    log_dir = tmp_path / "logs"
    first = default_log_path(log_dir=log_dir)
    second = default_log_path(log_dir=log_dir)

    assert first.parent == log_dir
    assert second.parent == log_dir
    assert first != second
    assert first.name.startswith("serialterminal-")
