import hashlib
from pathlib import Path
import random
import time

from serialterminal.file_transfer import (
    BinarySendReceipt,
    BinaryUserError,
    Compression,
    DataMessage,
    FileTransferManager,
    MetaMessage,
    ResumeMessage,
    decode_message,
    encode_message,
)
from serialterminal.file_transfer.protocol import data_payload_capacity


def _wait_until(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.01)
    return predicate()


class _PairTransport:
    payload_capacity = 200

    def __init__(self):
        self.receiver = None
        self.peer = None
        self.sent = []
        self.fail_data_from = None
        self.fail_all = False
        self.transient_failures = 0

    def set_receiver(self, receiver):
        self.receiver = receiver

    def send_binary(self, data, *, cancel_event=None):
        from serialterminal.file_transfer import BinaryUserCancelled

        if cancel_event is not None and cancel_event.is_set():
            raise BinaryUserCancelled()
        payload = bytes(data)
        message = decode_message(payload)
        if self.transient_failures > 0:
            self.transient_failures -= 1
            raise BinaryUserError("local_controller_reset", "synthetic reboot")
        if self.fail_all:
            raise BinaryUserError("local_disconnect", "synthetic disconnect")
        if (
            self.fail_data_from is not None
            and isinstance(message, DataMessage)
            and message.chunk_index >= self.fail_data_from
        ):
            raise BinaryUserError("local_disconnect", "synthetic disconnect")
        self.sent.append(payload)
        if self.peer is not None and self.peer.receiver is not None:
            self.peer.receiver(payload)
        return BinarySendReceipt(tx_id=len(self.sent))


def _pair(tmp_path, *, sender_kwargs=None, receiver_kwargs=None):
    left = _PairTransport()
    right = _PairTransport()
    left.peer = right
    right.peer = left
    sender = FileTransferManager(
        left,
        receive_dir=tmp_path / "left",
        id_factory=lambda: 0xAABBCCDD,
        result_timeout_s=2.0,
        resume_handshake_timeout_s=0.2,
        **(sender_kwargs or {}),
    )
    receiver = FileTransferManager(
        right,
        receive_dir=tmp_path / "right",
        id_factory=lambda: 0x11223344,
        result_timeout_s=2.0,
        resume_handshake_timeout_s=0.2,
        **(receiver_kwargs or {}),
    )
    return sender, receiver, left, right


def test_resume_message_round_trip():
    message = ResumeMessage(transfer_id=0x1234, next_chunk=77)
    encoded = encode_message(message, 200)
    assert decode_message(encoded) == message


def test_ft1_local_recovery_is_deadline_based_not_four_replays(tmp_path):
    source = tmp_path / "small.bin"
    source.write_bytes(random.Random(1).randbytes(900))
    sender, receiver, left, _right = _pair(
        tmp_path,
        sender_kwargs={
            "local_recovery_timeout_s": 1.0,
            "local_recovery_retry_s": 0.001,
        },
    )
    left.transient_failures = 6
    try:
        started = sender.start_send(source)
        done = _wait_until(
            lambda: (
                item
                if (item := sender.display_snapshot())
                and item["state"] in {"completed", "failed"}
                else None
            )
        )
        assert done["state"] == "completed"
        observed = sender.observe(
            started["transfer_id"], cursor=0, window=100, timeout_ms=0
        )
        kinds = [event["kind"] for event in observed["events"]]
        assert "local_recovery_started" in kinds
        assert "local_recovery_resumed" in kinds
        replay_events = [
            event for event in observed["events"] if event["kind"] == "binary_send_replay"
        ]
        assert len(replay_events) >= 6
    finally:
        sender.close()
        receiver.close()


def test_receiver_manifest_survives_manager_restart_and_reports_resume_cursor(tmp_path):
    receive_dir = tmp_path / "rx"
    transport = _PairTransport()
    manager = FileTransferManager(
        transport,
        receive_dir=receive_dir,
        incoming_idle_timeout_s=30.0,
    )
    payload = random.Random(2).randbytes(900)
    chunk_size = data_payload_capacity(transport.payload_capacity)
    chunks = [
        payload[offset : offset + chunk_size]
        for offset in range(0, len(payload), chunk_size)
    ]
    meta = MetaMessage(
        transfer_id=0x55,
        filename="resume.bin",
        original_size=len(payload),
        wire_size=len(payload),
        compression=Compression.NONE,
        chunk_size=chunk_size,
        original_sha256=hashlib.sha256(payload).digest(),
    )
    manager.feed_binary(encode_message(meta, transport.payload_capacity))
    assert _wait_until(lambda: manager.display_snapshot())
    for index in range(3):
        manager.feed_binary(
            encode_message(
                DataMessage(meta.transfer_id, index, chunks[index]),
                transport.payload_capacity,
            )
        )
    assert _wait_until(
        lambda: manager.display_snapshot()
        and manager.display_snapshot()["chunks_completed"] == 3
    )
    manager.close()

    transport2 = _PairTransport()
    manager2 = FileTransferManager(
        transport2,
        receive_dir=receive_dir,
        incoming_idle_timeout_s=30.0,
    )
    try:
        manager2.feed_binary(encode_message(meta, transport2.payload_capacity))
        assert _wait_until(
            lambda: any(
                isinstance(decode_message(item), ResumeMessage)
                for item in transport2.sent
            )
        )
        resume = next(
            decode_message(item)
            for item in transport2.sent
            if isinstance(decode_message(item), ResumeMessage)
        )
        assert resume.next_chunk == 3
        snapshot = manager2.display_snapshot()
        assert snapshot["state"] == "receiving"
        assert snapshot["chunks_completed"] == 3
    finally:
        manager2.close()


