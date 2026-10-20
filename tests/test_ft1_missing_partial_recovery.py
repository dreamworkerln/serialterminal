from dataclasses import replace
import errno
import itertools
from pathlib import Path
import random

import pytest

from serialterminal.file_transfer import (
    BinaryUserError, DataMessage, FileTransferManager, ResumeMessage, encode_message,
)
from serialterminal.file_transfer.resume_store import ResumeStateStore
from serialterminal.tui_file_transfer import file_transfer_status_line
from test_file_transfer_failure_retention import CaptureTransport, fixture, wait_until
from test_ft1_live_retention import retained


def suspend(manager):
    meta, chunks, end = fixture(manager, transfer_id=0x5670)
    manager._handle_data(DataMessage(meta.transfer_id, 0, chunks[0]))
    manager._suspend_incoming(manager._incoming_for(meta.transfer_id), reason="test_restart")
    assert manager._outbox.wait_idle(1)
    return meta, chunks, end


@pytest.mark.parametrize("restart_sender", [False, True])
def test_paired_retry_recovers_missing_partial_and_completes_same_id(tmp_path, restart_sender):
    source = tmp_path / "2.png"
    expected = random.Random(56).randbytes(227 * 6)
    source.write_bytes(expected)
    left, right = CaptureTransport(), CaptureTransport()
    ids = itertools.count(1000)
    tx = FileTransferManager(left, receive_dir=tmp_path / "tx", peer_key="sender-node",
                             id_factory=lambda: next(ids), resume_handshake_timeout_s=.1)
    rx = FileTransferManager(right, receive_dir=tmp_path / "rx")

    def interrupted(message):
        if isinstance(message, DataMessage) and message.chunk_index == 2:
            raise BinaryUserError("send_rejected", "first attempt interrupted")
        right.receiver(encode_message(message, 243))

    left.on_send = interrupted
    right.on_send = lambda message: left.receiver(encode_message(message, 243))
    try:
        first = tx.start_send(source)
        transfer_id = int(first["transfer_id"], 16)
        assert wait_until(lambda: tx._records[transfer_id].state == "failed")
        tx.join_all(1)
        assert wait_until(lambda: rx._incoming is not None and len(rx._incoming.received) >= 2)
        rx.close()
        part = rx._resume_store.incoming_part(transfer_id)
        old = rx._resume_store.load_incoming(transfer_id)[0]
        assert old["received_ranges"]
        part.unlink()
        if restart_sender:
            tx.close()
            left = CaptureTransport()
            tx = FileTransferManager(left, receive_dir=tmp_path / "tx", peer_key="sender-node",
                                     id_factory=lambda: next(ids), resume_handshake_timeout_s=.1)
        right = CaptureTransport()
        rx = FileTransferManager(right, receive_dir=tmp_path / "rx")
        left.on_send = lambda message: right.receiver(encode_message(message, 243))
        right.on_send = lambda message: left.receiver(encode_message(message, 243))
        cursor = len(left.sent)

        second = tx.start_send(source)

        assert second["transfer_id"] == first["transfer_id"]
        assert second["resumed"]
        assert wait_until(lambda: tx._records[transfer_id].state == "completed")
        assert rx._outbox.wait_idle(1)
        assert (tmp_path / "rx" / source.name).read_bytes() == expected
        assert len(list((tmp_path / "rx").glob("2*.png"))) == 1
        assert any(isinstance(message, ResumeMessage) and message.next_chunk == 0
                   for message in right.sent)
        assert next(message for message in left.sent[cursor:]
                    if isinstance(message, DataMessage)).chunk_index == 0
        events = rx.observe(transfer_id, window=100)["events"]
        reset = [event for event in events if event["kind"] == "resume_state_reset"]
        assert len(reset) == 1 and reset[0]["reason"] == "missing_partial"
        assert reset[0]["previous_chunks"] >= 2 and reset[0]["next_chunk"] == 0
        assert "приём с начала" in file_transfer_status_line(reset[0])
    finally:
        tx.close()
        rx.close()


