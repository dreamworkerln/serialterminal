from dataclasses import replace

import pytest

from serialterminal.file_transfer import Compression, EndMessage, FileTransferManager, MetaMessage, ResultMessage, ResumeMessage, encode_message
from serialterminal.file_transfer import core
from serialterminal.file_transfer.protocol import FileProtocolError, checked_chunk_count, decode_message
from test_file_transfer_failure_retention import CaptureTransport, fixture, wait_until


@pytest.mark.parametrize('chunk', [1, 227, 65535])
def test_uint32_boundary_and_rounding_are_exact(chunk):
    maximum = 0xFFFFFFFF
    assert checked_chunk_count((maximum - 1) * chunk + 1, chunk) == maximum
    assert checked_chunk_count(maximum * chunk, chunk) == maximum
    with pytest.raises(FileProtocolError, match='uint32'):
        checked_chunk_count(maximum * chunk + 1, chunk)
    assert checked_chunk_count(0, chunk) == 0
    assert checked_chunk_count(chunk + 1, chunk) == 2


@pytest.mark.parametrize('count', [0x100000000, 0x100000001, 0xFFFFFFFFFFFFFFFF])
def test_raw_invalid_meta_rejected_before_any_resource_admission(tmp_path, count):
    transport = CaptureTransport()
    claimed = []
    manager = FileTransferManager(transport, receive_dir=tmp_path, claim_transfer=lambda *args: claimed.append(args))
    try:
        valid = MetaMessage(909, 'virtual.bin', count, 1, Compression.NONE, 1, b'x' * 32)
        raw = bytearray(encode_message(valid, 243))
        raw[20:28] = count.to_bytes(8, 'big')
        manager.feed_binary(bytes(raw))
        assert wait_until(lambda: any(isinstance(m, ResultMessage) for m in transport.sent))
        result = next(m for m in transport.sent if isinstance(m, ResultMessage))
        assert result.code == 'invalid_metadata' and not result.ok
        assert not claimed and not manager._records and not manager._recursive_frames
        assert manager._active_id is None and manager._incoming is None
        assert not manager._resume_store._owned_leases
        assert not list(tmp_path.iterdir())
        with pytest.raises(FileProtocolError, match='uint32'):
            encode_message(replace(valid, wire_size=count), 243)
    finally:
        manager.close()


def test_largest_representable_meta_and_last_data_index(tmp_path):
    manager = FileTransferManager(CaptureTransport(), receive_dir=tmp_path)
    count = 0xFFFFFFFF
    meta = MetaMessage(909, 'virtual.bin', count, count, Compression.NONE, 1, b'x' * 32)
    try:
        manager._handle_meta(meta)
        incoming = manager._incoming_for(909)
        assert incoming.record.chunks_total == count
        assert manager._expected_chunk_length(incoming, count - 1) == 1
        with pytest.raises(core.FileTransferError):
            manager._expected_chunk_length(incoming, count)
        end = EndMessage(909, count, b'x' * 32)
        resume = ResumeMessage(909, count)
        assert decode_message(encode_message(end, 243)) == end
        assert decode_message(encode_message(resume, 243)) == resume
        assert incoming.wire_path.stat().st_size == 0
    finally:
        manager.close()


def test_invalid_meta_does_not_change_existing_root(tmp_path):
    manager = FileTransferManager(CaptureTransport(), receive_dir=tmp_path)
    try:
        meta, _, _ = fixture(manager)
        frame = manager._recursive_frames[meta.transfer_id]
        incoming = manager._incoming_for(meta.transfer_id)
        before = manager._records[meta.transfer_id].snapshot()
        manager._handle_meta(replace(meta, wire_size=0x100000000, chunk_size=1))
        assert manager._recursive_frames[meta.transfer_id] is frame
        assert manager._incoming_for(meta.transfer_id) is incoming
        after = manager._records[meta.transfer_id].snapshot()
        # Живое время растёт, отклонённая META не меняет остальные поля ROOT.
        assert after.pop("elapsed") >= before.pop("elapsed")
        assert after == before
    finally:
        manager.close()


def test_sender_checks_prepared_wire_before_journal_or_meta(tmp_path, monkeypatch):
    transport = CaptureTransport()
    manager = FileTransferManager(transport, receive_dir=tmp_path, id_factory=lambda: 909)
    source = tmp_path / 'source'
    source.write_bytes(b'x')
    synthetic = tmp_path / 'prepared'
    synthetic.write_bytes(b'x')
    prepared = core._PreparedSource(source, synthetic, True, source.name, 1, 227 * 0x100000000, Compression.NONE, b'x'*32, b'x'*32)
    monkeypatch.setattr(manager, '_prepare_source', lambda *args: prepared)
    try:
        manager.start_send(source)
        assert wait_until(lambda: manager._records[909].state == 'failed')
        manager.join_all(1)
        assert manager._records[909].failure['code'] == 'invalid_metadata'
        assert not transport.sent and not manager._resume_store.outgoing_manifest(909).exists()
        assert manager._active_id is None and not manager._resume_store._owned_leases
        assert not synthetic.exists() and source.read_bytes() == b'x'
    finally:
        manager.close()
