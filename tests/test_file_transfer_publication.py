import gzip
import hashlib
from pathlib import Path
import random

import pytest

from serialterminal.file_transfer import (
    BinaryUserError, Compression, DataMessage, EndMessage, FileTransferManager,
    MetaMessage, ResultMessage, ResumeMessage,
)
from serialterminal.file_transfer import core
from test_file_transfer_failure_retention import CaptureTransport, fixture


@pytest.mark.parametrize("compressed", [False, True])
def test_prepared_source_keeps_bytes_when_original_changes(tmp_path, compressed):
    payload = b"compressible" * 1000 if compressed else random.Random(6).randbytes(1000)
    source = tmp_path / "source.bin"
    source.write_bytes(payload)
    manager = FileTransferManager(CaptureTransport(), receive_dir=tmp_path / "rx")
    prepared = None
    try:
        record = manager._reserve_record(81, direction="TX", filename=source.name)
        prepared = manager._prepare_source(source, record)
        source.write_bytes(b"changed")
        wire = prepared.wire_path.read_bytes()
        actual = gzip.decompress(wire) if prepared.compression == Compression.GZIP else wire
        assert actual == payload
        assert prepared.original_sha256 == hashlib.sha256(payload).digest()
        assert prepared.wire_sha256 == hashlib.sha256(wire).digest()
        assert prepared.wire_path != source
    finally:
        manager.close()
        if prepared:
            prepared.wire_path.unlink(missing_ok=True)


def test_active_meta_never_sends_cursor_when_checkpoint_fails(tmp_path, monkeypatch):
    transport = CaptureTransport()
    manager = FileTransferManager(transport, receive_dir=tmp_path, resume_checkpoint_chunks=100, resume_checkpoint_s=100)
    try:
        meta, chunks, _ = fixture(manager)
        manager._handle_data(DataMessage(meta.transfer_id, 0, chunks[0]))
        transport.sent.clear()
        monkeypatch.setattr(manager, "_checkpoint_incoming", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("disk failed")))
        with pytest.raises(OSError):
            manager._handle_meta(meta)
        assert not any(isinstance(message, ResumeMessage) for message in transport.sent)
    finally:
        monkeypatch.undo()
        manager.close()


