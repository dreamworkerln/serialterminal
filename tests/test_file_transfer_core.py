import hashlib
from pathlib import Path
import random
import threading
import time

from serialterminal.file_transfer import (
    BinaryDelivery,
    Compression,
    DataMessage,
    EndMessage,
    FileTransferManager,
    MetaMessage,
    encode_message,
)
from serialterminal.file_transfer.protocol import data_payload_capacity


def _wait_until(predicate, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.01)
    return predicate()


class _PairBinaryTransport:
    payload_capacity = 200

    def __init__(self):
        self.receiver = None
        self.peer = None
        self.sent = []

    def set_receiver(self, receiver):
        self.receiver = receiver

    def send_binary(self, data, *, cancel_event=None):
        if cancel_event is not None and cancel_event.is_set():
            from serialterminal.file_transfer import BinaryUserCancelled

            raise BinaryUserCancelled()
        self.sent.append(bytes(data))
        if self.peer is not None and self.peer.receiver is not None:
            self.peer.receiver(bytes(data))
        return BinaryDelivery(tx_id=len(self.sent), user_id=f"TEST/{len(self.sent)}")


def _pair(tmp_path):
    left = _PairBinaryTransport()
    right = _PairBinaryTransport()
    left.peer = right
    right.peer = left
    tx = FileTransferManager(
        left,
        receive_dir=tmp_path / "left",
        id_factory=lambda: 0x1234,
        result_timeout_s=2.0,
    )
    rx = FileTransferManager(
        right,
        receive_dir=tmp_path / "right",
        id_factory=lambda: 0x5678,
        result_timeout_s=2.0,
    )
    return tx, rx, left, right


def test_file_transfer_compressed_end_to_end_and_remote_result(tmp_path):
    source = tmp_path / "source.txt"
    source.write_bytes(b"A" * 12000)
    tx, rx, _left, _right = _pair(tmp_path)
    try:
        started = tx.start_send(source)
        transfer_id = started["transfer_id"]

        done = _wait_until(
            lambda: (
                snapshot
                if (snapshot := tx.display_snapshot())
                and snapshot["state"] in {"completed", "failed"}
                else None
            )
        )
        assert done["state"] == "completed"
        assert done["percentage"] == 100.0
        assert done["wire_bytes"] < done["original_bytes"]
        assert done["chunks_completed"] == done["chunks_total"]

        received = _wait_until(
            lambda: (
                snapshot
                if (snapshot := rx.display_snapshot())
                and snapshot["state"] == "completed"
                else None
            )
        )
        final = Path(received["final_path"])
        assert final.read_bytes() == source.read_bytes()
        assert hashlib.sha256(final.read_bytes()).hexdigest() == hashlib.sha256(
            source.read_bytes()
        ).hexdigest()

        observed = tx.observe(
            transfer_id,
            cursor=0,
            window=100,
            timeout_ms=0,
        )
        assert observed["state"] == "completed"
        assert any(event["kind"] == "remote_result" for event in observed["events"])
    finally:
        tx.close()
        rx.close()


def test_file_transfer_uses_none_when_compression_does_not_help(tmp_path):
    source = tmp_path / "random.bin"
    source.write_bytes(random.Random(12345).randbytes(8192))
    tx, rx, _left, _right = _pair(tmp_path)
    try:
        tx.start_send(source)
        done = _wait_until(
            lambda: (
                snapshot
                if (snapshot := tx.display_snapshot())
                and snapshot["state"] == "completed"
                else None
            )
        )
        assert done["wire_bytes"] == done["original_bytes"]
        received = _wait_until(
            lambda: (
                snapshot
                if (snapshot := rx.display_snapshot())
                and snapshot["state"] == "completed"
                else None
            )
        )
        assert Path(received["final_path"]).read_bytes() == source.read_bytes()
    finally:
        tx.close()
        rx.close()


