import hashlib
import random
import time

import pytest

from serialterminal.file_transfer import (
    BinarySendReceipt, BinaryUserError, Compression, DataMessage, EndMessage,
    FileTransferManager, MetaMessage, MissingMessage, ResultMessage, ResumeMessage,
    decode_message, encode_message,
)
from serialterminal.file_transfer.protocol import data_payload_capacity


class CaptureTransport:
    payload_capacity = 243

    def __init__(self):
        self.sent = []
        self.receiver = None
        self.on_send = None

    def set_receiver(self, receiver):
        self.receiver = receiver

    def send_binary(self, data, *, cancel_event=None):
        message = decode_message(data)
        self.sent.append(message)
        if self.on_send is not None:
            self.on_send(message)
        return BinarySendReceipt(len(self.sent))


def fixture(manager, transfer_id=71, count=3):
    payload = random.Random(9).randbytes(data_payload_capacity(243) * count)
    size = data_payload_capacity(243)
    meta = MetaMessage(transfer_id, "retained.bin", len(payload), len(payload),
                       Compression.NONE, size, hashlib.sha256(payload).digest())
    chunks = [payload[i:i + size] for i in range(0, len(payload), size)]
    end = EndMessage(transfer_id, count, hashlib.sha256(payload).digest())
    manager._handle_meta(meta)
    return meta, chunks, end


def wait_until(predicate):
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def test_bad_index_and_end_keep_good_chunks_and_allow_completion(tmp_path):
    transport = CaptureTransport()
    manager = FileTransferManager(transport, receive_dir=tmp_path)
    try:
        meta, chunks, end = fixture(manager)
        manager._handle_data(DataMessage(meta.transfer_id, 0, chunks[0]))
        incoming = manager._incoming_for(meta.transfer_id)
        last_activity = incoming.last_activity_monotonic
        manager._handle_data(DataMessage(meta.transfer_id, 100, chunks[0]))
        manager._handle_end(EndMessage(meta.transfer_id, 99, end.wire_sha256))
        assert manager._incoming_for(meta.transfer_id) is incoming
        assert incoming.received == {0: len(chunks[0])}
        assert incoming.wire_path.read_bytes() == chunks[0]
        assert incoming.last_activity_monotonic == last_activity
        for index, chunk in enumerate(chunks[1:], 1):
            manager._handle_data(DataMessage(meta.transfer_id, index, chunk))
        manager._handle_end(end)
        assert (tmp_path / meta.filename).read_bytes() == b"".join(chunks)
        assert manager._records[meta.transfer_id].state == "completed"
    finally:
        manager.close()


def test_failed_creation_does_not_delete_preexisting_retained_part(tmp_path):
    manager = FileTransferManager(CaptureTransport(), receive_dir=tmp_path)
    part = manager._resume_store.incoming_part(72)
    part.parent.mkdir(parents=True, exist_ok=True)
    part.write_bytes(b"valuable retained bytes")
    try:
        fixture(manager, transfer_id=72)
        assert part.read_bytes() == b"valuable retained bytes"
        assert manager._incoming is None
    finally:
        manager.close()


def test_conflicting_duplicate_is_quarantined_and_not_resumed_after_restart(tmp_path):
    transport = CaptureTransport()
    manager = FileTransferManager(transport, receive_dir=tmp_path)
    meta, chunks, _ = fixture(manager)
    try:
        manager._handle_data(DataMessage(meta.transfer_id, 0, chunks[0]))
        conflict = bytes([chunks[0][0] ^ 1]) + chunks[0][1:]
        manager._handle_data(DataMessage(meta.transfer_id, 0, conflict))
        assert manager._records[meta.transfer_id].state == "failed"
        assert manager._resume_store.incoming_part(meta.transfer_id).read_bytes() == chunks[0]
        assert manager._resume_store.load_incoming(meta.transfer_id)[0]["status"] == "quarantined"
    finally:
        manager.close()
    transport2 = CaptureTransport()
    manager2 = FileTransferManager(transport2, receive_dir=tmp_path)
    try:
        manager2._handle_meta(meta)
        assert manager2._incoming is None
        assert not any(isinstance(m, ResumeMessage) for m in transport2.sent)
        assert manager2._resume_store.incoming_part(meta.transfer_id).is_file()
    finally:
        manager2.close()


def test_missing_send_failure_retains_partial_and_manifest(tmp_path):
    transport = CaptureTransport()
    def fail_missing(message):
        if isinstance(message, MissingMessage):
            raise BinaryUserError("send_rejected", "MISSING queue full")
    transport.on_send = fail_missing
    manager = FileTransferManager(transport, receive_dir=tmp_path)
    try:
        meta, chunks, end = fixture(manager)
        manager._handle_data(DataMessage(meta.transfer_id, 0, chunks[0]))
        manager._handle_end(end)
        assert manager._records[meta.transfer_id].state == "failed"
        assert manager._resume_store.incoming_part(meta.transfer_id).read_bytes() == chunks[0]
        assert manager._resume_store.load_incoming(meta.transfer_id)[0]["status"] == "suspended"
    finally:
        manager.close()


def test_missing_range_overflow_retains_partial_with_no_pagination(tmp_path):
    transport = CaptureTransport()
    manager = FileTransferManager(transport, receive_dir=tmp_path)
    try:
        meta, chunks, end = fixture(manager, count=60)
        for index in range(1, 60, 2):
            manager._handle_data(DataMessage(meta.transfer_id, index, chunks[index]))
        manager._handle_end(end)
        record = manager._records[meta.transfer_id]
        assert record.failure["code"] == "repair_too_large"
        assert manager._resume_store.incoming_part(meta.transfer_id).is_file()
        assert len(manager._resume_store.load_incoming(meta.transfer_id)[0]["received_ranges"]) == 30
        assert not any(isinstance(m, MissingMessage) for m in transport.sent)
    finally:
        manager.close()


@pytest.mark.parametrize("path", ["original", "pipeline", "repair"])
def test_negative_result_stops_new_data_without_operator_cancel(tmp_path, path):
    transport = CaptureTransport()
    if path == "pipeline":
        transport.pipeline_capacity = 2
        transport.submit_binary = transport.send_binary
        transport.settle_binary = lambda ticket, **kwargs: ticket
        transport.discard_binary_pipeline = lambda: None
    source = tmp_path / "source.bin"
    source.write_bytes(random.Random(2).randbytes(227 * 6))
    manager = FileTransferManager(transport, receive_dir=tmp_path / "rx", resume_handshake_timeout_s=0.01)
    counts = {"end": 0, "data": 0}
    def receive(message):
        if isinstance(message, EndMessage):
            counts["end"] += 1
            if path == "repair" and counts["end"] == 1:
                from serialterminal.file_transfer import MissingRange
                transport.receiver(encode_message(MissingMessage(message.transfer_id, (MissingRange(0, 6),)), 243))
        if isinstance(message, DataMessage):
            if path != "repair" or counts["end"]:
                counts["data"] += 1
                transport.receiver(encode_message(ResultMessage(message.transfer_id, False, "storage_failed", "disk full"), 243))
    transport.on_send = receive
    try:
        started = manager.start_send(source)
        transfer_id = int(started["transfer_id"], 16)
        assert wait_until(lambda: manager._records[transfer_id].state == "failed")
        record = manager._records[transfer_id]
        assert record.failure["code"] == "remote_failed"
        assert record.remote_failure_event.is_set()
        assert not record.cancel_event.is_set()
        assert counts["data"] == 1
    finally:
        manager.close()
