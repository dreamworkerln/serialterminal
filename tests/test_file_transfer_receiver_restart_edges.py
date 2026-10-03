import hashlib
from pathlib import Path
import random
import time

from serialterminal.file_transfer import (
    BinarySendReceipt,
    Compression,
    DataMessage,
    EndMessage,
    FileTransferManager,
    MetaMessage,
    ResumeMessage,
    decode_message,
    encode_message,
)
from serialterminal.file_transfer.protocol import data_payload_capacity


class _CaptureTransport:
    payload_capacity = 200

    def __init__(self):
        self.receiver = None
        self.sent = []

    def set_receiver(self, receiver):
        self.receiver = receiver

    def send_binary(self, data, *, cancel_event=None):
        payload = bytes(data)
        self.sent.append(payload)
        return BinarySendReceipt(tx_id=len(self.sent))


def _wait_until(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.01)
    return predicate()


def _fixture(transport, payload, transfer_id):
    chunk_size = data_payload_capacity(transport.payload_capacity)
    chunks = [
        payload[offset : offset + chunk_size]
        for offset in range(0, len(payload), chunk_size)
    ]
    meta = MetaMessage(
        transfer_id=transfer_id,
        filename="sparse.bin",
        original_size=len(payload),
        wire_size=len(payload),
        compression=Compression.NONE,
        chunk_size=chunk_size,
        original_sha256=hashlib.sha256(payload).digest(),
    )
    end = EndMessage(
        transfer_id=transfer_id,
        chunk_count=len(chunks),
        wire_sha256=hashlib.sha256(payload).digest(),
    )
    return meta, chunks, end


def _resume_from(transport):
    return next(
        message.next_chunk
        for raw in transport.sent
        if isinstance((message := decode_message(raw)), ResumeMessage)
    )


def test_sparse_receiver_map_survives_restart_and_repairs_from_earliest_hole(tmp_path):
    receive_dir = tmp_path / "rx"
    payload = random.Random(41).randbytes(760)
    transport1 = _CaptureTransport()
    manager1 = FileTransferManager(transport1, receive_dir=receive_dir)
    meta, chunks, end = _fixture(transport1, payload, 0x4101)

    try:
        manager1.feed_binary(encode_message(meta, transport1.payload_capacity))
        assert _wait_until(lambda: manager1.display_snapshot())
        for index in (0, 2):
            manager1.feed_binary(
                encode_message(
                    DataMessage(meta.transfer_id, index, chunks[index]),
                    transport1.payload_capacity,
                )
            )
        assert _wait_until(
            lambda: manager1.display_snapshot()
            and manager1.display_snapshot()["chunks_completed"] == 2
        )
    finally:
        manager1.close()

    transport2 = _CaptureTransport()
    manager2 = FileTransferManager(transport2, receive_dir=receive_dir)
    try:
        manager2.feed_binary(encode_message(meta, transport2.payload_capacity))
        assert _wait_until(
            lambda: any(
                isinstance(decode_message(raw), ResumeMessage)
                for raw in transport2.sent
            )
        )
        assert _resume_from(transport2) == 1
        restored = manager2.display_snapshot()
        assert restored["chunks_completed"] == 2

        for index in range(1, len(chunks)):
            manager2.feed_binary(
                encode_message(
                    DataMessage(meta.transfer_id, index, chunks[index]),
                    transport2.payload_capacity,
                )
            )
        manager2.feed_binary(encode_message(end, transport2.payload_capacity))
        completed = _wait_until(
            lambda: (
                snapshot
                if (snapshot := manager2.display_snapshot())
                and snapshot["state"] == "completed"
                else None
            )
        )
        final_path = Path(completed["final_path"])
        assert final_path.read_bytes() == payload
    finally:
        manager2.close()


def test_restore_never_infers_uncheckpointed_chunk_from_part_file_size(tmp_path):
    receive_dir = tmp_path / "rx"
    payload = random.Random(42).randbytes(500)
    transport = _CaptureTransport()
    manager = FileTransferManager(transport, receive_dir=receive_dir)
    meta, chunks, _end = _fixture(transport, payload, 0x4202)
    part = manager._resume_store.incoming_part(meta.transfer_id)
    part.parent.mkdir(parents=True, exist_ok=True)
    with part.open("wb") as handle:
        handle.write(chunks[0])
        handle.write(chunks[1])
        handle.flush()
    manager._resume_store.save_incoming(
        meta=meta,
        received={0: len(chunks[0])},
        status="suspended",
    )
    manager.close()

    transport2 = _CaptureTransport()
    manager2 = FileTransferManager(transport2, receive_dir=receive_dir)
    try:
        manager2.feed_binary(encode_message(meta, transport2.payload_capacity))
        assert _wait_until(
            lambda: any(
                isinstance(decode_message(raw), ResumeMessage)
                for raw in transport2.sent
            )
        )
        assert _resume_from(transport2) == 1
        restored = manager2.display_snapshot()
        assert restored["chunks_completed"] == 1
    finally:
        manager2.close()


def test_conflicting_duplicate_after_restart_is_still_fatal(tmp_path):
    receive_dir = tmp_path / "rx"
    payload = random.Random(43).randbytes(500)
    transport1 = _CaptureTransport()
    manager1 = FileTransferManager(transport1, receive_dir=receive_dir)
    meta, chunks, _end = _fixture(transport1, payload, 0x4303)

    try:
        manager1.feed_binary(encode_message(meta, transport1.payload_capacity))
        assert _wait_until(lambda: manager1.display_snapshot())
        manager1.feed_binary(
            encode_message(
                DataMessage(meta.transfer_id, 0, chunks[0]),
                transport1.payload_capacity,
            )
        )
        assert _wait_until(
            lambda: manager1.display_snapshot()
            and manager1.display_snapshot()["chunks_completed"] == 1
        )
    finally:
        manager1.close()

    transport2 = _CaptureTransport()
    manager2 = FileTransferManager(transport2, receive_dir=receive_dir)
    try:
        manager2.feed_binary(encode_message(meta, transport2.payload_capacity))
        assert _wait_until(lambda: manager2.display_snapshot())
        bad = bytearray(chunks[0])
        bad[0] ^= 0xFF
        manager2.feed_binary(
            encode_message(
                DataMessage(meta.transfer_id, 0, bytes(bad)),
                transport2.payload_capacity,
            )
        )
        failed = _wait_until(
            lambda: (
                snapshot
                if (snapshot := manager2.display_snapshot())
                and snapshot["state"] == "failed"
                else None
            )
        )
        assert failed["failure"]["code"] == "invalid_chunk"
    finally:
        manager2.close()