def test_same_process_suspended_rx_missing_part_resets_progress_and_proof(tmp_path):
    transport = CaptureTransport()
    manager = FileTransferManager(transport, receive_dir=tmp_path)
    try:
        meta, chunks, end = suspend(manager)
        record = manager._records[meta.transfer_id]
        manager._resume_store.incoming_part(meta.transfer_id).unlink()
        manager._handle_meta(meta)
        assert manager._outbox.wait_idle(1)
        assert manager._incoming.record is record
        assert record.chunks_completed == record.bytes_completed == 0
        assert manager._resume_store.load_incoming(meta.transfer_id)[0]["received_ranges"] == []
        assert isinstance(transport.sent[-1], ResumeMessage)
        assert transport.sent[-1].next_chunk == 0
        for index, chunk in enumerate(chunks):
            manager._handle_data(DataMessage(meta.transfer_id, index, chunk))
        manager._handle_end(end)
        assert wait_until(lambda: record.state == "completed")
        assert (tmp_path / meta.filename).read_bytes() == b"".join(chunks)
    finally:
        manager.close()


@pytest.mark.parametrize("fault", ["zero_before", "zero_after", "create", "checkpoint"])
def test_reset_failure_never_restores_old_ranges_beside_new_empty_part(tmp_path, monkeypatch, fault):
    manager = FileTransferManager(CaptureTransport(), receive_dir=tmp_path)
    try:
        meta, chunks, end = suspend(manager)
        part = manager._resume_store.incoming_part(meta.transfer_id)
        part.unlink()
        fired = [False]
        atomic = manager._resume_store.atomic_json
        checkpoint = manager._checkpoint_incoming
        original_open = Path.open

        def atomic_failure(path, payload):
            if fault in {"zero_before", "zero_after"} and not fired[0]:
                fired[0] = True
                if fault == "zero_after":
                    atomic(path, payload)
                raise OSError(errno.EIO, fault)
            return atomic(path, payload)

        def create_failure(path, mode="r", *args, **kwargs):
            if fault == "create" and path == part and mode == "xb" and not fired[0]:
                fired[0] = True
                raise OSError(errno.EIO, fault)
            return original_open(path, mode, *args, **kwargs)

        def checkpoint_failure(*args, **kwargs):
            if fault == "checkpoint" and not fired[0]:
                fired[0] = True
                raise OSError(errno.EIO, fault)
            return checkpoint(*args, **kwargs)

        with monkeypatch.context() as patch:
            patch.setattr(manager._resume_store, "atomic_json", atomic_failure)
            patch.setattr(Path, "open", create_failure)
            patch.setattr(manager, "_checkpoint_incoming", checkpoint_failure)
            with pytest.raises(OSError):
                manager._restore_incoming(meta, existing=manager._records[meta.transfer_id])
        assert fired[0]
        assert manager._incoming is None and manager._active_id is None
        durable = manager._resume_store.load_incoming(meta.transfer_id)[0]
        assert durable["status"] == "suspended" and durable["received_ranges"] == []
        assert not part.exists() or part.stat().st_size == 0
        manager._handle_meta(meta)
        assert manager._outbox.wait_idle(1)
        assert manager._incoming.received.ranges() == []
        for index, chunk in enumerate(chunks):
            manager._handle_data(DataMessage(meta.transfer_id, index, chunk))
        manager._handle_end(end)
        assert wait_until(lambda: manager._records[meta.transfer_id].state == "completed")
        assert (tmp_path / meta.filename).read_bytes() == b"".join(chunks)
    finally:
        manager.close()


def test_other_owner_blocks_reset_without_modifying_manifest(tmp_path):
    manager = FileTransferManager(CaptureTransport(), receive_dir=tmp_path)
    owner = ResumeStateStore(tmp_path / ".serialterminal-state")
    try:
        meta, _, _ = suspend(manager)
        manager.close()
        manager = FileTransferManager(CaptureTransport(), receive_dir=tmp_path)
        part = manager._resume_store.incoming_part(meta.transfer_id)
        part.unlink()
        manifest = manager._resume_store.incoming_manifest(meta.transfer_id)
        before = manifest.read_bytes()
        owner.claim("incoming", meta.transfer_id)
        with pytest.raises(OSError, match="another live owner"):
            manager._restore_incoming(meta)
        assert manifest.read_bytes() == before
        assert not part.exists()
    finally:
        owner.release_all()
        manager.close()


