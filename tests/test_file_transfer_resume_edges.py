import hashlib
import json
from pathlib import Path
import random
import time

from serialterminal.file_transfer import (
    BinarySendReceipt,
    BinaryUserCancelled,
    BinaryUserError,
    Compression,
    DataMessage,
    EndMessage,
    FileTransferManager,
    MetaMessage,
    ResultMessage,
    ResumeMessage,
    decode_message,
    encode_message,
)
from serialterminal.file_transfer.protocol import data_payload_capacity


def _wait_until(predicate, timeout=8.0):
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

    def set_receiver(self, receiver):
        self.receiver = receiver

    def send_binary(self, data, *, cancel_event=None):
        if cancel_event is not None and cancel_event.is_set():
            raise BinaryUserCancelled()
        payload = bytes(data)
        message = decode_message(payload)
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


def _manager(transport, receive_dir, *, transfer_id, **kwargs):
    return FileTransferManager(
        transport,
        receive_dir=receive_dir,
        id_factory=lambda: transfer_id,
        result_timeout_s=2.0,
        resume_handshake_timeout_s=0.2,
        **kwargs,
    )


def _pair(tmp_path, *, sender_id, receiver_id, sender_kwargs=None):
    left = _PairTransport()
    right = _PairTransport()
    left.peer = right
    right.peer = left
    sender = _manager(
        left,
        tmp_path / "left",
        transfer_id=sender_id,
        **(sender_kwargs or {}),
    )
    receiver = _manager(right, tmp_path / "right", transfer_id=receiver_id)
    return sender, receiver, left, right


def _failed_snapshot(manager):
    item = manager.display_snapshot()
    return item if item and item["state"] == "failed" else None


def _completed_snapshot(manager):
    item = manager.display_snapshot()
    return item if item and item["state"] == "completed" else None


