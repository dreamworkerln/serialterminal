from dataclasses import dataclass
import io
import json
import queue
import threading
import time

import pytest

from serialterminal.agent import AgentError, AgentProtocol, SessionManager, run_agent
from serialterminal.profiles.generic import GenericProfile
from serialterminal.runlog import RunLog
from serialterminal.session import ReceivedChunk
from serialterminal.transports.base import (
    Transport,
    TransportError,
    TransportWriteOutcomeUnknown,
)


@dataclass
class _Candidate:
    kind: str
    key: str
    label: str
    detail: str


class _Transport(Transport):
    def __init__(self, key):
        self.key = key
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
        return ("main",)

    def connect(self):
        self.connected = True
        return True

    def disconnect(self):
        self.connected = False

    def close(self):
        self.connected = False

    def read_chunk(self, size=512):
        if not self.connected:
            raise TransportError("not connected")
        try:
            return self.reads.get(timeout=0.01)
        except queue.Empty:
            return ReceivedChunk("main", b"")

    def read(self, size=512):
        return self.read_chunk(size).data

    def write(self, data):
        if not self.connected:
            raise TransportError("not connected")
        self.writes.append(bytes(data))


class _Selector:
    def __init__(self, owner, scope, baud, scan_seconds):
        self.owner = owner
        self.profile = None

    def discover(self):
        return list(self.owner.candidates)

    def make_transport(self, candidate):
        transport = _Transport(candidate.key)
        self.owner.transports[candidate.key] = transport
        return transport


class _SelectorFactory:
    def __init__(self):
        self.candidates = [
            _Candidate("serial", "serial:a", "A", "/dev/a"),
            _Candidate("serial", "serial:b", "B", "/dev/b"),
            _Candidate("serial", "serial:c", "C", "/dev/c"),
        ]
        self.transports = {}

    def __call__(self, scope, baud, scan_seconds):
        return _Selector(self, scope, baud, scan_seconds)


class _FailingAdapter:
    name = "test.failing"

    def phase_timeout_s(self, phase, coordinate):
        return 1.0

    def prepare(self, phase):
        raise RuntimeError("prepare failed")

    def apply_coordinate(self, coordinate, phase):
        raise AssertionError("not reached")

    def verify_coordinate(self, coordinate, phase):
        raise AssertionError("not reached")

    def start_sample(self, coordinate, repetition, phase):
        raise AssertionError("not reached")

    def wait_sample_settled(
        self,
        coordinate,
        repetition,
        token,
        phase,
    ):
        raise AssertionError("not reached")

    def cleanup(self, phase):
        return None


class _BlockingAdapter:
    name = "test.blocking"

    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()

    def phase_timeout_s(self, phase, coordinate):
        return 1.0

    def prepare(self, phase):
        self.started.set()
        while not self.release.wait(timeout=0.01):
            phase.raise_if_cancelled()

    def apply_coordinate(self, coordinate, phase):
        phase.raise_if_cancelled()

    def verify_coordinate(self, coordinate, phase):
        phase.raise_if_cancelled()

    def start_sample(self, coordinate, repetition, phase):
        phase.raise_if_cancelled()
        return None

    def wait_sample_settled(
        self,
        coordinate,
        repetition,
        token,
        phase,
    ):
        phase.raise_if_cancelled()
        return None

    def cleanup(self, phase):
        return None


def _wait_until(predicate, timeout=1.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.005)
    return predicate()


def _sweep_log_payloads(path):
    payloads = []
    for line in path.read_text(encoding="utf-8").splitlines():
        marker = " [SWEEP] "
        if marker not in line:
            continue
        payloads.append(json.loads(line.split(marker, 1)[1]))
    return payloads