def test_reset_checkpoint_failure_then_close_does_not_republish_cached_ranges(tmp_path, monkeypatch):
    manager = FileTransferManager(CaptureTransport(), receive_dir=tmp_path)
    try:
        meta, chunks, end = suspend(manager)
        part = manager._resume_store.incoming_part(meta.transfer_id)
        part.unlink()
        with monkeypatch.context() as patch:
            def failed_checkpoint(*args, **kwargs):
                raise OSError(errno.EIO, "checkpoint failure")
            patch.setattr(manager, "_checkpoint_incoming", failed_checkpoint)
            with pytest.raises(OSError, match="checkpoint failure"):
                manager._restore_incoming(meta, existing=manager._records[meta.transfer_id])
        manager.close()
        assert part.stat().st_size == 0
        assert manager._resume_store.load_incoming(meta.transfer_id)[0]["received_ranges"] == []
        manager = FileTransferManager(CaptureTransport(), receive_dir=tmp_path)
        manager._handle_meta(meta)
        assert manager._outbox.wait_idle(1)
        assert len(manager._incoming.received) == 0
        for index, chunk in enumerate(chunks):
            manager._handle_data(DataMessage(meta.transfer_id, index, chunk))
        manager._handle_end(end)
        assert wait_until(lambda: manager._records[meta.transfer_id].state == "completed")
        assert (tmp_path / meta.filename).read_bytes() == b"".join(chunks)
    finally:
        manager.close()


def test_existing_partial_and_conflicting_meta_are_not_reset(tmp_path):
    manager = FileTransferManager(CaptureTransport(), receive_dir=tmp_path)
    try:
        meta, chunks, _ = suspend(manager)
        part = manager._resume_store.incoming_part(meta.transfer_id)
        original = part.read_bytes()
        assert manager._restore_incoming(replace(meta, filename="conflict.bin")) is None
        assert part.read_bytes() == original
        manager._handle_meta(meta)
        assert manager._outbox.wait_idle(1)
        assert manager._incoming.received.ranges() == [[0, 1]]
        assert part.read_bytes() == chunks[0]
        assert not any(event["kind"] == "resume_state_reset"
                       for event in manager.observe(meta.transfer_id)["events"])
    finally:
        manager.close()


@pytest.mark.parametrize("status", ["publishing", "quarantined"])
def test_missing_publishing_or_quarantined_partial_is_not_reset(tmp_path, status):
    manager = FileTransferManager(CaptureTransport(), receive_dir=tmp_path)
    try:
        meta, _, _ = suspend(manager)
        manager.close()
        manager = FileTransferManager(CaptureTransport(), receive_dir=tmp_path)
        part = manager._resume_store.incoming_part(meta.transfer_id)
        part.unlink()
        manifest = manager._resume_store.incoming_manifest(meta.transfer_id)
        payload = manager._resume_store.read_json(manifest)
        payload["status"] = status
        manager._resume_store.atomic_json(manifest, payload)
        before = manifest.read_bytes()
        manager._handle_meta(meta)
        assert manager._outbox.wait_idle(1)
        assert not part.exists() and manifest.read_bytes() == before
    finally:
        manager.close()


def test_part_budget_cleanup_interrupt_keeps_proof_data_consistent(tmp_path, monkeypatch):
    store = ResumeStateStore(tmp_path / ".serialterminal-state")
    part = retained(store, 56, data=b"retained bytes")
    manifest = store.incoming_manifest(56)
    store.max_part_bytes = 0
    unlink = Path.unlink

    def fail_manifest(path, *args, **kwargs):
        if path == manifest:
            raise OSError(errno.EIO, "manifest removal interrupted")
        return unlink(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "unlink", fail_manifest)
        with pytest.raises(OSError, match="removal interrupted"):
            store.cleanup()
    assert manifest.is_file()
    assert part.read_bytes() == b"retained bytes"
    store.cleanup()
    assert not manifest.exists() and not part.exists()