def test_sender_and_receiver_restart_resume_same_transfer_id(tmp_path):
    source = tmp_path / "source.bin"
    source.write_bytes(random.Random(3).randbytes(5000))

    sender1, receiver1, left1, _right1 = _pair(
        tmp_path,
        sender_kwargs={
            "local_recovery_timeout_s": 0.05,
            "local_recovery_retry_s": 0.005,
        },
    )
    left1.fail_data_from = 5
    first = sender1.start_send(source)
    first_id = first["transfer_id"]
    failed = _wait_until(
        lambda: (
            item
            if (item := sender1.display_snapshot()) and item["state"] == "failed"
            else None
        )
    )
    assert failed["failure"]["code"] == "local_recovery_timeout"
    partial = _wait_until(
        lambda: (
            item
            if (item := receiver1.display_snapshot())
            and item["chunks_completed"] >= 5
            else None
        )
    )
    assert partial["chunks_completed"] >= 5
    sender1.close()
    receiver1.close()

    left2 = _PairTransport()
    right2 = _PairTransport()
    left2.peer = right2
    right2.peer = left2
    sender2 = FileTransferManager(
        left2,
        receive_dir=tmp_path / "left",
        id_factory=lambda: 0xDEADBEEF,
        result_timeout_s=2.0,
        resume_handshake_timeout_s=0.2,
    )
    receiver2 = FileTransferManager(
        right2,
        receive_dir=tmp_path / "right",
        id_factory=lambda: 0xCAFEBABE,
        result_timeout_s=2.0,
        resume_handshake_timeout_s=0.2,
    )
    try:
        second = sender2.start_send(source)
        assert second["transfer_id"] == first_id
        assert second.get("resumed") is True
        done = _wait_until(
            lambda: (
                item
                if (item := sender2.display_snapshot())
                and item["state"] in {"completed", "failed"}
                else None
            ),
            timeout=8.0,
        )
        assert done["state"] == "completed"
        received = _wait_until(
            lambda: (
                item
                if (item := receiver2.display_snapshot())
                and item["state"] == "completed"
                else None
            )
        )
        final = Path(received["final_path"])
        assert final.read_bytes() == source.read_bytes()
        assert hashlib.sha256(final.read_bytes()).digest() == hashlib.sha256(
            source.read_bytes()
        ).digest()

        sent_messages = [decode_message(item) for item in left2.sent]
        sent_data = [item for item in sent_messages if isinstance(item, DataMessage)]
        assert sent_data
        assert sent_data[0].chunk_index >= 5
    finally:
        sender2.close()
        receiver2.close()


def test_completed_tombstone_avoids_duplicate_full_resend_after_restart(tmp_path):
    source = tmp_path / "done.bin"
    source.write_bytes(random.Random(4).randbytes(1200))
    sender, receiver, _left, _right = _pair(tmp_path)
    started = sender.start_send(source)
    transfer_id = started["transfer_id"]
    done = _wait_until(
        lambda: (
            item
            if (item := sender.display_snapshot()) and item["state"] == "completed"
            else None
        )
    )
    assert done
    rx_done = _wait_until(
        lambda: (
            item
            if (item := receiver.display_snapshot()) and item["state"] == "completed"
            else None
        )
    )
    assert rx_done
    final_path = Path(rx_done["final_path"])
    sender.close()
    receiver.close()

    # Recreate a sender journal representing a lost local completion record. The
    # receiver tombstone should answer the replayed META with RESULT OK before DATA.
    left_state = tmp_path / "left" / ".serialterminal-state" / "outgoing"
    left_state.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    journal = {
        "schema": 1,
        "kind": "outgoing",
        "transfer_id": transfer_id,
        "status": "active",
        "source_path": str(source.resolve()),
        "filename": source.name,
        "original_size": source.stat().st_size,
        "original_sha256": digest,
        "wire_size": source.stat().st_size,
        "wire_sha256": digest,
        "compression": 0,
        "chunk_size": data_payload_capacity(200),
        "updated": time.time(),
    }
    import json

    (left_state / f"{transfer_id}.json").write_text(json.dumps(journal), encoding="utf-8")

    left = _PairTransport()
    right = _PairTransport()
    left.peer = right
    right.peer = left
    sender2 = FileTransferManager(
        left,
        receive_dir=tmp_path / "left",
        result_timeout_s=2.0,
        resume_handshake_timeout_s=0.2,
    )
    receiver2 = FileTransferManager(
        right,
        receive_dir=tmp_path / "right",
        result_timeout_s=2.0,
        resume_handshake_timeout_s=0.2,
    )
    try:
        restarted = sender2.start_send(source)
        assert restarted["transfer_id"] == transfer_id
        completed = _wait_until(
            lambda: (
                item
                if (item := sender2.display_snapshot()) and item["state"] == "completed"
                else None
            )
        )
        assert completed
        assert final_path.exists()
        assert not any(isinstance(decode_message(item), DataMessage) for item in left.sent)
    finally:
        sender2.close()
        receiver2.close()
