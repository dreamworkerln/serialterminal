import base64
import hashlib
import itertools
from pathlib import Path
import random
import time

import pytest

from serialterminal.file_transfer import (
    BinaryUserError, DataMessage, EndMessage, FileTransferManager,
    MetaMessage, ResultMessage, ResumeMessage, encode_message,
)
from serialterminal.file_transfer import core
from serialterminal.profiles.chatter.binary_pipeline import PipelinedChatterBinaryUserAdapter
from serialterminal.profiles.chatter.binary_user import ChatterBinaryUserAdapter
from test_file_transfer_failure_retention import CaptureTransport, fixture, wait_until


def test_same_process_retry_preserves_id_after_remote_failure_and_resumes_partial(tmp_path):
    source = tmp_path / "same-id.bin"
    payload = random.Random(51).randbytes(227 * 60)
    source.write_bytes(payload)
    left, right = CaptureTransport(), CaptureTransport()
    tx = FileTransferManager(left, receive_dir=tmp_path / "tx", id_factory=lambda: 121, result_timeout_s=1)
    rx = FileTransferManager(right, receive_dir=tmp_path / "rx")
    dropping = [True]
    def send_left(message):
        if dropping[0] and isinstance(message, DataMessage) and message.chunk_index % 2 == 0:
            return
        right.receiver(encode_message(message, 243))
    left.on_send = send_left
    right.on_send = lambda message: left.receiver(encode_message(message, 243))
    try:
        first = tx.start_send(source)
        assert wait_until(lambda: tx._records[121].state == "failed")
        tx.join_all(1)
        record = tx._records[121]
        assert record.remote_failure_event.is_set()
        assert rx._resume_store.load_incoming(121)[0]["status"] == "suspended"
        old_cursor = record._next_event_seq - 1
        sent_before = len(left.sent)
        dropping[0] = False
        second = tx.start_send(source)
        assert second["transfer_id"] == first["transfer_id"]
        assert second["resumed"]
        assert wait_until(lambda: tx._records[121].state == "completed")
        assert tx._records[121] is record
        assert record.failure is None
        assert not record.remote_failure_event.is_set()
        assert Path(rx._records[121].final_path).read_bytes() == payload
        assert len(list((tmp_path / "rx").glob("same-id*.bin"))) == 1
        assert any(isinstance(m, ResumeMessage) for m in right.sent)
        assert all(m.transfer_id == 121 for m in left.sent[sent_before:])
        assert tx.observe(121, cursor=old_cursor, window=100, timeout_ms=0)["events"]
    finally:
        tx.close()
        rx.close()


def failed_receiver(manager):
    meta, chunks, _ = fixture(manager, transfer_id=131)
    manager._handle_data(DataMessage(131, 0, chunks[0]))
    incoming = manager._incoming_for(131)
    manager._fail_incoming(incoming, core.FileTransferError("local_recovery_timeout", "timeout"))
    return meta, chunks


@pytest.mark.parametrize("failure_at", ["claim", "checkpoint"])
def test_failed_rx_restore_preserves_history_map_and_releases_reservation(tmp_path, monkeypatch, failure_at):
    transport = CaptureTransport()
    manager = FileTransferManager(transport, receive_dir=tmp_path)
    try:
        meta, chunks = failed_receiver(manager)
        record = manager._records[131]
        before = record.snapshot()
        manifest = manager._resume_store.load_incoming(131)[0]
        order = []
        def claim(*args):
            order.append("claim")
            if failure_at == "claim":
                raise core.FileTransferError("file_transfer_busy", "lease busy")
        manager.claim_transfer = claim
        manager.release_transfer = lambda *args: order.append("release")
        if failure_at == "checkpoint":
            def fail_checkpoint(*args, **kwargs):
                raise OSError("checkpoint failed")
            monkeypatch.setattr(manager, "_checkpoint_incoming", fail_checkpoint)
        manager._handle_meta(meta)
        assert manager._active_id is None and manager._incoming is None
        assert record.snapshot() == before
        assert manager._records[131] is record
        assert 131 in manager._terminal_order
        assert manager._resume_store.load_incoming(131)[0] == manifest
        assert manager._resume_store.incoming_part(131).read_bytes() == chunks[0]
        assert order == (["claim"] if failure_at == "claim" else ["claim", "release"])
        monkeypatch.undo()
        manager.claim_transfer = None
        manager._handle_meta(meta)
        assert manager._incoming_for(131) is not None
        assert record.failure is None and record.state == "receiving"
        assert 131 not in manager._terminal_order
    finally:
        manager.close()