@pytest.mark.parametrize("boundary", ["file", "intent", "rename", "directory", "tombstone", "result"])
@pytest.mark.parametrize("compressed", [False, True])
def test_interrupted_publication_restarts_without_duplicate_or_early_ok(tmp_path, monkeypatch, boundary, compressed):
    transport = CaptureTransport()
    manager = FileTransferManager(transport, receive_dir=tmp_path)
    original = b"publish exactly once" * 40
    wire = gzip.compress(original, mtime=0) if compressed else original
    size = 227
    meta = MetaMessage(91, "published.bin", len(original), len(wire), Compression.GZIP if compressed else Compression.NONE, size, hashlib.sha256(original).digest())
    end = EndMessage(91, (len(wire) + size - 1) // size, hashlib.sha256(wire).digest())
    occupied = tmp_path / meta.filename
    occupied.write_bytes(b"preexisting file")
    manager._handle_meta(meta)
    for index, offset in enumerate(range(0, len(wire), size)):
        manager._handle_data(DataMessage(91, index, wire[offset:offset + size]))
    sent_before = len(transport.sent)
    expected = core._unique_destination(tmp_path, meta.filename)
    def fail(*args, **kwargs):
        raise OSError("injected publication interruption")
    if boundary == "file":
        fsync = core.os.fsync
        part = manager._resume_store.incoming_part(91)
        def fsync_or_fail(fd):
            filename = Path(core.os.readlink(f"/proc/self/fd/{fd}"))
            if filename == part or filename.suffix == ".verified":
                fail()
            return fsync(fd)
        monkeypatch.setattr(core.os, "fsync", fsync_or_fail)
    elif boundary == "intent":
        checkpoint = manager._checkpoint_incoming
        def checkpoint_or_fail(*args, **kwargs):
            if kwargs.get("status") == "publishing":
                fail()
            return checkpoint(*args, **kwargs)
        monkeypatch.setattr(manager, "_checkpoint_incoming", checkpoint_or_fail)
    elif boundary == "rename":
        link = core.os.link
        def link_or_fail(source, destination):
            if Path(destination) == expected:
                fail()
            return link(source, destination)
        monkeypatch.setattr(core.os, "link", link_or_fail)
    elif boundary == "directory":
        monkeypatch.setattr(manager, "_fsync_directory", fail)
    elif boundary == "tombstone":
        monkeypatch.setattr(manager._resume_store, "save_completed", fail)
    else:
        def on_send(message):
            if isinstance(message, ResultMessage) and message.ok:
                assert manager._resume_store.load_completed(91)["final_path"] == str(expected)
                assert expected.read_bytes() == original
                raise BinaryUserError("send_rejected", "RESULT unavailable")
        transport.on_send = on_send
    try:
        manager._handle_end(end)
        if boundary != "result":
            assert not any(isinstance(message, ResultMessage) and message.ok for message in transport.sent[sent_before:])
        else:
            assert manager._records[91].state == "completed"
        assert occupied.read_bytes() == b"preexisting file"
    finally:
        monkeypatch.undo()
        manager.close()
    transport2 = CaptureTransport()
    manager2 = FileTransferManager(transport2, receive_dir=tmp_path)
    try:
        manager2._handle_meta(meta)
        assert manager2._outbox.wait_idle(1)
        restored = manager2._incoming_for(91)
        if restored is not None:
            for index, offset in enumerate(range(0, len(wire), size)):
                if index not in restored.received:
                    manager2._handle_data(DataMessage(91, index, wire[offset:offset + size]))
            manager2._handle_end(end)
        assert any(isinstance(message, ResultMessage) and message.ok for message in transport2.sent)
        assert expected.read_bytes() == original
        assert len(list(tmp_path.glob("published*.bin"))) == 2
        assert manager2._resume_store.load_completed(91)["final_path"] == str(expected)
        manager2._handle_end(end)
        assert len(list(tmp_path.glob("published*.bin"))) == 2
    finally:
        manager2.close()


def _publish_concurrent_payload(root, transfer_id, payload, barrier, result_queue):
    manager = FileTransferManager(CaptureTransport(), receive_dir=Path(root))
    try:
        barrier.wait(5)
        meta = MetaMessage(transfer_id, "same.bin", len(payload), len(payload), Compression.NONE, 227, hashlib.sha256(payload).digest())
        end = EndMessage(transfer_id, 1, hashlib.sha256(payload).digest())
        manager._handle_meta(meta)
        manager._handle_data(DataMessage(transfer_id, 0, payload))
        publish = manager._publish_verified
        def synchronized(*args):
            barrier.wait(5)
            return publish(*args)
        manager._publish_verified = synchronized
        manager._handle_end(end)
        record = manager._records[transfer_id]
        value = record.snapshot()
        value["bytes"] = Path(record.final_path).read_bytes() if record.final_path else None
        result_queue.put(value)
    except Exception as exc:
        result_queue.put({"exception": str(exc)})
    finally:
        manager.close()


def test_two_processes_publish_same_basename_without_overwrite_or_dual_path(tmp_path):
    import multiprocessing

    context = multiprocessing.get_context("fork")
    barrier = context.Barrier(2)
    results = context.Queue()
    payloads = [b"first payload preserved", b"second payload preserved"]
    processes = [context.Process(target=_publish_concurrent_payload,
                                 args=(str(tmp_path), 500 + index, payload, barrier, results))
                 for index, payload in enumerate(payloads)]
    try:
        for process in processes:
            process.start()
        values = [results.get(timeout=8) for _ in processes]
        for process in processes:
            process.join(5)
            assert not process.is_alive() and process.exitcode == 0
        assert all(value["state"] == "completed" for value in values), values
        assert {value["bytes"] for value in values} == set(payloads)
        assert len({value["final_path"] for value in values}) == 2
        assert {Path(value["final_path"]).name for value in values} == {"same.bin", "same (1).bin"}
        assert not list(tmp_path.glob("*.part"))
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
            process.join(2)
        results.close()


def test_durable_publishing_intent_reserves_name_after_writer_stops(tmp_path, monkeypatch):
    first = FileTransferManager(CaptureTransport(), receive_dir=tmp_path)
    second = FileTransferManager(CaptureTransport(), receive_dir=tmp_path)
    original = b"original retained transfer"
    newcomer = b"independent new transfer"
    def receive(manager, transfer_id, payload):
        meta = MetaMessage(transfer_id, "same.bin", len(payload), len(payload), Compression.NONE, 227, hashlib.sha256(payload).digest())
        manager._handle_meta(meta)
        manager._handle_data(DataMessage(transfer_id, 0, payload))
        return meta, EndMessage(transfer_id, 1, hashlib.sha256(payload).digest())
    try:
        meta, end = receive(first, 501, original)
        link = core.os.link
        def fail_first(source, destination):
            if Path(destination) == tmp_path / "same.bin":
                raise OSError("stopped after intent before publication")
            return link(source, destination)
        with monkeypatch.context() as fault:
            fault.setattr(core.os, "link", fail_first)
            first._handle_end(end)
        assert first._resume_store.load_incoming(501)[0]["status"] == "publishing"
        _, end_new = receive(second, 502, newcomer)
        second._handle_end(end_new)
        assert second._records[502].state == "completed"
        assert (tmp_path / "same (1).bin").read_bytes() == newcomer
        first._handle_meta(meta)
        first._handle_end(end)
        assert first._records[501].state == "completed"
        assert (tmp_path / "same.bin").read_bytes() == original
        assert (tmp_path / "same (1).bin").read_bytes() == newcomer
    finally:
        first.close()
        second.close()


def test_completed_user_file_cannot_be_mistaken_for_internal_orphan_part(tmp_path):
    payload = b"verified user file with reserved-looking filename"
    filename = ".serialterminal-0000000000000900.part"
    manager = FileTransferManager(CaptureTransport(), receive_dir=tmp_path)
    meta = MetaMessage(901, filename, len(payload), len(payload), Compression.NONE, 227, hashlib.sha256(payload).digest())
    end = EndMessage(901, 1, hashlib.sha256(payload).digest())
    try:
        manager._handle_meta(meta)
        manager._handle_data(DataMessage(901, 0, payload))
        manager._handle_end(end)
        record = manager._records[901]
        assert record.state == "completed"
        final = Path(record.final_path)
        assert final.name == ".serialterminal-0000000000000900 (1).part"
        manager._resume_store.ttl_s = 0
        manager._resume_store.max_part_bytes = 0
        manager._resume_store.cleanup()
        assert not manager._resume_store.completed_manifest(901).exists()
        assert final.read_bytes() == payload
    finally:
        manager.close()
