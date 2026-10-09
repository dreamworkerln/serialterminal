import base64
import random
import time
from dataclasses import dataclass
from pathlib import Path

import pytest

from serialterminal.file_transfer import (
    BinarySendReceipt,
    BinaryUserError,
    FileTransferManager,
)
from serialterminal.profiles.chatter.binary_pipeline import (
    CHATTER_BINARY_PIPELINE_CAPACITY,
    PipelinedChatterBinaryUserAdapter,
)
from serialterminal.profiles.chatter.binary_user import encode_binary_command


def _tx_line(payload: bytes) -> str:
    encoded = base64.b64encode(payload).decode("ascii")
    return f"> [BINARY] {encoded}"


def _wait_until(predicate, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.01)
    return predicate()


def test_chatter_pipeline_accepts_two_before_first_presentation():
    sent = []
    next_tx_id = {"value": 0}

    def send_line(text):
        sent.append(text)
        next_tx_id["value"] += 1
        return {"tx_id": next_tx_id["value"], "state": "queued"}

    adapter = PipelinedChatterBinaryUserAdapter(
        send_line,
        wait_tx_outcome=lambda _tx_id, _timeout: "written",
        presentation_timeout_s=0.2,
    )
    adapter.feed_line("main", "[SYS] current=CHAT")

    first = adapter.submit_binary(b"one")
    second = adapter.submit_binary(b"two")

    assert CHATTER_BINARY_PIPELINE_CAPACITY == 2
    assert sent == [encode_binary_command(b"one"), encode_binary_command(b"two")]
    with pytest.raises(BinaryUserError) as caught:
        adapter.submit_binary(b"three")
    assert caught.value.code == "binary_pipeline_full"

    adapter.feed_line("chat", _tx_line(b"one"))
    assert adapter.settle_binary(first).tx_id == 1

    third = adapter.submit_binary(b"three")
    adapter.feed_line("chat", _tx_line(b"two"))
    adapter.feed_line("chat", _tx_line(b"three"))
    assert adapter.settle_binary(second).tx_id == 2
    assert adapter.settle_binary(third).tx_id == 3


def test_chatter_pipeline_does_not_reuse_one_presentation_for_equal_payloads():
    adapter = PipelinedChatterBinaryUserAdapter(
        lambda _text: {"tx_id": 1, "state": "queued"},
        wait_tx_outcome=lambda _tx_id, _timeout: "written",
        presentation_timeout_s=0.03,
    )
    adapter.feed_line("main", "[SYS] current=CHAT")

    first = adapter.submit_binary(b"same")
    second = adapter.submit_binary(b"same")
    adapter.feed_line("chat", _tx_line(b"same"))

    adapter.settle_binary(first)
    with pytest.raises(BinaryUserError) as caught:
        adapter.settle_binary(second)
    assert caught.value.code == "binary_presentation_timeout"


@dataclass(frozen=True)
class _Ticket:
    tx_id: int
    payload: bytes


class _PipelinePairTransport:
    payload_capacity = 200
    pipeline_capacity = 2

    def __init__(self, *, fail_second_submit_once=False):
        self.receiver = None
        self.peer = None
        self.pending = []
        self.sent = []
        self.max_pending = 0
        self._next_tx_id = 1
        self._submit_count = 0
        self._fail_second_submit_once = fail_second_submit_once
        self._failed = False
        self.discards = 0

    def set_receiver(self, receiver):
        self.receiver = receiver

    def _deliver(self, payload):
        if self.peer is not None and self.peer.receiver is not None:
            self.peer.receiver(bytes(payload))

    def send_binary(self, data, *, cancel_event=None):
        payload = bytes(data)
        self.sent.append(payload)
        tx_id = self._next_tx_id
        self._next_tx_id += 1
        self._deliver(payload)
        return BinarySendReceipt(tx_id=tx_id)

    def submit_binary(self, data, *, cancel_event=None):
        self._submit_count += 1
        if (
            self._fail_second_submit_once
            and self._submit_count == 2
            and not self._failed
        ):
            self._failed = True
            raise BinaryUserError("local_disconnect", "synthetic reconnect")
        ticket = _Ticket(self._next_tx_id, bytes(data))
        self._next_tx_id += 1
        self.pending.append(ticket)
        self.max_pending = max(self.max_pending, len(self.pending))
        return ticket

    def settle_binary(self, ticket, *, cancel_event=None):
        assert self.pending and self.pending[0] is ticket
        self.pending.pop(0)
        self.sent.append(ticket.payload)
        self._deliver(ticket.payload)
        return BinarySendReceipt(tx_id=ticket.tx_id)

    def discard_binary_pipeline(self):
        self.discards += 1
        self.pending.clear()