def test_restart_checkpoint_failure_does_not_publish_phantom_rx_record(tmp_path, monkeypatch):
    manager = FileTransferManager(CaptureTransport(), receive_dir=tmp_path)
    meta, _ = failed_receiver(manager)
    manager.close()
    manager2 = FileTransferManager(CaptureTransport(), receive_dir=tmp_path)
    order = []
    manager2.claim_transfer = lambda *args: order.append("claim")
    manager2.release_transfer = lambda *args: order.append("release")
    def fail(*args, **kwargs):
        raise OSError("disk failed")
    monkeypatch.setattr(manager2, "_checkpoint_incoming", fail)
    try:
        with pytest.raises(OSError):
            manager2._restore_incoming(meta)
        assert manager2._records == {}
        assert manager2._active_id is None and manager2._incoming is None
        assert order == ["claim", "release"]
        assert manager2._resume_store.load_incoming(131) is not None
    finally:
        monkeypatch.undo()
        manager2.close()


def test_sender_claim_failure_keeps_failed_attempt_and_journal(tmp_path):
    source = tmp_path / "source.bin"
    source.write_bytes(random.Random(4).randbytes(900))
    transport = CaptureTransport()
    transport.on_send = lambda m: (_ for _ in ()).throw(BinaryUserError("send_rejected", "failed attempt"))
    manager = FileTransferManager(transport, receive_dir=tmp_path / "tx", id_factory=lambda: 141)
    try:
        manager.start_send(source)
        assert wait_until(lambda: manager._records[141].state == "failed")
        manager.join_all(1)
        record = manager._records[141]
        before = record.snapshot()
        journal = manager._resume_store.outgoing_manifest(141).read_bytes()
        def fail_claim(*args):
            raise core.FileTransferError("file_transfer_busy", "lease busy")
        manager.claim_transfer = fail_claim
        with pytest.raises(core.FileTransferError):
            manager.start_send(source)
        assert manager._records[141] is record and record.snapshot() == before
        assert manager._active_id is None
        assert 141 in manager._terminal_order
        assert manager._resume_store.outgoing_manifest(141).read_bytes() == journal
    finally:
        manager.close()


@pytest.mark.parametrize("pipeline", [False, True])
def test_lost_echo_after_delivery_blocks_new_binary_until_controller_reset(pipeline):
    sent = []
    delivered = []
    def send_line(text):
        sent.append(text)
        if text.startswith("/bin "):
            delivered.append(text)
        return {"tx_id": len(sent)}
    adapter_type = PipelinedChatterBinaryUserAdapter if pipeline else ChatterBinaryUserAdapter
    adapter = adapter_type(send_line, wait_tx_outcome=lambda *args: "written", presentation_timeout_s=0.01)
    adapter.feed_line("chat", "[SYS] current=CHAT")
    if pipeline:
        first = adapter.submit_binary(b"one")
        adapter.submit_binary(b"two")
        with pytest.raises(BinaryUserError):
            adapter.settle_binary(first)
    else:
        with pytest.raises(BinaryUserError):
            adapter.send_binary(b"one")
    count = len(sent)
    for _ in range(3):
        with pytest.raises(BinaryUserError) as caught:
            adapter.send_binary(b"one")
        assert caught.value.code == "local_tx_unsettled"
    assert len(sent) == count
    assert len(delivered) == (2 if pipeline else 1)
    adapter.feed_line("chat", "ESP-ROM:esp32s3-20210327")
    adapter.feed_line("chat", "[SYS] CHATTER READY")
    adapter.feed_line("chat", "[SYS] current=CHAT")
    def send_with_echo(text):
        result = send_line(text)
        adapter.feed_line("chat", "> [BINARY] " + base64.b64encode(b"one").decode())
        return result
    adapter._send_line = send_with_echo
    assert adapter.send_binary(b"one").tx_id == count + 1


