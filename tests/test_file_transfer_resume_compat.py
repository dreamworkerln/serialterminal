import hashlib
from pathlib import Path
import random
import time

from serialterminal.file_transfer import (
    BinarySendReceipt,
    DataMessage,
    FileTransferManager,
    ResumeMessage,
    decode_message,
)
from serialterminal.file_transfer.core import FileTransferManager as LegacyFileTransferManager


class _PairTransport:
    payload_capacity = 200

    def __init__(self):
        self.receiver = None
        self.peer = None
        self.sent = []

    def set_receiver(self, receiver):
        self.receiver = receiver

    def send_binary(self, data, *, cancel_event=None):
        payload = bytes(data)
        self.sent.append(payload)
        if self.peer is not None and self.peer.receiver is not None:
            self.peer.receiver(payload)
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


def test_new_sender_falls_back_to_full_pass_with_legacy_receiver(tmp_path):
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
    receiver = LegacyFileTransferManager(
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


def test_legacy_sender_ignores_optional_resume_from_new_receiver(tmp_path):
    source = tmp_path / "source.bin"
    source.write_bytes(random.Random(32).randbytes(1400))
    left, right = _pair_transports()
    sender = LegacyFileTransferManager(
        left,
        receive_dir=tmp_path / "sender",
        id_factory=lambda: 0x3003,
        result_timeout_s=2.0,
    )
    receiver = FileTransferManager(
        right,
        receive_dir=tmp_path / "receiver",
        id_factory=lambda: 0x4004,
        result_timeout_s=2.0,
        resume_handshake_timeout_s=0.05,
    )

    try:
        sender.start_send(source)
        done = _wait_terminal(sender)
        assert done["state"] == "completed"
        received = _wait_terminal(receiver)
        assert received["state"] == "completed"
        final_path = Path(received["final_path"])
        assert final_path.read_bytes() == source.read_bytes()

        reverse_messages = [decode_message(raw) for raw in right.sent]
        assert any(isinstance(item, ResumeMessage) for item in reverse_messages)
        assert any(
            isinstance(item, DataMessage) and item.chunk_index == 0
            for item in (decode_message(raw) for raw in left.sent)
        )
    finally:
        sender.close()
        receiver.close()
