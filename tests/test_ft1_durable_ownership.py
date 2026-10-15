"""Active-owned durable state не удаляется другим manager/process."""
import hashlib
from pathlib import Path
import threading

import pytest

from serialterminal.file_transfer import Compression, DataMessage, FileTransferManager, MetaMessage, encode_message
from serialterminal.file_transfer.resume_store import ResumeStateStore
from test_file_transfer_failure_retention import CaptureTransport, wait_until


def test_second_manager_cleanup_preserves_live_pre_manifest_part(tmp_path):
    entered = threading.Event()
    release = threading.Event()
    def claim(*args):
        entered.set()
        assert release.wait(2)
    first = FileTransferManager(CaptureTransport(), receive_dir=tmp_path, claim_transfer=claim)
    second = None
    payload = b"already retained bytes"
    meta = MetaMessage(601, "owned.bin", len(payload), len(payload), Compression.NONE, 227, hashlib.sha256(payload).digest())
    try:
        first.feed_binary(encode_message(meta, 243))
        assert entered.wait(1)
        part = first._resume_store.incoming_part(601)
        assert part.is_file()
        assert not first._resume_store.incoming_manifest(601).exists()
        second = FileTransferManager(CaptureTransport(), receive_dir=tmp_path)
        second._resume_store.ttl_s = 0
        second._resume_store.max_part_bytes = 0
        second._resume_store.cleanup()
        assert part.is_file()
        release.set()
        assert wait_until(lambda: first._incoming_for(601) is not None)
        first._handle_data(DataMessage(601, 0, payload))
        first._checkpoint_incoming(first._incoming_for(601), force=True)
        second._resume_store.cleanup()
        assert part.read_bytes() == payload
        assert first._resume_store.incoming_manifest(601).is_file()
        assert first._records[601].state == "receiving"
        first.close()
        second._resume_store.cleanup()
        assert not part.exists()
    finally:
        release.set()
        first.close()
        if second is not None:
            second.close()


def _owned_partial_process(root, signal):
    store = ResumeStateStore(Path(root))
    store.claim("incoming", 701)
    payload = b"process-owned part"
    store.incoming_part(701).write_bytes(payload)
    meta = MetaMessage(701, "owned.bin", len(payload), len(payload), Compression.NONE, 227, hashlib.sha256(payload).digest())
    store.save_incoming(meta=meta, received={0: len(payload)}, status="receiving")
    manifest = store.read_json(store.incoming_manifest(701))
    store.atomic_json(store.incoming_manifest(701), {**manifest, "updated": 0})
    signal.send("owned")
    signal.recv()
    store.release_all()


def test_process_lease_protects_expired_over_budget_state_and_crash_releases_it(tmp_path):
    import multiprocessing

    context = multiprocessing.get_context("fork")
    parent, child = context.Pipe()
    root = tmp_path / ".serialterminal-state"
    process = context.Process(target=_owned_partial_process, args=(str(root), child))
    try:
        process.start()
        assert parent.poll(3) and parent.recv() == "owned"
        store = ResumeStateStore(root, ttl_s=.001, max_part_bytes=0)
        part = store.incoming_part(701)
        assert part.read_bytes() == b"process-owned part"
        assert store.incoming_manifest(701).is_file()
        store.cleanup()
        assert part.is_file()
        process.terminate()
        process.join(3)
        assert not process.is_alive()
        store.cleanup()
        assert not part.exists()
        assert not store.incoming_manifest(701).exists()
    finally:
        if process.is_alive():
            process.terminate()
        process.join(2)
        parent.close()
        child.close()


def test_adapter_close_failure_still_releases_storage_lease_after_workers_stop(tmp_path):
    transport = CaptureTransport()
    def fail():
        raise OSError("adapter close failed")
    transport.close = fail
    manager = FileTransferManager(transport, receive_dir=tmp_path)
    manager._reserve_record(801, direction="TX", filename="source")
    store = ResumeStateStore(tmp_path / ".serialterminal-state")
    try:
        with pytest.raises(OSError):
            store.claim("outgoing", 801)
        with pytest.raises(OSError, match="adapter close failed"):
            manager.close()
        assert not manager._rx_thread.is_alive()
        assert not manager._outbox.worker.is_alive()
        assert store.claim("outgoing", 801)
        store.release_all()
    finally:
        store.release_all()
        del transport.close
        manager.close()