def test_session_mutation_ownership_is_exclusive_but_unrelated_session_is_free(
    monkeypatch,
    tmp_path,
):
    adapters = []

    def factory(context, sessions, plan):
        adapter = _BlockingAdapter()
        adapters.append(adapter)
        return adapter

    monkeypatch.setattr(
        GenericProfile,
        "sweep_adapters",
        lambda self: {"test.blocking": factory},
    )

    selector = _SelectorFactory()
    log_path = tmp_path / "agent.log"
    with RunLog(log_path) as run_log:
        manager = SessionManager(
            selector_factory=selector,
            reconnect_delay=0.01,
            run_log=run_log,
        )
        try:
            manager.discover()
            a = manager.open("serial:a", wait_connected_ms=500)
            b = manager.open("serial:b", wait_connected_ms=500)
            c = manager.open("serial:c", wait_connected_ms=500)
            sessions = [a["session"], b["session"]]
            started = manager.sweep_start(
                "test.blocking",
                sessions,
                {"axes": [], "repetitions": 1},
            )
            sweep_id = started["sweep_id"]
            assert adapters[0].started.wait(timeout=1.0)

            with pytest.raises(AgentError) as second:
                manager.sweep_start(
                    "test.blocking",
                    sessions,
                    {"axes": [], "repetitions": 1},
                )
            assert second.value.code == "sweep_busy"

            before = list(selector.transports["serial:a"].writes)
            with pytest.raises(AgentError) as line_busy:
                manager.send_line(a["session"], "blocked")
            assert line_busy.value.code == "session_busy"
            with pytest.raises(AgentError) as bytes_busy:
                manager.send_bytes(a["session"], b"x")
            assert bytes_busy.value.code == "session_busy"
            with pytest.raises(AgentError) as close_busy:
                manager.close(a["session"])
            assert close_busy.value.code == "session_busy"
            assert selector.transports["serial:a"].writes == before

            assert manager.status(a["session"])["state"] == "connected"
            observed = manager.observe(
                {a["session"]: a["latest_seq"]},
                timeout_ms=0,
            )
            assert observed["timed_out"] is False

            unrelated = manager.send_line(c["session"], "allowed")
            assert unrelated["state"] == "queued"
            assert _wait_until(
                lambda: selector.transports["serial:c"].writes
                == [b"allowed\n"]
            )

            adapters[0].release.set()
            assert _wait_until(
                lambda: manager.sweep_observe(
                    sweep_id,
                    cursor=0,
                    window=100,
                    timeout_ms=0,
                )["state"]
                == "completed"
            )

            allowed_after = manager.send_line(a["session"], "after")
            assert allowed_after["state"] == "queued"
            assert _wait_until(
                lambda: selector.transports["serial:a"].writes
                == [b"after\n"]
            )

            forensic = log_path.read_text(encoding="utf-8")
            assert "[SWEEP]" in forensic
            assert '"sweep_id":"%s"' % sweep_id in forensic
            assert '"event_seq":1' in forensic

            assert manager.sweep_close(sweep_id)["state"] == "closed"
            with pytest.raises(AgentError) as unknown:
                manager.sweep_observe(
                    sweep_id,
                    cursor=0,
                    window=1,
                    timeout_ms=0,
                )
            assert unknown.value.code == "unknown_sweep"
        finally:
            manager.cancel_sweeps()
            manager.close_all()
            manager.join_sweeps(1.0)