def _pipeline_pair(tmp_path, *, fail_second_submit_once=False):
    left = _PipelinePairTransport(
        fail_second_submit_once=fail_second_submit_once
    )
    right = _PipelinePairTransport()
    left.peer = right
    right.peer = left
    tx = FileTransferManager(
        left,
        receive_dir=tmp_path / "left",
        id_factory=lambda: 0x1234,
        result_timeout_s=2.0,
        control_replay_interval_s=0.05,
    )
    rx = FileTransferManager(
        right,
        receive_dir=tmp_path / "right",
        id_factory=lambda: 0x5678,
        result_timeout_s=2.0,
        control_replay_interval_s=0.05,
    )
    return tx, rx, left, right


def test_ft1_data_pipeline_window_two_completes_and_preserves_bytes(tmp_path):
    source = tmp_path / "pipeline.bin"
    source.write_bytes(random.Random(20261006).randbytes(4096))
    tx, rx, left, _right = _pipeline_pair(tmp_path)
    try:
        tx.start_send(source)
        done = _wait_until(
            lambda: (
                snapshot
                if (snapshot := tx.display_snapshot())
                and snapshot["state"] in {"completed", "failed"}
                else None
            )
        )
        assert done is not None
        assert done["state"] == "completed"
        assert left.max_pending == 2
        assert not left.pending

        received = _wait_until(
            lambda: (
                snapshot
                if (snapshot := rx.display_snapshot())
                and snapshot["state"] == "completed"
                else None
            )
        )
        assert received is not None
        assert Path(received["final_path"]).read_bytes() == source.read_bytes()

        observed = tx.observe(
            done["transfer_id"], cursor=0, window=100, timeout_ms=0
        )
        assert any(
            event["kind"] == "binary_pipeline_enabled"
            and event["window"] == 2
            for event in observed["events"]
        )
    finally:
        tx.close()
        rx.close()


def test_ft1_pipeline_recoverable_submit_error_falls_back_from_earliest_outstanding(tmp_path):
    source = tmp_path / "pipeline-recovery.bin"
    source.write_bytes(random.Random(77).randbytes(2048))
    tx, rx, left, _right = _pipeline_pair(
        tmp_path, fail_second_submit_once=True
    )
    try:
        tx.start_send(source)
        done = _wait_until(
            lambda: (
                snapshot
                if (snapshot := tx.display_snapshot())
                and snapshot["state"] in {"completed", "failed"}
                else None
            )
        )
        assert done is not None
        assert done["state"] == "completed"
        assert left.discards >= 1

        received = _wait_until(
            lambda: (
                snapshot
                if (snapshot := rx.display_snapshot())
                and snapshot["state"] == "completed"
                else None
            )
        )
        assert received is not None
        assert Path(received["final_path"]).read_bytes() == source.read_bytes()

        observed = tx.observe(
            done["transfer_id"], cursor=0, window=100, timeout_ms=0
        )
        fallback = [
            event
            for event in observed["events"]
            if event["kind"] == "binary_pipeline_fallback"
        ]
        assert fallback
        assert fallback[0]["reason"] == "local_disconnect"
        assert fallback[0]["next_chunk"] == 0
    finally:
        tx.close()
        rx.close()
