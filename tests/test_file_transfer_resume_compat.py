import hashlib
import itertools
from pathlib import Path
import random
import time

from serialterminal.file_transfer import (
    BinarySendReceipt,
    DataMessage,
    FileTransferManager,
    ResumeMessage,
    MetaMessage,
    decode_message,
)
from recursive_evidence import service_requests


class _PairTransport:
    payload_capacity = 200

    def __init__(self):
        self.receiver = None
        self.peer = None
        self.sent = []
        self.drop_resume_once = False
        self.holes = set()

    def set_receiver(self, receiver):
        self.receiver = receiver

    def send_binary(self, data, *, cancel_event=None):
        payload = bytes(data)
        self.sent.append(payload)
        message = decode_message(payload)
        if isinstance(message, ResumeMessage) and self.drop_resume_once:
            self.drop_resume_once = False
            return BinarySendReceipt(tx_id=len(self.sent))
        if isinstance(message, DataMessage) and message.chunk_index in self.holes:
            self.holes.remove(message.chunk_index)
            return BinarySendReceipt(tx_id=len(self.sent))
        if self.peer is not None and self.peer.receiver is not None:
            self.peer.receiver(payload)
            while self.peer.receiver.__self__._rx_queue.qsize() > 8:
                time.sleep(.001)
        return BinarySendReceipt(tx_id=len(self.sent))


def _wait_terminal(manager, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        snapshot = manager.display_snapshot()
        if snapshot and snapshot["state"] in {"completed", "failed", "cancelled"}:
            return snapshot
        time.sleep(0.01)
    return manager.display_snapshot()


def _pair_transports():
    left = _PairTransport()
    right = _PairTransport()
    left.peer = right
    right.peer = left
    return left, right


def test_lost_initial_resume_still_completes_between_current_peers(tmp_path):
    source = tmp_path / "source.bin"
    source.write_bytes(random.Random(31).randbytes(1400))
    left, right = _pair_transports()
    sender = FileTransferManager(
        left,
        receive_dir=tmp_path / "sender",
        id_factory=lambda: 0x1001,
        result_timeout_s=2.0,
        resume_handshake_timeout_s=0.05,
    )
    right.drop_resume_once = True
    receiver = FileTransferManager(
        right,
        receive_dir=tmp_path / "receiver",
        id_factory=lambda: 0x2002,
        result_timeout_s=2.0,
    )

    try:
        started = sender.start_send(source)
        done = _wait_terminal(sender)
        assert done["state"] == "completed"
        received = _wait_terminal(receiver)
        assert received["state"] == "completed"
        final_path = Path(received["final_path"])
        assert final_path.read_bytes() == source.read_bytes()
        assert hashlib.sha256(final_path.read_bytes()).digest() == hashlib.sha256(
            source.read_bytes()
        ).digest()

        messages = [decode_message(raw) for raw in left.sent]
        data_messages = [item for item in messages if isinstance(item, DataMessage)]
        assert data_messages
        assert data_messages[0].chunk_index == 0

        observed = sender.observe(
            started["transfer_id"], cursor=0, window=200, timeout_ms=0
        )
        assert any(
            event["kind"] == "resume_handshake_fallback"
            for event in observed["events"]
        )
    finally:
        sender.close()
        receiver.close()


def test_current_peers_repair_more_ranges_than_one_packet(tmp_path):
    source = tmp_path / "source.bin"
    source.write_bytes(random.Random(32).randbytes(184 * 300))
    left, right = _pair_transports()
    holes = set(range(1, 160, 2))
    left.holes = holes.copy()
    ids = itertools.count(0x3003)
    sender = FileTransferManager(left, receive_dir=tmp_path / "sender",
                                 id_factory=lambda: next(ids), control_replay_interval_s=.2)
    receiver = FileTransferManager(right, receive_dir=tmp_path / "receiver",
                                   id_factory=lambda: next(ids), control_replay_interval_s=.2)
    try:
        started = sender.start_send(source)
        done = _wait_terminal(sender)
        assert done["state"] == "completed", done
        received = _wait_terminal(receiver)
        assert received["state"] == "completed", received
        assert Path(received["final_path"]).read_bytes() == source.read_bytes()
        parent = int(started["transfer_id"], 16)
        requests = service_requests(right.sent, parent)
        assert len(requests) == 1
        assert len(requests[0].ranges) == 80
        assert {r.start_chunk for r in requests[0].ranges} == holes
        service = [decode_message(raw) for raw in right.sent]
        assert any(isinstance(m, MetaMessage) and m.parent_transfer_id == parent for m in service)
        counts = {}
        for raw in left.sent:
            message = decode_message(raw)
            if isinstance(message, DataMessage) and message.transfer_id == parent:
                counts[message.chunk_index] = counts.get(message.chunk_index, 0) + 1
        assert counts == {index: 2 if index in holes else 1 for index in range(300)}
    finally:
        sender.close()
        receiver.close()