def test_sweep_waits_for_prelease_external_tx_before_adapter_prepare(
    monkeypatch,
    tmp_path,
):
    adapters = []

    def factory(context, sessions, plan):
        adapter = _BlockingAdapter()
        adapters.append(adapter)
        return adapter

    monkeypatch.setattr(
        GenericProfile,
        "sweep_adapters",
        lambda self: {"test.blocking": factory},
    )
    selector = _SelectorFactory()
    with RunLog(tmp_path / "agent.log") as run_log:
        manager = SessionManager(
            selector_factory=selector,
            reconnect_delay=0.01,
            run_log=run_log,
        )
        try:
            manager.discover()
            opened = manager.open("serial:a", wait_connected_ms=500)
            transport = selector.transports["serial:a"]
            write_started = threading.Event()
            write_release = threading.Event()
            original_write = transport.write

            def blocked_write(data):
                write_started.set()
                assert write_release.wait(timeout=1.0)
                original_write(data)

            transport.write = blocked_write
            queued = manager.send_line(opened["session"], "before-sweep")
            assert queued["state"] == "queued"
            assert write_started.wait(timeout=1.0)

            sweep_id = manager.sweep_start(
                "test.blocking",
                [opened["session"]],
                {"axes": [], "repetitions": 1},
            )["sweep_id"]
            assert adapters
            assert not adapters[0].started.wait(timeout=0.05)

            write_release.set()
            assert adapters[0].started.wait(timeout=1.0)
            assert transport.writes == [b"before-sweep\n"]

            adapters[0].release.set()
            assert _wait_until(
                lambda: manager.sweep_observe(
                    sweep_id,
                    cursor=0,
                    window=100,
                    timeout_ms=0,
                )["state"]
                == "completed"
            )
        finally:
            write_release.set()
            manager.cancel_sweeps()
            manager.close_all()
            manager.join_sweeps(1.0)


def test_sweep_fails_before_prepare_on_ambiguous_prelease_tx(
    monkeypatch,
    tmp_path,
):
    adapters = []

    def factory(context, sessions, plan):
        adapter = _BlockingAdapter()
        adapters.append(adapter)
        return adapter

    monkeypatch.setattr(
        GenericProfile,
        "sweep_adapters",
        lambda self: {"test.blocking": factory},
    )
    selector = _SelectorFactory()
    with RunLog(tmp_path / "agent.log") as run_log:
        manager = SessionManager(
            selector_factory=selector,
            reconnect_delay=0.01,
            run_log=run_log,
        )
        try:
            manager.discover()
            opened = manager.open("serial:a", wait_connected_ms=500)
            transport = selector.transports["serial:a"]
            original_write = transport.write
            ambiguous = threading.Event()

            def unknown_write(data):
                if not ambiguous.is_set():
                    ambiguous.set()
                    raise TransportWriteOutcomeUnknown("ambiguous pre-sweep write")
                original_write(data)

            transport.write = unknown_write
            queued = manager.send_line(opened["session"], "before-sweep")
            assert queued["state"] == "queued"
            assert ambiguous.wait(timeout=1.0)

            sweep_id = manager.sweep_start(
                "test.blocking",
                [opened["session"]],
                {"axes": [], "repetitions": 1},
            )["sweep_id"]
            assert _wait_until(
                lambda: manager.sweep_observe(
                    sweep_id,
                    cursor=0,
                    window=100,
                    timeout_ms=0,
                )["state"]
                == "failed"
            )
            result = manager.sweep_observe(
                sweep_id,
                cursor=0,
                window=100,
                timeout_ms=0,
            )
            assert result["failure"]["code"] == "session_tx_unknown"
            assert adapters
            assert not adapters[0].started.is_set()
        finally:
            manager.close_all()


