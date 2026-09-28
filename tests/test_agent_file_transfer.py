import io
import threading
import time

from serialterminal.agent import AgentProtocol, _AgentJsonlRunner
from serialterminal.runlog import RunLog


class _FileAgentManager:
    def __init__(self):
        self.observe_started = threading.Event()
        self.observe_release = threading.Event()

    def file_send_start(self, session_id, local_path):
        return {
            "transfer_id": "0000000000000042",
            "direction": "TX",
            "filename": local_path.rsplit("/", 1)[-1],
            "state": "preparing",
        }

    def file_transfer_observe(
        self,
        session_id,
        transfer_id,
        *,
        cursor,
        window,
        timeout_ms,
    ):
        self.observe_started.set()
        self.observe_release.wait(timeout=2.0)
        return {
            "events": [],
            "cursor": cursor,
            "head_cursor": cursor,
            "state": "sending",
            "progress": {
                "transfer_id": transfer_id,
                "direction": "TX",
                "filename": "demo.bin",
                "state": "sending",
                "percentage": 50.0,
            },
            "timed_out": True,
        }

    def file_transfer_cancel(self, session_id, transfer_id):
        return {
            "transfer_id": transfer_id,
            "direction": "TX",
            "filename": "demo.bin",
            "state": "cancelled",
        }

    def file_transfer_close(self, session_id, transfer_id):
        return {"transfer_id": transfer_id, "state": "closed"}

    def status(self, session_id):
        return {
            "session": session_id,
            "state": "connected",
            "connected": True,
        }

    def cancel_observes(self):
        pass

    def cancel_file_transfers(self):
        self.observe_release.set()

    def join_file_transfers(self, timeout):
        pass

    def cancel_sweeps(self):
        pass

    def join_sweeps(self, timeout):
        pass

    def close_all(self):
        pass


def _wait_until(predicate, timeout=1.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def test_agent_file_transfer_operations_are_structured(tmp_path):
    manager = _FileAgentManager()
    with RunLog(tmp_path / "agent.log") as run_log:
        protocol = AgentProtocol(manager, run_log=run_log)

        started = protocol.handle(
            {
                "id": 1,
                "op": "file_send_start",
                "session": "s1",
                "path": "/tmp/demo.bin",
            }
        )
        assert started["ok"] is True
        assert started["result"]["transfer_id"] == "0000000000000042"
        assert started["result"]["state"] == "preparing"

        missing_path = protocol.handle(
            {
                "id": 2,
                "op": "file_send_start",
                "session": "s1",
            }
        )
        assert missing_path["ok"] is False
        assert missing_path["error"]["code"] == "invalid_request"

        missing_observe_id = protocol.handle(
            {
                "op": "file_transfer_observe",
                "session": "s1",
                "transfer_id": "0000000000000042",
            }
        )
        assert missing_observe_id["ok"] is False
        assert missing_observe_id["error"]["code"] == "invalid_request"

        cancelled = protocol.handle(
            {
                "id": 3,
                "op": "file_transfer_cancel",
                "session": "s1",
                "transfer_id": "0000000000000042",
            }
        )
        assert cancelled["ok"] is True
        assert cancelled["result"]["state"] == "cancelled"

        closed = protocol.handle(
            {
                "id": 4,
                "op": "file_transfer_close",
                "session": "s1",
                "transfer_id": "0000000000000042",
            }
        )
        assert closed["ok"] is True
        assert closed["result"]["state"] == "closed"


def test_file_transfer_observe_does_not_block_other_agent_requests(tmp_path):
    manager = _FileAgentManager()
    input_stream = io.StringIO()
    output_stream = io.StringIO()
    with RunLog(tmp_path / "agent.log") as run_log:
        protocol = AgentProtocol(manager, run_log=run_log)
        runner = _AgentJsonlRunner(
            manager,
            protocol,
            run_log,
            input_stream,
            output_stream,
        )

        runner._handle_request(
            {
                "id": 10,
                "op": "file_transfer_observe",
                "session": "s1",
                "transfer_id": "0000000000000042",
                "cursor": 0,
                "timeout_ms": 5000,
            }
        )
        assert manager.observe_started.wait(timeout=1.0)

        runner._handle_request(
            {
                "id": 11,
                "op": "status",
                "session": "s1",
            }
        )
        assert '"id":11' in output_stream.getvalue()
        assert '"id":10' not in output_stream.getvalue()

        manager.observe_release.set()
        assert _wait_until(lambda: '"id":10' in output_stream.getvalue())
        assert '"percentage":50.0' in output_stream.getvalue()
