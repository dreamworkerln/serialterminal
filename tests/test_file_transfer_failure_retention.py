import hashlib
import random
import time

import pytest

from serialterminal.file_transfer import (
    BinarySendReceipt, BinaryUserError, Compression, DataMessage, EndMessage,
    FileTransferError, FileTransferManager, MetaMessage, MissingMessage, ResultMessage, ResumeMessage,
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
    assert manager._outbox.wait_idle(1)
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


def test_service_send_failure_retains_root_partial_and_manifest(tmp_path):
    transport = CaptureTransport()
    def fail_service(message):
        if isinstance(message, MetaMessage) and message.parent_transfer_id:
            raise BinaryUserError("send_rejected", "missing-list META queue full")
    transport.on_send = fail_service
    manager = FileTransferManager(transport, receive_dir=tmp_path, resume_handshake_timeout_s=0.01)
    try:
        meta, chunks, end = fixture(manager,count=5)
        for index in (0,2,3,4):
            manager._handle_data(DataMessage(meta.transfer_id,index,chunks[index]))
        manager._handle_end(end)
        assert wait_until(lambda: manager._records[meta.transfer_id].state == "failed")
        assert manager._records[meta.transfer_id].failure["code"] == "binary_send_failed"
        assert manager._resume_store.incoming_part(meta.transfer_id).read_bytes().startswith(chunks[0])
        assert manager._resume_store.load_incoming(meta.transfer_id)[0]["status"] == "suspended"
    finally:
        manager.close()


def test_percent_gate_retains_disjoint_partial_without_service_file(tmp_path):
    transport = CaptureTransport()
    manager = FileTransferManager(transport, receive_dir=tmp_path)
    try:
        meta, chunks, end = fixture(manager, count=60)
        for index in range(1, 60, 2):
            manager._handle_data(DataMessage(meta.transfer_id, index, chunks[index]))
        manager._handle_end(end)
        record = manager._records[meta.transfer_id]
        assert record.failure["code"] == "missing_percent_exceeded"
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
    manager = FileTransferManager(transport, receive_dir=tmp_path / "tx", resume_handshake_timeout_s=0.01)
    remote = None
    right = CaptureTransport()
    if path == "repair":
        remote = FileTransferManager(right, receive_dir=tmp_path / "rx", resume_handshake_timeout_s=0.01)
        right.on_send = lambda message: transport.receiver(encode_message(message,243))
    counts = {"end":0, "data":0}
    root_id = [None]
    def receive(message):
        if isinstance(message, MetaMessage) and message.depth == 0:
            root_id[0] = message.transfer_id
        if isinstance(message, EndMessage) and message.transfer_id == root_id[0]:
            counts["end"] += 1
        if isinstance(message, DataMessage) and message.transfer_id == root_id[0]:
            if path != "repair" or counts["end"]:
                counts["data"] += 1
                transport.receiver(encode_message(ResultMessage(message.transfer_id,False,"storage_failed","disk full"),243))
                return
            if message.chunk_index == 1:
                return
        if remote is not None:
            right.receiver(encode_message(message,243))
    transport.on_send = receive
    try:
        started = manager.start_send(source)
        transfer_id = int(started["transfer_id"],16)
        assert wait_until(lambda: manager._records[transfer_id].state == "failed")
        record = manager._records[transfer_id]
        assert record.failure["code"] == "remote_failed"
        assert record.remote_failure_event.is_set()
        assert not record.cancel_event.is_set()
        assert counts["data"] == 1
        if path == "repair":
            assert any(isinstance(m,MetaMessage) and m.parent_transfer_id == transfer_id for m in right.sent)
    finally:
        manager.close()
        if remote is not None:
            remote.close()


@pytest.mark.parametrize("cancel_in_flight", [False, True])
def test_cancel_then_close_does_not_resurrect_deleted_receiver(tmp_path, cancel_in_flight):
    import threading

    transport = CaptureTransport()
    manager = FileTransferManager(transport, receive_dir=tmp_path)
    entered, release, closing = threading.Event(), threading.Event(), threading.Event()
    errors = []
    original_result = manager._send_result
    original_data = manager._handle_data
    original_set_receiver = transport.set_receiver

    def blocked_result(record, result):
        if not result.ok:
            entered.set()
            assert release.wait(2)
        return original_result(record, result)

    def blocked_data(message):
        entered.set()
        assert release.wait(2)
        return original_data(message)

    def receiver_changed(receiver):
        if receiver is None:
            closing.set()
        return original_set_receiver(receiver)

    def close():
        try:
            manager.close()
        except Exception as exc:
            errors.append(exc)

    worker = None
    try:
        meta, chunks, _ = fixture(manager)
        manager._handle_data(DataMessage(meta.transfer_id, 0, chunks[0]))
        if cancel_in_flight:
            manager._send_result = blocked_result
            manager.cancel(meta.transfer_id)
        else:
            manager._handle_data = blocked_data
            manager.feed_binary(encode_message(DataMessage(meta.transfer_id, 1, chunks[1]), 243))
        assert entered.wait(1)
        if not cancel_in_flight:
            manager.cancel(meta.transfer_id)
        transport.set_receiver = receiver_changed
        worker = threading.Thread(target=close)
        worker.start()
        # close обязан сначала остановить RX, а не fsync уже удалённого part.
        closing.wait(.2)
        release.set()
        worker.join(3)
        assert not worker.is_alive()
        assert not errors, errors
        assert not manager._rx_thread.is_alive()
        assert manager._records[meta.transfer_id].state == "cancelled"
        assert manager._incoming is None
        assert not manager._resume_store.incoming_part(meta.transfer_id).exists()
        assert not manager._resume_store.incoming_manifest(meta.transfer_id).exists()
        assert not getattr(manager, "last_rx_worker_error", None)
    finally:
        release.set()
        if worker is not None:
            worker.join(3)
        manager._send_result = original_result
        manager._handle_data = original_data
        manager.close()


@pytest.mark.parametrize("stop_reason", ["remote_result", "operator_cancel"])
@pytest.mark.parametrize("wait_path", ["send", "prepare", "pipeline_submit", "pipeline_settle"])
def test_remote_failure_and_operator_cancel_interrupt_binary_wait_with_distinct_outcomes(tmp_path, wait_path, stop_reason):
    import threading
    from serialterminal.file_transfer import BinaryUserCancelled

    transport = CaptureTransport()
    source = tmp_path / "source.bin"
    source.write_bytes(random.Random(20).randbytes(227 * 6))
    entered = threading.Event()
    exited = threading.Event()
    requests = []
    manager = FileTransferManager(
        transport, receive_dir=tmp_path / "state",
        resume_handshake_timeout_s=0.01, local_recovery_retry_s=0.001,
    )
    original_send = transport.send_binary

    def blocked(cancel_event):
        entered.set()
        try:
            if cancel_event.wait(2):
                raise BinaryUserCancelled()
            raise BinaryUserError("binary_presentation_timeout", "wait was not interrupted")
        finally:
            exited.set()

    def send(data, *, cancel_event=None):
        message = decode_message(data)
        if isinstance(message, DataMessage):
            requests.append(message)
            if wait_path == "prepare":
                raise BinaryUserError("local_disconnect", "local readiness lost")
            blocked(cancel_event)
        return original_send(data, cancel_event=cancel_event)

    if wait_path.startswith("pipeline"):
        transport.pipeline_capacity = 2
        transport.discard_binary_pipeline = lambda: None
        def submit(data, *, cancel_event=None):
            message = decode_message(data)
            requests.append(message)
            if wait_path == "pipeline_submit":
                blocked(cancel_event)
            return BinarySendReceipt(len(requests))
        def settle(ticket, *, cancel_event=None):
            blocked(cancel_event)
        transport.submit_binary = submit
        transport.settle_binary = settle
    else:
        transport.send_binary = send
        if wait_path == "prepare":
            transport.prepare_binary = lambda *, deadline, cancel_event: blocked(cancel_event)

    try:
        started = manager.start_send(source)
        transfer_id = int(started["transfer_id"], 16)
        # Подготовка gzip/journal имеет отдельный бюджет; stop latency ниже — 0.5 s.
        assert entered.wait(5), manager.display_snapshot()
        record = manager._records[transfer_id]
        if stop_reason == "remote_result":
            record.set_remote_result(ResultMessage(transfer_id, False, "storage_failed", "disk full"))
        else:
            manager.cancel(transfer_id)
        assert exited.wait(0.5), "stop must wake binary wait promptly"
        expected_state = "failed" if stop_reason == "remote_result" else "cancelled"
        assert wait_until(lambda: record.state == expected_state)
        assert record.failure["code"] == ("remote_failed" if stop_reason == "remote_result" else "cancelled")
        if stop_reason == "remote_result":
            assert record.failure["details"]["remote_code"] == "storage_failed"
            assert not record.cancel_event.is_set()
            assert manager._resume_store.outgoing_manifest(transfer_id).is_file()
        else:
            assert record.cancel_event.is_set()
            assert not manager._resume_store.outgoing_manifest(transfer_id).exists()
        assert len(requests) == (2 if wait_path == "pipeline_settle" else 1)
    finally:
        manager.close()


def test_negative_result_after_readiness_prevents_replay_submission(tmp_path):
    transport = CaptureTransport()
    calls = []
    manager = FileTransferManager(transport, receive_dir=tmp_path, local_recovery_retry_s=0.001)
    record = manager._reserve_record(155, direction="TX", filename="x")
    def send(data, *, cancel_event=None):
        calls.append(data)
        if len(calls) == 1:
            raise BinaryUserError("local_disconnect", "disconnected")
        return BinarySendReceipt(len(calls))
    def ready(*, deadline, cancel_event=None):
        record.set_remote_result(ResultMessage(155, False, "storage_failed", "disk full"))
    transport.send_binary = send
    transport.prepare_binary = ready
    try:
        with pytest.raises(FileTransferError) as caught:
            manager._send_message(DataMessage(155, 0, b"x"), cancel_event=record.cancel_event)
        assert caught.value.code == "remote_failed"
        assert len(calls) == 1
        assert not record.cancel_event.is_set()
    finally:
        manager.close()


def test_overflow_failure_is_visible_and_does_not_kill_shared_rx_worker(tmp_path, monkeypatch):
    transport = CaptureTransport()
    manager = FileTransferManager(transport, receive_dir=tmp_path)
    try:
        meta, chunks, _ = fixture(manager)
        manager._handle_data(DataMessage(meta.transfer_id, 0, chunks[0]))
        part = manager._resume_store.incoming_part(meta.transfer_id)
        manifest = manager._resume_store.incoming_manifest(meta.transfer_id)
        original = manager._fail_incoming
        def broken(incoming, failure, **kwargs):
            if failure.code == "receiver_overflow":
                raise OSError("overflow checkpoint unavailable")
            return original(incoming, failure, **kwargs)
        monkeypatch.setattr(manager, "_fail_incoming", broken)
        manager._rx_overflow.set()
        manager._rx_queue.put(object())
        assert wait_until(lambda: manager._records[meta.transfer_id].state == "failed")
        assert manager._rx_thread.is_alive()
        assert part.read_bytes() == chunks[0]
        assert manifest.is_file()
        events = manager.observe(meta.transfer_id)["events"]
        assert any(item["kind"] == "rx_worker_error" and "overflow checkpoint" in item["error"] for item in events)
        assert wait_until(lambda: manager._active_id is None)
        other_meta, _, _ = fixture(manager, transfer_id=meta.transfer_id + 1)
        assert manager._incoming_for(other_meta.transfer_id) is not None
    finally:
        manager.close()



@pytest.mark.parametrize("failure_at", ["submit", "settle", "between_submissions"])
def test_remote_failure_preserves_primary_cause_and_lease_when_pipeline_drain_fails(tmp_path, failure_at):
    from serialterminal.file_transfer import BinaryUserCancelled

    transport = CaptureTransport()
    transport.pipeline_capacity = 2
    source = tmp_path / "source.bin"
    source.write_bytes(random.Random(21).randbytes(227 * 6))
    manager = FileTransferManager(transport, receive_dir=tmp_path / "state", resume_handshake_timeout_s=0.01)
    submitted = []
    def reject():
        record = manager._records[manager._active_id]
        record.set_remote_result(ResultMessage(record.transfer_id, False, "storage_failed", "disk full"))
    def submit(data, *, cancel_event=None):
        submitted.append(decode_message(data))
        if failure_at in {"submit", "between_submissions"}:
            reject()
            if failure_at == "submit":
                raise BinaryUserCancelled()
        return BinarySendReceipt(len(submitted))
    def settle(ticket, *, cancel_event=None):
        reject()
        raise BinaryUserCancelled()
    def unsettled(*args):
        raise BinaryUserError("local_tx_unsettled", "owned RF still pending")
    transport.submit_binary = submit
    transport.settle_binary = settle
    transport.discard_binary_pipeline = unsettled
    transport.drain_binary = unsettled
    try:
        started = manager.start_send(source)
        transfer_id = int(started["transfer_id"], 16)
        record = manager._records[transfer_id]
        assert wait_until(lambda: record.state == "failed")
        assert record.failure["code"] == "remote_failed"
        assert record.failure["details"]["remote_code"] == "storage_failed"
        assert manager._active_id == transfer_id
        assert manager._resume_store.outgoing_manifest(transfer_id).is_file()
        assert not record.cancel_event.is_set()
        events = manager.observe(transfer_id)["events"]
        assert any(item["kind"] == "pipeline_cleanup_failed" for item in events)
        assert any(item["kind"] == "local_tx_drain_failed" for item in events)
        assert len(submitted) == (2 if failure_at == "settle" else 1)
    finally:
        manager.close()