def test_sweep_api_events_correlate_with_durable_forensic_records(
    monkeypatch,
    tmp_path,
):
    def factory(context, sessions, plan):
        return _BlockingAdapter()

    monkeypatch.setattr(
        GenericProfile,
        "sweep_adapters",
        lambda self: {"test.blocking": factory},
    )
    selector = _SelectorFactory()
    log_path = tmp_path / "agent.log"
    with RunLog(log_path) as run_log:
        manager = SessionManager(
            selector_factory=selector,
            reconnect_delay=0.01,
            run_log=run_log,
        )
        try:
            manager.discover()
            opened = manager.open(
                "serial:a",
                wait_connected_ms=500,
            )
            started = manager.sweep_start(
                "test.blocking",
                [opened["session"]],
                {"axes": [], "repetitions": 2},
            )
            sweep_id = started["sweep_id"]

            # This adapter blocks in prepare until explicitly released.
            job_adapter = manager._sweep_manager._get(sweep_id).adapter
            assert isinstance(job_adapter, _BlockingAdapter)
            assert job_adapter.started.wait(timeout=1.0)
            job_adapter.release.set()

            terminal = None
            assert _wait_until(
                lambda: manager.sweep_observe(
                    sweep_id,
                    cursor=0,
                    window=100,
                    timeout_ms=0,
                )["state"]
                == "completed"
            )
            terminal = manager.sweep_observe(
                sweep_id,
                cursor=0,
                window=100,
                timeout_ms=0,
            )
            api_events = terminal["events"]
            assert terminal["cursor"] == terminal["head_cursor"]
            assert api_events[-1]["kind"] == "sweep_completed"

            before_close = _sweep_log_payloads(log_path)
            assert [
                payload["event_seq"]
                for payload in before_close
                if payload["sweep_id"] == sweep_id
            ] == [event["seq"] for event in api_events]
            assert [
                payload["kind"]
                for payload in before_close
                if payload["sweep_id"] == sweep_id
            ] == [event["kind"] for event in api_events]

            assert manager.sweep_close(sweep_id)["state"] == "closed"
            after_close = _sweep_log_payloads(log_path)
            assert after_close == before_close
        finally:
            manager.close_all()


def test_sweep_session_acquisition_is_all_or_none(
    monkeypatch,
    tmp_path,
):
    def factory(context, sessions, plan):
        return _BlockingAdapter()

    monkeypatch.setattr(
        GenericProfile,
        "sweep_adapters",
        lambda self: {"test.blocking": factory},
    )
    selector = _SelectorFactory()
    with RunLog(tmp_path / "agent.log") as run_log:
        manager = SessionManager(
            selector_factory=selector,
            reconnect_delay=0.01,
            run_log=run_log,
        )
        try:
            manager.discover()
            a = manager.open("serial:a", wait_connected_ms=500)
            b = manager.open("serial:b", wait_connected_ms=500)
            held = manager._begin_external_mutation(b["session"])
            try:
                with pytest.raises(AgentError) as caught:
                    manager.sweep_start(
                        "test.blocking",
                        [a["session"], b["session"]],
                        {"axes": [], "repetitions": 1},
                    )
                assert caught.value.code == "session_busy"

                # A failed two-session acquire must not leave the first
                # session partially owned by the rejected sweep.
                sent = manager.send_line(a["session"], "still-free")
                assert sent["state"] == "queued"
            finally:
                assert held is not None
                manager._finish_external_mutation(b["session"])
        finally:
            manager.close_all()


def test_failed_sweep_releases_session_mutation_ownership(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        GenericProfile,
        "sweep_adapters",
        lambda self: {
            "test.failing": (
                lambda context, sessions, plan: _FailingAdapter()
            )
        },
    )
    selector = _SelectorFactory()
    with RunLog(tmp_path / "agent.log") as run_log:
        manager = SessionManager(
            selector_factory=selector,
            reconnect_delay=0.01,
            run_log=run_log,
        )
        try:
            manager.discover()
            opened = manager.open(
                "serial:a",
                wait_connected_ms=500,
            )
            sweep_id = manager.sweep_start(
                "test.failing",
                [opened["session"]],
                {"axes": [], "repetitions": 1},
            )["sweep_id"]

            assert _wait_until(
                lambda: manager.sweep_observe(
                    sweep_id,
                    cursor=0,
                    window=100,
                    timeout_ms=0,
                )["state"]
                == "failed"
            )
            sent = manager.send_line(
                opened["session"],
                "after-failure",
            )
            assert sent["state"] == "queued"
        finally:
            manager.close_all()


