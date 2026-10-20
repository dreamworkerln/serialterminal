import hashlib
import itertools
from pathlib import Path
import random
import threading
import time

import pytest

from serialterminal.file_transfer import (
    BinarySendReceipt,
    BinaryUserError,
    Compression,
    DataMessage,
    EndMessage,
    FileTransferManager,
    MetaMessage,
    MissingMessage,
    ResultMessage,
    encode_message,
    decode_message,
)
from recursive_evidence import service_requests
from serialterminal.file_transfer.core import default_receive_dir
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
        return BinarySendReceipt(tx_id=len(self.sent))


class _LegacyLifecycleTrapTransport(_PairBinaryTransport):
    def __init__(self):
        super().__init__()
        self.lifecycle = []

    def begin_transfer(self):
        self.lifecycle.append("begin")

    def end_transfer(self):
        self.lifecycle.append("end")


class _BlockingMetaBinaryTransport(_PairBinaryTransport):
    def __init__(self):
        super().__init__()
        self.started = threading.Event()
        self.release = threading.Event()

    def send_binary(self, data, *, cancel_event=None):
        self.started.set()
        self.release.wait(timeout=2.0)
        raise BinaryUserError("test_stop", "stop after metadata state check")


class _LossyPairBinaryTransport(_PairBinaryTransport):
    def __init__(self, drop_counts=None):
        super().__init__()
        self.drop_counts = dict(drop_counts or {})

    def send_binary(self, data, *, cancel_event=None):
        if cancel_event is not None and cancel_event.is_set():
            from serialterminal.file_transfer import BinaryUserCancelled

            raise BinaryUserCancelled()
        payload = bytes(data)
        self.sent.append(payload)
        message = decode_message(payload)
        key = None
        if isinstance(message, MetaMessage):
            key = ("meta", None)
        elif isinstance(message, DataMessage):
            key = ("data", message.chunk_index)
        elif isinstance(message, EndMessage):
            key = ("end", None)
        remaining = self.drop_counts.get(key, 0)
        if remaining > 0:
            self.drop_counts[key] = remaining - 1
            return BinarySendReceipt(tx_id=len(self.sent))
        if self.peer is not None and self.peer.receiver is not None:
            self.peer.receiver(payload)
        return BinarySendReceipt(tx_id=len(self.sent))


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


def test_truncated_transfer_requests_repair_and_keeps_temp_state(tmp_path):
    transport = _PairBinaryTransport()
    receive_dir = tmp_path / "rx"
    manager = FileTransferManager(transport, receive_dir=receive_dir)
    try:
        payload = b"x" * 700
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
        for index in range(3):
            manager.feed_binary(encode_message(DataMessage(100, index, payload[index*chunk_size:(index+1)*chunk_size]), 200))
        manager.feed_binary(
            encode_message(
                EndMessage(100, 4, digest),
                200,
            )
        )

        repairing = _wait_until(
            lambda: (
                snapshot
                if (snapshot := manager.display_snapshot())
                and snapshot["state"] == "repair_requested"
                else None
            )
        )
        assert repairing["state"] == "repair_requested"
        missing = _wait_until(lambda: service_requests(transport.sent, 100))
        assert len(missing) == 1
        assert [(r.start_chunk,r.count) for r in missing[0].ranges] == [(3,1)]
        assert not (receive_dir / "truncated.bin").exists()
        assert manager._resume_store.incoming_part(100).read_bytes() == payload[:3*chunk_size]
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
        if isinstance(decode_message(data), ResultMessage):
            return BinarySendReceipt(2)
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



