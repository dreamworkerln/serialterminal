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
        replace = core.os.replace
        def replace_or_fail(source, destination):
            if Path(destination) == expected:
                fail()
            return replace(source, destination)
        monkeypatch.setattr(core.os, "replace", replace_or_fail)
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