def test_cancelled_sweep_releases_session_mutation_ownership(
    monkeypatch,
    tmp_path,
):
    adapters = []

    def factory(context, sessions, plan):
        adapter = _BlockingAdapter()
        adapters.append(adapter)
        return adapter

    monkeypatch.setattr(
        GenericProfile,
        "sweep_adapters",
        lambda self: {"test.blocking": factory},
    )
    selector = _SelectorFactory()
    with RunLog(tmp_path / "agent.log") as run_log:
        manager = SessionManager(
            selector_factory=selector,
            reconnect_delay=0.01,
            run_log=run_log,
        )
        try:
            manager.discover()
            opened = manager.open(
                "serial:a",
                wait_connected_ms=500,
            )
            sweep_id = manager.sweep_start(
                "test.blocking",
                [opened["session"]],
                {"axes": [], "repetitions": 1},
            )["sweep_id"]
            assert adapters[0].started.wait(timeout=1.0)

            assert manager.sweep_cancel(sweep_id)["state"] == "cancelling"
            assert _wait_until(
                lambda: manager.sweep_observe(
                    sweep_id,
                    cursor=0,
                    window=100,
                    timeout_ms=0,
                )["state"]
                == "cancelled"
            )
            sent = manager.send_line(
                opened["session"],
                "after-cancel",
            )
            assert sent["state"] == "queued"
        finally:
            manager.close_all()


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("cursor", True, "invalid_sweep_cursor"),
        ("cursor", -1, "invalid_sweep_cursor"),
        ("window", 0, "invalid_sweep_window"),
        ("window", 1.5, "invalid_sweep_window"),
        ("timeout_ms", -1, "invalid_timeout"),
        ("timeout_ms", "100", "invalid_timeout"),
    ],
)
def test_agent_protocol_sweep_observe_rejects_invalid_window_fields(
    monkeypatch,
    tmp_path,
    field,
    value,
    code,
):
    adapters = []

    def factory(context, sessions, plan):
        adapter = _BlockingAdapter()
        adapters.append(adapter)
        return adapter

    monkeypatch.setattr(
        GenericProfile,
        "sweep_adapters",
        lambda self: {"test.blocking": factory},
    )
    selector = _SelectorFactory()
    with RunLog(tmp_path / "agent.log") as run_log:
        manager = SessionManager(
            selector_factory=selector,
            reconnect_delay=0.01,
            run_log=run_log,
        )
        protocol = AgentProtocol(manager, run_log=run_log)
        try:
            manager.discover()
            opened = manager.open(
                "serial:a",
                wait_connected_ms=500,
            )
            sweep_id = manager.sweep_start(
                "test.blocking",
                [opened["session"]],
                {"axes": [], "repetitions": 1},
            )["sweep_id"]
            assert adapters[0].started.wait(timeout=1.0)

            request = {
                "id": 10,
                "op": "sweep_observe",
                "sweep_id": sweep_id,
                "cursor": 0,
                "window": 10,
                "timeout_ms": 0,
            }
            request[field] = value
            response = protocol.handle(request)
            assert response["id"] == 10
            assert response["ok"] is False
            assert response["error"]["code"] == code
        finally:
            manager.cancel_sweeps()
            manager.close_all()
            manager.join_sweeps(1.0)


def test_agent_protocol_reports_failed_job_as_successful_observe_request(
    monkeypatch,
    tmp_path,
):
    def factory(context, sessions, plan):
        return _FailingAdapter()

    monkeypatch.setattr(
        GenericProfile,
        "sweep_adapters",
        lambda self: {"test.failing": factory},
    )
    selector = _SelectorFactory()
    with RunLog(tmp_path / "agent.log") as run_log:
        manager = SessionManager(
            selector_factory=selector,
            reconnect_delay=0.01,
            run_log=run_log,
        )
        protocol = AgentProtocol(manager, run_log=run_log)
        try:
            manager.discover()
            opened = manager.open(
                "serial:a",
                wait_connected_ms=500,
            )
            start = protocol.handle(
                {
                    "id": 1,
                    "op": "sweep_start",
                    "adapter": "test.failing",
                    "sessions": [opened["session"]],
                    "plan": {"axes": [], "repetitions": 1},
                }
            )
            assert start["ok"] is True
            sweep_id = start["result"]["sweep_id"]

            response = None
            assert _wait_until(
                lambda: (
                    (candidate := protocol.handle(
                        {
                            "id": 2,
                            "op": "sweep_observe",
                            "sweep_id": sweep_id,
                            "cursor": 0,
                            "window": 100,
                            "timeout_ms": 0,
                        }
                    ))["ok"]
                    and candidate["result"]["state"] == "failed"
                )
            )
            response = protocol.handle(
                {
                    "id": 3,
                    "op": "sweep_observe",
                    "sweep_id": sweep_id,
                    "cursor": 0,
                    "window": 100,
                    "timeout_ms": 0,
                }
            )
            assert response["ok"] is True
            assert response["result"]["state"] == "failed"
            assert response["result"]["failure"]["code"] == "adapter_failed"
        finally:
            manager.close_all()