def test_receiver_accepts_out_of_order_and_duplicate_chunks(tmp_path):
    transport = _PairBinaryTransport()
    manager = FileTransferManager(
        transport,
        receive_dir=tmp_path / "rx",
        id_factory=lambda: 7,
    )
    try:
        payload = b"0123456789" * 50
        chunk_size = data_payload_capacity(200)
        chunks = [
            payload[offset : offset + chunk_size]
            for offset in range(0, len(payload), chunk_size)
        ]
        digest = hashlib.sha256(payload).digest()
        meta = MetaMessage(
            transfer_id=99,
            filename="data.bin",
            original_size=len(payload),
            wire_size=len(payload),
            compression=Compression.NONE,
            chunk_size=chunk_size,
            original_sha256=digest,
        )
        manager.feed_binary(encode_message(meta, 200))
        assert _wait_until(
            lambda: manager.display_snapshot()
            and manager.display_snapshot()["direction"] == "RX"
        )

        order = [1, 0, 1, 2]
        for index in order:
            manager.feed_binary(
                encode_message(
                    DataMessage(99, index, chunks[index]),
                    200,
                )
            )
        manager.feed_binary(
            encode_message(
                EndMessage(99, len(chunks), digest),
                200,
            )
        )

        done = _wait_until(
            lambda: (
                snapshot
                if (snapshot := manager.display_snapshot())
                and snapshot["state"] == "completed"
                else None
            )
        )
        assert done["chunks_completed"] == len(chunks)
        assert done["bytes_completed"] == len(payload)
        assert Path(done["final_path"]).read_bytes() == payload
    finally:
        manager.close()


def test_truncated_transfer_fails_and_leaves_no_final_or_part_file(tmp_path):
    transport = _PairBinaryTransport()
    receive_dir = tmp_path / "rx"
    manager = FileTransferManager(transport, receive_dir=receive_dir)
    try:
        payload = b"x" * 400
        digest = hashlib.sha256(payload).digest()
        chunk_size = data_payload_capacity(200)
        manager.feed_binary(
            encode_message(
                MetaMessage(
                    100,
                    "truncated.bin",
                    len(payload),
                    len(payload),
                    Compression.NONE,
                    chunk_size,
                    digest,
                ),
                200,
            )
        )
        assert _wait_until(lambda: manager.display_snapshot() is not None)
        manager.feed_binary(
            encode_message(
                DataMessage(100, 0, payload[:chunk_size]),
                200,
            )
        )
        manager.feed_binary(
            encode_message(
                EndMessage(100, 3, digest),
                200,
            )
        )

        failed = _wait_until(
            lambda: (
                snapshot
                if (snapshot := manager.display_snapshot())
                and snapshot["state"] == "failed"
                else None
            )
        )
        assert failed["failure"]["code"] == "missing_chunks"
        assert not (receive_dir / "truncated.bin").exists()
        assert not list(receive_dir.glob("*.part"))
    finally:
        manager.close()


def test_unsafe_filename_is_rejected_without_filesystem_escape(tmp_path):
    transport = _PairBinaryTransport()
    receive_dir = tmp_path / "rx"
    manager = FileTransferManager(transport, receive_dir=receive_dir)
    try:
        digest = hashlib.sha256(b"x").digest()
        manager.feed_binary(
            encode_message(
                MetaMessage(
                    101,
                    "../escape.bin",
                    1,
                    1,
                    Compression.NONE,
                    1,
                    digest,
                ),
                200,
            )
        )
        time.sleep(0.05)
        assert not (tmp_path / "escape.bin").exists()
        assert not receive_dir.exists() or not list(receive_dir.iterdir())
    finally:
        manager.close()


class _BlockingBinaryTransport:
    payload_capacity = 200

    def __init__(self):
        self.receiver = None
        self.started = threading.Event()

    def set_receiver(self, receiver):
        self.receiver = receiver

    def send_binary(self, data, *, cancel_event=None):
        self.started.set()
        while cancel_event is None or not cancel_event.wait(0.01):
            pass
        from serialterminal.file_transfer import BinaryUserCancelled

        raise BinaryUserCancelled()


def test_sender_cancellation_becomes_terminal_cancelled(tmp_path):
    source = tmp_path / "cancel.bin"
    source.write_bytes(b"x" * 1000)
    transport = _BlockingBinaryTransport()
    manager = FileTransferManager(
        transport,
        receive_dir=tmp_path / "rx",
        id_factory=lambda: 0xAA,
    )
    try:
        started = manager.start_send(source)
        assert transport.started.wait(timeout=1.0)
        manager.cancel(started["transfer_id"])
        cancelled = _wait_until(
            lambda: (
                snapshot
                if (snapshot := manager.display_snapshot())
                and snapshot["state"] == "cancelled"
                else None
            )
        )
        assert cancelled["failure"]["code"] == "cancelled"
    finally:
        manager.close()