def test_changed_source_does_not_reuse_retained_transfer_id(tmp_path):
    source = tmp_path / "source.bin"
    source.write_bytes(random.Random(11).randbytes(4000))
    sender1, receiver1, left1, _right1 = _pair(
        tmp_path,
        sender_id=0x1111,
        receiver_id=0xAAAA,
        sender_kwargs={
            "local_recovery_timeout_s": 0.03,
            "local_recovery_retry_s": 0.003,
        },
    )
    left1.fail_data_from = 3
    first = sender1.start_send(source)
    assert _wait_until(lambda: _failed_snapshot(sender1))
    old_transfer_id = first["transfer_id"]
    sender1.close()
    receiver1.close()

    changed = bytearray(source.read_bytes())
    changed[len(changed) // 2] ^= 0x5A
    source.write_bytes(changed)

    sender2, receiver2, _left2, _right2 = _pair(
        tmp_path,
        sender_id=0x2222,
        receiver_id=0xBBBB,
    )
    try:
        second = sender2.start_send(source)
        assert second["transfer_id"] != old_transfer_id
        assert int(second["transfer_id"], 16) == 0x2222
        assert second.get("resumed") is not True
        assert _wait_until(lambda: _completed_snapshot(sender2))
    finally:
        sender2.close()
        receiver2.close()


def test_gzip_wire_is_deterministic_across_sender_restart(tmp_path):
    source = tmp_path / "compressible.bin"
    block = bytes(range(256)) * 2048
    source.write_bytes(block + block + block)

    sender1, receiver1, left1, _right1 = _pair(
        tmp_path,
        sender_id=0x3333,
        receiver_id=0xCCCC,
        sender_kwargs={
            "local_recovery_timeout_s": 0.03,
            "local_recovery_retry_s": 0.003,
        },
    )
    left1.fail_data_from = 4
    first = sender1.start_send(source)
    assert _wait_until(lambda: _failed_snapshot(sender1))
    partial = _wait_until(
        lambda: (
            item
            if (item := receiver1.display_snapshot())
            and item["chunks_completed"] >= 4
            else None
        )
    )
    assert partial
    first_id = first["transfer_id"]

    journal_path = (
        tmp_path
        / "left"
        / ".serialterminal-state"
        / "outgoing"
        / f"{first_id}.json"
    )
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    assert journal["compression"] == int(Compression.GZIP)
    first_wire_hash = journal["wire_sha256"]

    sender1.close()
    receiver1.close()

    sender2, receiver2, left2, _right2 = _pair(
        tmp_path,
        sender_id=0x4444,
        receiver_id=0xDDDD,
    )
    try:
        second = sender2.start_send(source)
        assert second["transfer_id"] == first_id
        assert second.get("resumed") is True
        assert _wait_until(lambda: _completed_snapshot(sender2))
        received = _wait_until(lambda: _completed_snapshot(receiver2))
        assert Path(received["final_path"]).read_bytes() == source.read_bytes()

        sent = [decode_message(payload) for payload in left2.sent]
        data_messages = [item for item in sent if isinstance(item, DataMessage)]
        assert data_messages
        assert data_messages[0].chunk_index >= 4

        completed_manifest = next(
            (tmp_path / "right" / ".serialterminal-state" / "completed").glob(
                "*.json"
            )
        )
        completed = json.loads(completed_manifest.read_text(encoding="utf-8"))
        assert completed["end"]["wire_sha256"] == first_wire_hash
    finally:
        sender2.close()
        receiver2.close()


def test_corrupt_receiver_manifest_is_not_trusted(tmp_path):
    receive_dir = tmp_path / "rx"
    transport = _PairTransport()
    manager = _manager(transport, receive_dir, transfer_id=0x9999)
    transfer_id = 0x55
    manifest = (
        receive_dir
        / ".serialterminal-state"
        / "incoming"
        / f"{transfer_id:016x}.json"
    )
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text("{broken-json", encoding="utf-8")
    (receive_dir / f".serialterminal-{transfer_id:016x}.part").write_bytes(b"evil")

    payload = b"safe receiver state"
    meta = MetaMessage(
        transfer_id=transfer_id,
        filename="safe.bin",
        original_size=len(payload),
        wire_size=len(payload),
        compression=Compression.NONE,
        chunk_size=data_payload_capacity(transport.payload_capacity),
        original_sha256=hashlib.sha256(payload).digest(),
    )
    try:
        manager.feed_binary(encode_message(meta, transport.payload_capacity))
        assert _wait_until(
            lambda: any(
                isinstance(item := decode_message(raw), ResultMessage)
                and item.transfer_id == transfer_id
                and item.code == "storage_failed"
                for raw in transport.sent
            )
        )
        assert not (receive_dir / "safe.bin").exists()
    finally:
        manager.close()


class _InvalidResumeTransport:
    payload_capacity = 200

    def __init__(self):
        self.receiver = None

    def set_receiver(self, receiver):
        self.receiver = receiver

    def send_binary(self, data, *, cancel_event=None):
        if cancel_event is not None and cancel_event.is_set():
            raise BinaryUserCancelled()
        message = decode_message(bytes(data))
        if isinstance(message, MetaMessage) and self.receiver is not None:
            self.receiver(
                encode_message(
                    ResumeMessage(message.transfer_id, 0xFFFFFFFF),
                    self.payload_capacity,
                )
            )
        return BinarySendReceipt(tx_id=1)


def test_resume_cursor_outside_chunk_count_fails_sender(tmp_path):
    source = tmp_path / "source.bin"
    source.write_bytes(random.Random(12).randbytes(900))
    manager = _manager(
        _InvalidResumeTransport(),
        tmp_path / "sender",
        transfer_id=0x7777,
    )
    try:
        manager.start_send(source)
        failure = _wait_until(lambda: _failed_snapshot(manager))
        assert failure["failure"]["code"] == "invalid_resume_request"
    finally:
        manager.close()


def test_receiver_restart_after_all_data_resumes_directly_at_end(tmp_path):
    receive_dir = tmp_path / "rx"
    transport1 = _PairTransport()
    manager1 = _manager(transport1, receive_dir, transfer_id=0xABCD)
    payload = random.Random(13).randbytes(700)
    chunk_size = data_payload_capacity(transport1.payload_capacity)
    chunks = [
        payload[offset : offset + chunk_size]
        for offset in range(0, len(payload), chunk_size)
    ]
    transfer_id = 0x8888
    meta = MetaMessage(
        transfer_id=transfer_id,
        filename="all-data.bin",
        original_size=len(payload),
        wire_size=len(payload),
        compression=Compression.NONE,
        chunk_size=chunk_size,
        original_sha256=hashlib.sha256(payload).digest(),
    )
    for message in [meta] + [
        DataMessage(transfer_id, index, block)
        for index, block in enumerate(chunks)
    ]:
        manager1.feed_binary(encode_message(message, transport1.payload_capacity))
    assert _wait_until(
        lambda: manager1.display_snapshot()
        and manager1.display_snapshot()["chunks_completed"] == len(chunks)
    )
    manager1.close()

    transport2 = _PairTransport()
    manager2 = _manager(transport2, receive_dir, transfer_id=0xDCBA)
    try:
        manager2.feed_binary(encode_message(meta, transport2.payload_capacity))
        assert _wait_until(
            lambda: any(
                isinstance(item := decode_message(raw), ResumeMessage)
                and item.next_chunk == len(chunks)
                for raw in transport2.sent
            )
        )
        end = EndMessage(
            transfer_id,
            len(chunks),
            hashlib.sha256(payload).digest(),
        )
        manager2.feed_binary(encode_message(end, transport2.payload_capacity))
        done = _wait_until(lambda: _completed_snapshot(manager2))
        assert Path(done["final_path"]).read_bytes() == payload
    finally:
        manager2.close()