class _QueueInput:
    def __init__(self):
        self.lines = queue.Queue()

    def put(self, line):
        self.lines.put(line)

    def close(self):
        self.lines.put(None)

    def __iter__(self):
        return self

    def __next__(self):
        line = self.lines.get()
        if line is None:
            raise StopIteration
        return line


class _BlockingSweepObserveManager:
    def __init__(self, **kwargs):
        self.started = threading.Event()
        self.release = threading.Event()

    def sweep_observe(
        self,
        sweep_id,
        *,
        cursor,
        window,
        timeout_ms,
    ):
        self.started.set()
        self.release.wait(timeout=2.0)
        return {
            "events": [],
            "cursor": cursor,
            "head_cursor": cursor,
            "state": "running",
            "progress": {
                "completed_samples": 0,
                "total_samples": 1,
                "current": None,
            },
            "timed_out": True,
        }

    def status(self, session_id):
        return {
            "session": session_id,
            "state": "connected",
            "connected": True,
        }

    def cancel_observes(self):
        return None

    def cancel_sweeps(self):
        self.release.set()

    def join_sweeps(self, timeout):
        return None

    def close_all(self):
        return None


def _responses(output):
    return [
        json.loads(line)
        for line in output.getvalue().splitlines()
        if line.strip()
    ]


def test_sweep_observe_long_poll_does_not_block_later_ordinary_request(
    monkeypatch,
    tmp_path,
):
    import serialterminal.agent as agent_module

    holder = {}

    def manager_factory(**kwargs):
        manager = _BlockingSweepObserveManager(**kwargs)
        holder["manager"] = manager
        return manager

    monkeypatch.setattr(
        agent_module,
        "SessionManager",
        manager_factory,
    )
    input_stream = _QueueInput()
    output_stream = io.StringIO()
    thread = threading.Thread(
        target=run_agent,
        kwargs={
            "log_path": str(tmp_path / "runner.log"),
            "stdin": input_stream,
            "stdout": output_stream,
        },
    )
    thread.start()
    assert _wait_until(lambda: "manager" in holder)

    input_stream.put(
        json.dumps(
            {
                "id": 1,
                "op": "sweep_observe",
                "sweep_id": "sw1",
                "cursor": 0,
                "window": 100,
                "timeout_ms": 30000,
            }
        )
        + "\n"
    )
    assert holder["manager"].started.wait(timeout=1.0)

    input_stream.put(
        json.dumps(
            {
                "id": 2,
                "op": "status",
                "session": "s1",
            }
        )
        + "\n"
    )
    assert _wait_until(
        lambda: any(
            response.get("id") == 2
            for response in _responses(output_stream)
        )
    )
    assert not any(
        response.get("id") == 1
        for response in _responses(output_stream)
    )

    holder["manager"].release.set()
    assert _wait_until(
        lambda: any(
            response.get("id") == 1
            for response in _responses(output_stream)
        )
    )

    input_stream.close()
    thread.join(timeout=2.0)
    assert not thread.is_alive()
