import hashlib
import random
import struct

import pytest

from serialterminal.file_transfer import Compression, DataMessage, FileTransferManager, MetaMessage
from serialterminal.file_transfer.received import ReceivedRanges
from serialterminal.file_transfer.resume_store import ResumeStateStore
from serialterminal.file_transfer.recursive import read_missing_list
from serialterminal.file_transfer.protocol import FileProtocolError
from test_file_transfer_failure_retention import CaptureTransport, wait_until


def meta(count=10, chunk=1):
    return MetaMessage(901, 'ranges.bin', count * chunk, count * chunk, Compression.NONE, chunk, b'x' * 32)


def test_random_insertions_match_chunks_and_merge_without_history():
    received = ReceivedRanges(meta(1000))
    indices = list(range(1000))
    random.Random(913).shuffle(indices)
    reference = {}
    for index in indices:
        received[index] = 1
        reference[index] = 1
        assert len(received) == len(reference)
        assert received.byte_count == len(reference)
    assert received == reference
    assert received.ranges() == [[0, 1000]]
    assert list(received.missing(1000)) == []
    received[500] = 1
    assert len(received) == 1000


def test_uint32_sequential_history_restores_as_one_range_without_expansion():
    count = 0xFFFFFFFF
    received = ReceivedRanges.restore(meta(count), count, [[0, count]])
    assert len(received) == count and received.byte_count == count
    assert received.starts == [0] and received.ends == [count]
    assert received[count - 1] == 1
    assert received.ranges() == [[0, count]]
    assert not list(received.missing(count))


def test_range_budget_allows_merge_but_rejection_preserves_map():
    received = ReceivedRanges(meta(), maximum=2)
    received[0] = received[2] = 1
    with pytest.raises(ValueError, match='range limit'):
        received[4] = 1
    assert received.ranges() == [[0, 1], [2, 1]]
    received[1] = 1
    received[4] = 1
    assert received.ranges() == [[0, 3], [4, 1]]
    assert list(received.missing(10)) == [(3, 1), (5, 5)]


def test_final_short_chunk_contributes_exact_bytes():
    identity = MetaMessage(901, 'short', 8, 8, Compression.NONE, 3, b'x' * 32)
    received = ReceivedRanges.restore(identity, 3, [[0, 3]])
    assert received.byte_count == 8 and received[2] == 2


def test_fragmented_receiver_failure_keeps_durable_partial(tmp_path):
    manager = FileTransferManager(CaptureTransport(), receive_dir=tmp_path, max_received_ranges=2)
    identity = meta()
    try:
        manager._handle_meta(identity)
        manager._handle_data(DataMessage(901, 0, b'a'))
        manager._handle_data(DataMessage(901, 2, b'b'))
        before = manager._resume_store.incoming_part(901).read_bytes()
        manager._handle_data(DataMessage(901, 4, b'c'))
        assert wait_until(lambda: manager._records[901].state == 'failed')
        assert manager._records[901].failure['code'] == 'storage_failed'
        payload, _ = manager._resume_store.load_incoming(901)
        assert payload['received_ranges'] == [[0, 1], [2, 1]]
        assert manager._resume_store.incoming_part(901).read_bytes() == before
    finally:
        manager.close()


def test_manifest_read_and_write_limits_preserve_previous_document(tmp_path):
    store = ResumeStateStore(tmp_path / '.serialterminal-state', max_manifest_bytes=512)
    store.save_outgoing(1, {'status': 'active'})
    previous = store.outgoing_manifest(1).read_bytes()
    with pytest.raises(OSError, match='resource limit'):
        store.save_outgoing(1, {'padding': 'x' * 513})
    assert store.outgoing_manifest(1).read_bytes() == previous
    store.outgoing_manifest(2).write_bytes(b' ' * 513)
    assert store.read_json(store.outgoing_manifest(2)) is None


def test_list_count_rejected_before_ranges_are_allocated(tmp_path):
    path = tmp_path / 'list'
    path.write_bytes(struct.pack('>4sQII', b'MRF2', 1, 100, 100))
    with pytest.raises(FileProtocolError, match='count/total'):
        read_missing_list(path, 1, 100, 9, max_ranges=2)


def test_restore_rejects_excess_fragmentation_without_range_expansion(tmp_path):
    store = ResumeStateStore(tmp_path / '.serialterminal-state', max_received_ranges=1)
    assert store.received_from_ranges(meta(), 10, [[0, 1], [2, 1]]) is None
    assert store.received_from_ranges(meta(), 10, [[0, 10]]).ranges() == [[0, 10]]