def test_receiver_sha_mismatch_fails_without_final_file(tmp_path):
    transport = _PairBinaryTransport()
    receive_dir = tmp_path / "rx"
    manager = FileTransferManager(transport, receive_dir=receive_dir)
    try:
        payload = b"payload with bad declared sha"
        chunk_size = data_payload_capacity(200)
        manager.feed_binary(
            encode_message(
                MetaMessage(
                    202,
                    "badsha.bin",
                    len(payload),
                    len(payload),
                    Compression.NONE,
                    chunk_size,
                    hashlib.sha256(b"different").digest(),
                ),
                200,
            )
        )
        assert _wait_until(lambda: manager.display_snapshot() is not None)
        manager.feed_binary(
            encode_message(DataMessage(202, 0, payload), 200)
        )
        manager.feed_binary(
            encode_message(
                EndMessage(202, 1, hashlib.sha256(payload).digest()),
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
        assert failed["failure"]["code"] == "original_hash_mismatch"
        assert not (receive_dir / "badsha.bin").exists()
        part = manager._resume_store.incoming_part(202)
        assert part.read_bytes() == payload
        manifest, _ = manager._resume_store.load_incoming(202)
        assert manifest["status"] == "quarantined"
    finally:
        manager.close()


class _RemoteFailureTransport:
    payload_capacity = 200

    def __init__(self):
        self.receiver = None
        self.manager = None

    def set_receiver(self, receiver):
        self.receiver = receiver

    def send_binary(self, data, *, cancel_event=None):
        from serialterminal.file_transfer.protocol import (
            EndMessage,
            ResultMessage,
            decode_message,
            encode_message,
        )

        message = decode_message(data)
        if isinstance(message, EndMessage) and self.receiver is not None:
            self.receiver(
                encode_message(
                    ResultMessage(
                        transfer_id=message.transfer_id,
                        ok=False,
                        code="storage_failed",
                        reason="receiver disk full",
                    ),
                    200,
                )
            )
        return BinarySendReceipt(tx_id=1)


def test_sender_remote_result_failure_is_not_completed(tmp_path):
    source = tmp_path / "source.bin"
    source.write_bytes(b"x" * 100)
    transport = _RemoteFailureTransport()
    manager = FileTransferManager(
        transport,
        receive_dir=tmp_path / "rx",
        id_factory=lambda: 0x404,
        result_timeout_s=1.0,
    )
    try:
        manager.start_send(source)
        failed = _wait_until(
            lambda: (
                snapshot
                if (snapshot := manager.display_snapshot())
                and snapshot["state"] == "failed"
                else None
            )
        )
        assert failed["failure"]["code"] == "remote_failed"
        assert failed["failure"]["details"]["remote_code"] == "storage_failed"
        assert failed["percentage"] < 100.0
    finally:
        manager.close()



def _lossy_pair(tmp_path, drop_counts, *, replay_interval=0.05):
    left = _LossyPairBinaryTransport(drop_counts)
    right = _LossyPairBinaryTransport()
    left.peer = right
    right.peer = left
    tx_ids, rx_ids = itertools.count(0xABCD), itertools.count(0xDCBA)
    tx = FileTransferManager(
        left,
        receive_dir=tmp_path / "left-lossy",
        id_factory=lambda: next(tx_ids),
        result_timeout_s=2.0,
        control_replay_interval_s=replay_interval,
        max_control_replays=4,
        max_repair_rounds=6,
    )
    rx = FileTransferManager(
        right,
        receive_dir=tmp_path / "right-lossy",
        id_factory=lambda: next(rx_ids),
        result_timeout_s=2.0,
        control_replay_interval_s=replay_interval,
        max_control_replays=4,
        max_repair_rounds=6,
    )
    return tx, rx, left, right


def test_missing_chunks_are_selectively_repaired_without_resending_whole_file(tmp_path):
    source = tmp_path / "lossy.bin"
    source.write_bytes(random.Random(2026).randbytes(184 * 10))
    tx, rx, left, right = _lossy_pair(
        tmp_path,
        {
            ("data", 2): 1,
            ("data", 3): 1,
            ("data", 7): 1,
        },
    )
    try:
        started = tx.start_send(source)
        done = _wait_until(
            lambda: (
                snapshot
                if (snapshot := tx.display_snapshot())
                and snapshot["state"] in {"completed", "failed"}
                else None
            )
        )
        assert done["state"] == "completed"
        received = _wait_until(
            lambda: (
                snapshot
                if (snapshot := rx.display_snapshot())
                and snapshot["state"] == "completed"
                else None
            )
        )
        assert Path(received["final_path"]).read_bytes() == source.read_bytes()

        sent_data = [
            message
            for raw in left.sent
            if isinstance((message := decode_message(raw)), DataMessage)
        ]
        counts = {
            index: sum(item.chunk_index == index for item in sent_data)
            for index in range(10)
        }
        assert counts[2] == 2
        assert counts[3] == 2
        assert counts[7] == 2
        assert all(
            count == 1
            for index, count in counts.items()
            if index not in {2, 3, 7}
        )
        missing_messages = service_requests(right.sent, int(started["transfer_id"],16))
        assert len(missing_messages) == 1
        assert [(r.start_chunk, r.count) for r in missing_messages[0].ranges] == [
            (2, 2),
            (7, 1),
        ]

        observed = tx.observe(
            started["transfer_id"],
            cursor=0,
            window=100,
            timeout_ms=0,
        )
        assert any(event["kind"] == "repair_progress" for event in observed["events"])
    finally:
        tx.close()
        rx.close()


def test_second_repair_round_recovers_chunk_lost_during_first_repair(tmp_path):
    source = tmp_path / "two-rounds.bin"
    source.write_bytes(random.Random(77).randbytes(184 * 4))
    tx, rx, left, _right = _lossy_pair(
        tmp_path,
        {("data", 1): 2},
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
        assert done["state"] == "completed"
        sent_data = [
            message
            for raw in left.sent
            if isinstance((message := decode_message(raw)), DataMessage)
        ]
        assert sum(item.chunk_index == 1 for item in sent_data) == 3
    finally:
        tx.close()
        rx.close()


def test_lost_meta_hits_percent_gate_then_explicit_retry_keeps_identity(tmp_path):
    source = tmp_path / "miss-meta.bin"
    source.write_bytes(random.Random(99).randbytes(184 * 5))
    tx, rx, left, _right = _lossy_pair(
        tmp_path,
        {("meta", None): 1},
    )
    try:
        first = tx.start_send(source)
        done = _wait_until(
            lambda: (
                snapshot
                if (snapshot := tx.display_snapshot())
                and snapshot["state"] in {"completed", "failed"}
                else None
            ),
            timeout=4.0,
        )
        assert done["state"] == "failed"
        assert done["failure"]["details"]["remote_code"] == "missing_percent_exceeded"
        tx.join_all(1)
        second = tx.start_send(source)
        assert second["transfer_id"] == first["transfer_id"] and second["resumed"]
        completed = _wait_until(lambda: tx.display_snapshot() if tx.display_snapshot()["state"] == "completed" else None)
        assert completed["state"] == "completed"
        received = _wait_until(lambda: rx.display_snapshot() if rx.display_snapshot()["state"] == "completed" else None)
        assert Path(received["final_path"]).read_bytes() == source.read_bytes()
        meta_count = sum(
            isinstance(decode_message(raw), MetaMessage)
            for raw in left.sent
        )
        assert meta_count >= 2
    finally:
        tx.close()
        rx.close()


def test_control_replay_recovers_when_receiver_missed_initial_end(tmp_path):
    source = tmp_path / "miss-end.bin"
    source.write_bytes(random.Random(100).randbytes(184 * 3))
    tx, rx, left, _right = _lossy_pair(
        tmp_path,
        {("end", None): 1},
    )
    try:
        tx.start_send(source)
        done = _wait_until(
            lambda: (
                snapshot
                if (snapshot := tx.display_snapshot())
                and snapshot["state"] in {"completed", "failed"}
                else None
            ),
            timeout=4.0,
        )
        assert done["state"] == "completed"
        end_count = sum(
            isinstance(decode_message(raw), EndMessage)
            for raw in left.sent
        )
        assert end_count >= 2
    finally:
        tx.close()
        rx.close()


def test_repeated_identical_meta_and_end_are_idempotent_after_completion(tmp_path):
    source = tmp_path / "replay.bin"
    source.write_bytes(b"repeat me" * 50)
    tx, rx, left, right = _pair(tmp_path)
    try:
        tx.start_send(source)
        assert _wait_until(
            lambda: (
                snapshot
                if (snapshot := tx.display_snapshot())
                and snapshot["state"] == "completed"
                else None
            )
        )
        meta = next(
            message
            for raw in left.sent
            if isinstance((message := decode_message(raw)), MetaMessage)
        )
        end = next(
            message
            for raw in left.sent
            if isinstance((message := decode_message(raw)), EndMessage)
        )
        before = sum(
            isinstance(decode_message(raw), ResultMessage)
            for raw in right.sent
        )
        rx.feed_binary(encode_message(meta, 200))
        rx.feed_binary(encode_message(end, 200))
        assert _wait_until(
            lambda: sum(
                isinstance(decode_message(raw), ResultMessage)
                for raw in right.sent
            ) >= before + 2
        )
    finally:
        tx.close()
        rx.close()


def test_more_than_28_disjoint_holes_use_verified_service_file(tmp_path):
    source = tmp_path / "fragmented.bin"
    source.write_bytes(random.Random(303).randbytes(184 * 100))
    holes = set(range(0,60,2))
    tx, rx, left, right = _lossy_pair(tmp_path,{("data",index):1 for index in holes})
    try:
        started = tx.start_send(source)
        done = _wait_until(lambda: tx.display_snapshot() if tx.display_snapshot()["state"] in {"completed","failed"} else None)
        assert done["state"] == "completed", done
        received = _wait_until(lambda: rx.display_snapshot() if rx.display_snapshot()["state"] == "completed" else None)
        assert Path(received["final_path"]).read_bytes() == source.read_bytes()
        root_id = int(started["transfer_id"],16)
        lists = service_requests(right.sent,root_id)
        assert len(lists) == 1
        assert [(r.start_chunk,r.count) for r in lists[0].ranges] == [(index,1) for index in sorted(holes)]
        data = [m for raw in left.sent if isinstance((m:=decode_message(raw)),DataMessage) and m.transfer_id == root_id]
        assert all(sum(m.chunk_index == index for m in data) == (2 if index in holes else 1) for index in range(100))
        assert not any(isinstance(decode_message(raw),MissingMessage) for raw in right.sent)
    finally:
        tx.close()
        rx.close()



class _AmbiguousOncePairTransport(_PairBinaryTransport):
    def __init__(self, ambiguous_chunk):
        super().__init__()
        self.ambiguous_chunk = ambiguous_chunk
        self.injected = False

    def send_binary(self, data, *, cancel_event=None):
        from serialterminal.file_transfer import BinaryUserError

        payload = bytes(data)
        message = decode_message(payload)
        self.sent.append(payload)
        if self.peer is not None and self.peer.receiver is not None:
            self.peer.receiver(payload)
        if (
            isinstance(message, DataMessage)
            and message.chunk_index == self.ambiguous_chunk
            and not self.injected
        ):
            self.injected = True
            raise BinaryUserError(
                "local_tx_unknown",
                "simulated local transport ambiguity",
            )
        return BinarySendReceipt(tx_id=len(self.sent))


def test_file_layer_replays_same_idempotent_chunk_after_local_tx_unknown(tmp_path):
    source = tmp_path / "ambiguous.bin"
    source.write_bytes(random.Random(404).randbytes(184 * 3))
    left = _AmbiguousOncePairTransport(ambiguous_chunk=1)
    right = _PairBinaryTransport()
    left.peer = right
    right.peer = left
    tx = FileTransferManager(
        left,
        receive_dir=tmp_path / "left-ambiguous",
        id_factory=lambda: 0x1111,
        result_timeout_s=2.0,
    )
    rx = FileTransferManager(
        right,
        receive_dir=tmp_path / "right-ambiguous",
        id_factory=lambda: 0x2222,
        result_timeout_s=2.0,
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
        assert done["state"] == "completed"
        sent_data = [
            message
            for raw in left.sent
            if isinstance((message := decode_message(raw)), DataMessage)
        ]
        assert sum(item.chunk_index == 1 for item in sent_data) == 2
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



def test_default_receive_dir_is_serialterminal_source_root_files_directory():
    import serialterminal.file_transfer.core as core

    source_root = Path(core.__file__).resolve().parents[3]
    assert (source_root / "pyproject.toml").is_file()
    assert default_receive_dir() == source_root / "files"

    transport = _PairBinaryTransport()
    manager = FileTransferManager(transport)
    try:
        assert manager.receive_dir == source_root / "files"
    finally:
        manager.close()



def test_file_transfer_does_not_invoke_legacy_binary_transport_lifecycle(tmp_path):
    left = _LegacyLifecycleTrapTransport()
    right = _LegacyLifecycleTrapTransport()
    left.peer = right
    right.peer = left
    tx = FileTransferManager(
        left,
        receive_dir=tmp_path / "left-lifecycle",
        id_factory=lambda: 0x1111,
        result_timeout_s=2.0,
    )
    rx = FileTransferManager(
        right,
        receive_dir=tmp_path / "right-lifecycle",
        id_factory=lambda: 0x2222,
        result_timeout_s=2.0,
    )
    source = tmp_path / "lifecycle.bin"
    source.write_bytes(b"lifecycle" * 100)
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
        assert done["state"] == "completed"
        assert left.lifecycle == []
        assert right.lifecycle == []
    finally:
        tx.close()
        rx.close()


def test_file_transfer_leaves_compressing_before_metadata_binary_send_settles(tmp_path):
    source = tmp_path / "state.bin"
    source.write_bytes(b"A" * 4096)
    transport = _BlockingMetaBinaryTransport()
    manager = FileTransferManager(
        transport,
        receive_dir=tmp_path / "state-rx",
        id_factory=lambda: 0x3333,
        result_timeout_s=2.0,
    )
    try:
        manager.start_send(source)
        assert transport.started.wait(timeout=2.0)
        snapshot = manager.display_snapshot()
        assert snapshot is not None
        assert snapshot["state"] == "sending"
        assert snapshot["percentage"] == 0.0
    finally:
        transport.release.set()
        manager.join_all(2.0)
        manager.close()



def test_receiver_stale_meta_times_out_and_releases_session(tmp_path):
    transport = _PairBinaryTransport()
    manager = FileTransferManager(
        transport,
        receive_dir=tmp_path / "rx-stale",
        id_factory=lambda: 77,
        incoming_idle_timeout_s=0.05,
    )
    payload = b"x" * 20
    meta = MetaMessage(
        transfer_id=0x9001,
        filename="stale.bin",
        original_size=len(payload),
        wire_size=len(payload),
        compression=Compression.NONE,
        chunk_size=data_payload_capacity(200),
        original_sha256=hashlib.sha256(payload).digest(),
    )
    try:
        manager.feed_binary(encode_message(meta, 200))
        assert _wait_until(
            lambda: manager.display_snapshot()
            and manager.display_snapshot()["state"] == "receiving"
        )

        # Sweep thread is deliberately coarse in production; call the same
        # expiry routine directly so this unit regression stays deterministic.
        time.sleep(0.06)
        manager._expire_stale_incoming()

        failed = manager.display_snapshot()
        assert failed is not None
        assert failed["state"] == "failed"
        assert failed["failure"]["code"] == "remote_sender_timeout"

        next_source = tmp_path / "next.bin"
        next_source.write_bytes(b"next")
        started = manager.start_send(next_source)
        assert started["direction"] == "TX"
    finally:
        manager.close()


def test_receiver_activity_refreshes_stale_deadline(tmp_path):
    transport = _PairBinaryTransport()
    manager = FileTransferManager(
        transport,
        receive_dir=tmp_path / "rx-touch",
        incoming_idle_timeout_s=0.08,
    )
    payload = b"0123456789" * 10
    chunk_size = data_payload_capacity(200)
    meta = MetaMessage(
        transfer_id=0x9002,
        filename="touch.bin",
        original_size=len(payload),
        wire_size=len(payload),
        compression=Compression.NONE,
        chunk_size=chunk_size,
        original_sha256=hashlib.sha256(payload).digest(),
    )
    try:
        manager.feed_binary(encode_message(meta, 200))
        assert _wait_until(lambda: manager.display_snapshot() is not None)
        time.sleep(0.05)
        manager.feed_binary(
            encode_message(DataMessage(0x9002, 0, payload), 200)
        )
        assert _wait_until(
            lambda: manager.display_snapshot()
            and manager.display_snapshot()["chunks_completed"] == 1
        )
        time.sleep(0.05)
        manager._expire_stale_incoming()
        assert manager.display_snapshot()["state"] == "receiving"
    finally:
        manager.close()



def test_file_transfer_event_sink_records_message_stages_without_payload(tmp_path):
    events = []
    left = _PairBinaryTransport()
    right = _PairBinaryTransport()
    left.peer = right
    right.peer = left
    tx = FileTransferManager(
        left,
        receive_dir=tmp_path / "log-left",
        id_factory=lambda: 0xB01,
        result_timeout_s=2.0,
        event_sink=events.append,
    )
    rx = FileTransferManager(
        right,
        receive_dir=tmp_path / "log-right",
        id_factory=lambda: 0xB02,
        result_timeout_s=2.0,
    )
    source = tmp_path / "logged.bin"
    source.write_bytes(b"forensic-stage" * 40)
    try:
        tx.start_send(source)
        assert _wait_until(
            lambda: tx.display_snapshot()
            and tx.display_snapshot()["state"] == "completed"
        )
        starts = [event for event in events if event["kind"] == "binary_send_start"]
        settled = [event for event in events if event["kind"] == "binary_send_settled"]
        assert any(event["message_type"] == "META" for event in starts)
        assert any(event["message_type"] == "DATA" for event in starts)
        assert any(event["message_type"] == "END" for event in starts)
        assert len(settled) >= len(starts) - 1
        rendered = repr(events)
        assert "payload" not in rendered
        assert "base64" not in rendered
    finally:
        tx.close()
        rx.close()


class _DamagingPairBinaryTransport(_PairBinaryTransport):
    payload_capacity = 243

    def __init__(self, chunk_index, length_delta, damage_count, *, duplicate=False):
        super().__init__()
        self.chunk_index = chunk_index
        self.length_delta = length_delta
        self.damage_count = damage_count
        self.duplicate = duplicate

    def send_binary(self, data, *, cancel_event=None):
        if cancel_event is not None and cancel_event.is_set():
            from serialterminal.file_transfer import BinaryUserCancelled

            raise BinaryUserCancelled()
        payload = bytes(data)
        self.sent.append(payload)
        message = decode_message(payload)
        if (
            isinstance(message, DataMessage)
            and message.chunk_index == self.chunk_index
            and self.damage_count > 0
        ):
            self.damage_count -= 1
            if self.duplicate:
                self.peer.receiver(payload)
            changed = (
                message.payload[:self.length_delta]
                if self.length_delta < 0
                else message.payload + b"!" * self.length_delta
            )
            payload = encode_message(
                DataMessage(message.transfer_id, message.chunk_index, changed),
                self.payload_capacity,
            )
        self.peer.receiver(payload)
        return BinarySendReceipt(tx_id=len(self.sent))


@pytest.mark.parametrize(
    "chunk_index,length_delta,damage_count,duplicate",
    [
        (1, -48, 1, False),
        (1, -48, 2, False),
        (6, -7, 1, False),
        (6, 1, 1, False),
        (1, -48, 1, True),
    ],
)
def test_bad_length_chunk_is_selectively_repaired_without_losing_good_chunks(
    tmp_path, chunk_index, length_delta, damage_count, duplicate
):
    source = tmp_path / "damaged.bin"
    source.write_bytes(random.Random(834).randbytes(227 * 6 + 53))
    left = _DamagingPairBinaryTransport(
        chunk_index, length_delta, damage_count, duplicate=duplicate
    )
    right = _PairBinaryTransport()
    right.payload_capacity = 243
    left.peer = right
    right.peer = left
    tx = FileTransferManager(
        left, receive_dir=tmp_path / "sender", result_timeout_s=2.0
    )
    rx = FileTransferManager(
        right, receive_dir=tmp_path / "receiver", result_timeout_s=2.0
    )
    try:
        started = tx.start_send(source)
        done = _wait_until(
            lambda: snapshot
            if (snapshot := tx.display_snapshot())
            and snapshot["state"] in {"completed", "failed"}
            else None
        )
        assert done["state"] == "completed"
        received = _wait_until(
            lambda: snapshot
            if (snapshot := rx.display_snapshot())
            and snapshot["state"] == "completed"
            else None
        )
        final = Path(received["final_path"])
        assert final.read_bytes() == source.read_bytes()
        assert received["chunks_completed"] == received["chunks_total"] == 7
        assert received["percentage"] == 100.0
        sent_data = [
            message
            for raw in left.sent
            if isinstance((message := decode_message(raw)), DataMessage)
        ]
        for index in range(7):
            expected_count = (
                1 + damage_count if index == chunk_index and not duplicate else 1
            )
            assert sum(m.chunk_index == index for m in sent_data) == expected_count
        missing = service_requests(right.sent, int(started["transfer_id"],16))
        assert len(missing) == (0 if duplicate else damage_count)
        assert all(
            [(r.start_chunk, r.count) for r in message.ranges] == [(chunk_index, 1)]
            for message in missing
        )
        observed = rx.observe(
            started["transfer_id"], cursor=0, window=100, timeout_ms=0
        )
        rejected = [e for e in observed["events"] if e["kind"] == "chunk_rejected"]
        assert len(rejected) == damage_count
        expected_length = 53 if chunk_index == 6 else 227
        assert all(
            e["chunk_index"] == chunk_index
            and e["reason"] == "length_mismatch"
            and e["actual_length"] == expected_length + length_delta
            and e["expected_length"] == expected_length
            for e in rejected
        )
        assert not list((tmp_path / "receiver").glob("*.part"))
    finally:
        tx.close()
        rx.close()


def test_terminal_record_drains_host_writes_before_releasing_lease(tmp_path):
    order = []
    class DrainTransport(_PairBinaryTransport):
        def drain_binary(self, timeout_s):
            assert 0 < timeout_s <= 10.0
            order.append("drain")
            return {42: "cancelled"}
    manager = FileTransferManager(DrainTransport(), receive_dir=tmp_path, release_transfer=lambda *_: order.append("release"))
    try:
        record = manager._reserve_record(17, direction="TX", filename="x")
        manager._terminal_record(record, "failed")
        assert order == ["drain", "release"]
        assert manager._active_id is None
    finally:
        manager.close()


def test_drain_timeout_retains_lease_and_reports_failure(tmp_path):
    released = []
    class DrainTransport(_PairBinaryTransport):
        def drain_binary(self, timeout_s):
            raise BinaryUserError("local_tx_drain_timeout", "write still active")
    manager = FileTransferManager(DrainTransport(), receive_dir=tmp_path, release_transfer=lambda *_: released.append(True))
    try:
        record = manager._reserve_record(17, direction="TX", filename="x")
        manager._terminal_record(record, "failed")
        assert record.failure["code"] == "local_tx_drain_timeout"
        assert manager._active_id == 17
        assert released == []
    finally:
        manager.close()