def test_outer_result_deadline_bounds_nested_control_recovery(tmp_path):
    transport = CaptureTransport()
    calls = []
    def send_until(data, *, deadline, cancel_event=None):
        calls.append(deadline)
        raise BinaryUserError("local_disconnect", "disconnected")
    transport.send_binary_until = send_until
    manager = FileTransferManager(transport, receive_dir=tmp_path, local_recovery_timeout_s=10, local_recovery_retry_s=0.01)
    record = manager._reserve_record(151, direction="TX", filename="x")
    deadline = time.monotonic() + 0.03
    try:
        with pytest.raises(core.FileTransferError) as caught:
            manager._send_message(EndMessage(151, 0, hashlib.sha256(b"").digest()), cancel_event=record.cancel_event, deadline=deadline)
        assert caught.value.code == "remote_result_timeout"
        assert calls and all(value <= deadline for value in calls)
        assert time.monotonic() < deadline + 0.15
    finally:
        manager.close()


def test_lease_rollback_failure_keeps_admission_blocked(tmp_path, monkeypatch):
    manager = FileTransferManager(CaptureTransport(), receive_dir=tmp_path)
    meta, _ = failed_receiver(manager)
    manager.claim_transfer = lambda *args: None
    def fail(*args, **kwargs):
        raise OSError("rollback failed")
    manager.release_transfer = fail
    monkeypatch.setattr(manager, "_checkpoint_incoming", fail)
    try:
        manager._handle_meta(meta)
        assert manager._active_id == meta.transfer_id
        assert manager._incoming is None
        assert manager._records[meta.transfer_id].state == "failed"
        with pytest.raises(core.FileTransferError) as caught:
            manager._reserve_record(999, direction="TX", filename="x")
        assert caught.value.code == "file_transfer_busy"
        observed = manager.observe(meta.transfer_id, cursor=0, window=100, timeout_ms=0)
        assert any(e["kind"] == "resume_rollback_failed" for e in observed["events"])
    finally:
        monkeypatch.undo()
        manager.release_transfer = None
        manager.close()


def test_same_process_publishing_failure_reconciles_single_destination(tmp_path, monkeypatch):
    transport = CaptureTransport()
    manager = FileTransferManager(transport, receive_dir=tmp_path)
    meta, chunks, end = fixture(manager, transfer_id=161)
    for index, chunk in enumerate(chunks):
        manager._handle_data(DataMessage(meta.transfer_id, index, chunk))
    def fail(*args, **kwargs):
        raise OSError("tombstone unavailable")
    monkeypatch.setattr(manager._resume_store, "save_completed", fail)
    try:
        manager._handle_end(end)
        assert manager._records[161].state == "failed"
        assert manager._resume_store.load_incoming(161)[0]["status"] == "publishing"
        monkeypatch.undo()
        manager._handle_meta(meta)
        assert manager._records[161].state == "completed"
        assert manager._records[161].failure is None
        assert manager._records[161].rx_end == end
        assert len(list(tmp_path.glob("retained*.bin"))) == 1
        assert (tmp_path / meta.filename).read_bytes() == b"".join(chunks)
    finally:
        monkeypatch.undo()
        manager.close()


@pytest.mark.parametrize("message_type", [MetaMessage, ResultMessage])
@pytest.mark.parametrize("permanent", [False, True])
def test_lost_control_is_bounded_and_explicit_retry_keeps_identity(tmp_path, message_type, permanent):
    source = tmp_path / "control.bin"
    payload = random.Random(15).randbytes(227 * 4)
    source.write_bytes(payload)
    left, right = CaptureTransport(), CaptureTransport()
    # Outbox и durable publication асинхронны: 20 ms replay interval расходовал
    # два повтора раньше fsync/RESULT (~140 ms в полном прогоне). Проверяем
    # ограниченное число control replay и внешнюю границу завершения <1 s.
    ids = itertools.count(171)
    tx = FileTransferManager(left, receive_dir=tmp_path / "tx", id_factory=lambda: next(ids),
                             result_timeout_s=0.3, control_replay_interval_s=0.08,
                             max_control_replays=2, resume_handshake_timeout_s=0.02)
    rx = FileTransferManager(right, receive_dir=tmp_path / "rx", control_replay_interval_s=0.08, max_control_replays=2, resume_handshake_timeout_s=0.02)
    dropped_data = [False]
    dropped_control = [False]
    loss_enabled = [True]
    def send_left(message):
        if message_type is MetaMessage and isinstance(message, DataMessage) and message.chunk_index == 1 and not dropped_data[0]:
            dropped_data[0] = True
            return
        right.receiver(encode_message(message, 243))
    def send_right(message):
        if isinstance(message, message_type) and (message_type is not MetaMessage or message.parent_transfer_id != 0) and loss_enabled[0] and (permanent or not dropped_control[0]):
            dropped_control[0] = True
            return
        left.receiver(encode_message(message, 243))
    left.on_send = send_left
    right.on_send = send_right
    started = time.monotonic()
    try:
        first = tx.start_send(source)
        assert wait_until(lambda: tx._records[171].state in {"completed", "failed"})
        tx.join_all(1)
        assert time.monotonic() - started < 1
        assert dropped_control[0]
        if permanent:
            assert tx._records[171].failure["code"] in {"remote_result_timeout", "remote_failed"}
            if tx._records[171].failure["code"] == "remote_failed":
                assert tx._records[171].failure["details"]["remote_code"] == "remote_result_timeout"
            assert tx._resume_store.outgoing_manifest(171).is_file()
            if message_type is MetaMessage:
                assert rx._resume_store.incoming_part(171).is_file()
            # У ROOT и потерянного child независимые control budgets. Перед
            # явным resume ждём settlement обеих сторон, иначе старый child
            # ещё владеет RX и может прислать RESULT предыдущей попытки.
            assert wait_until(lambda: rx._records[171].state in {"completed", "failed"})
            assert rx._outbox.wait_idle(1)
            assert time.monotonic() - started < 1
            loss_enabled[0] = False
            second = tx.start_send(source)
            assert second["transfer_id"] == first["transfer_id"] and second["resumed"]
            assert wait_until(lambda: tx._records[171].state == "completed"), tx._records[171].snapshot()
        else:
            assert tx._records[171].state == "completed", tx._records[171].snapshot()
        assert Path(rx._records[171].final_path).read_bytes() == payload
        assert len(list((tmp_path / "rx").glob("control*.bin"))) == 1
    finally:
        tx.close()
        rx.close()


def test_manager_close_during_rx_claim_rolls_back_without_reviving(tmp_path):
    manager = FileTransferManager(CaptureTransport(), receive_dir=tmp_path)
    meta, _ = failed_receiver(manager)
    before = manager._records[131].snapshot()
    order = []
    def close_during_claim(*args):
        order.append("claim")
        manager._stopping.set()
    manager.claim_transfer = close_during_claim
    manager.release_transfer = lambda *args: order.append("release")
    try:
        manager._handle_meta(meta)
        assert order == ["claim", "release"]
        assert manager._active_id is None and manager._incoming is None
        assert manager._records[131].snapshot() == before
    finally:
        manager.close()


def test_sender_thread_start_failure_releases_lease(tmp_path, monkeypatch):
    source = tmp_path / "source.bin"
    source.write_bytes(b"source")
    manager = FileTransferManager(CaptureTransport(), receive_dir=tmp_path / "tx", id_factory=lambda: 181)
    released = []
    manager.release_transfer = lambda *args: released.append(args)
    def fail(*args):
        raise RuntimeError("thread unavailable")
    monkeypatch.setattr("serialterminal.file_transfer.resumable.threading.Thread.start", fail)
    try:
        with pytest.raises(core.FileTransferError) as caught:
            manager.start_send(source)
        assert caught.value.code == "local_failure"
        assert manager._active_id is None
        assert released == [(181, "TX")]
        assert manager._records[181].state == "failed"
    finally:
        monkeypatch.undo()
        manager.close()


def test_manager_close_during_sender_claim_rolls_back(tmp_path):
    manager = FileTransferManager(CaptureTransport(), receive_dir=tmp_path)
    released = []
    manager.claim_transfer = lambda *args: manager._stopping.set()
    manager.release_transfer = lambda *args: released.append(args)
    try:
        with pytest.raises(core.FileTransferError) as caught:
            manager._reserve_record(191, direction="TX", filename="x")
        assert caught.value.code == "local_shutdown"
        assert released == [(191, "TX")]
        assert manager._active_id is None and manager._records == {}
    finally:
        manager.close()
