"""Регрессии lifecycle/admission/replay findings REVIEW_001."""
from dataclasses import replace

import pytest

from serialterminal.file_transfer import (
    Compression, DataMessage, EndMessage, FileTransferError, FileTransferManager,
    MetaMessage, MissingMessage, MissingRange, ResultMessage,
)
from serialterminal.file_transfer import core, recursive
from test_file_transfer_failure_retention import CaptureTransport, fixture, wait_until


def test_valid_root_end_is_deferred_before_child_result_arrives(tmp_path):
    manager = FileTransferManager(CaptureTransport(), receive_dir=tmp_path)
    try:
        meta, chunks, end = fixture(manager)
        frame = manager._recursive_frames[meta.transfer_id]
        child = core._TransferRecord(801, direction="TX", filename="list", event_retention=16)
        manager._records[801] = child
        manager._recursive_frames[801] = recursive._Frame(child, parent_id=meta.transfer_id, depth=1)
        frame.child_id = frame.request_id = 801
        replay = replace(end, repair_id=801)
        for index, chunk in enumerate(chunks):
            manager._handle_data(DataMessage(meta.transfer_id, index, chunk))
        manager._handle_end(replace(replay, repair_id=800))
        assert frame.deferred_end is None
        manager._handle_end(replay)
        assert frame.deferred_end == replay
        assert child.remote_result is None
        manager._terminal_record_settled(child, "completed")
        assert wait_until(lambda: manager._records[meta.transfer_id].state == "completed")
        assert (tmp_path / meta.filename).read_bytes() == b"".join(chunks)
    finally:
        manager.close()


@pytest.mark.parametrize("collision", ["parent", "other_context"])
def test_child_identity_collision_preserves_existing_context(tmp_path, collision):
    transport = CaptureTransport()
    manager = FileTransferManager(transport, receive_dir=tmp_path)
    parent = manager._reserve_record(100, direction="TX", filename="root")
    parent.set_sizes(original_bytes=2270, wire_bytes=2270, chunks_total=10)
    root = recursive._Frame(parent, last_end=EndMessage(100, 10, b"x" * 32))
    manager._recursive_frames[100] = root
    manager._recursive_root_id = 100
    child_id = 100
    if collision == "other_context":
        child_id = 99
        manager._recursive_frames[99] = recursive._Frame(parent)
    before = dict(manager._recursive_frames)
    meta = MetaMessage(child_id, "list", 28, 28, Compression.NONE, 227, b"x" * 32, parent_transfer_id=100, depth=1)
    try:
        manager._handle_meta(meta)
        assert manager._outbox.wait_idle(1)
        assert manager._recursive_frames == before
        assert manager._records[100] is parent
        assert manager._active_id == 100
        assert root.child_id is None
        assert manager._incoming is None
        assert isinstance(transport.sent[-1], ResultMessage) and not transport.sent[-1].ok
    finally:
        manager.close()


@pytest.mark.parametrize("direction", ["TX", "RX"])
def test_rejected_root_meta_does_not_replace_live_frame(tmp_path, direction):
    manager = FileTransferManager(CaptureTransport(), receive_dir=tmp_path)
    try:
        if direction == "RX":
            meta, _, end = fixture(manager)
            frame = manager._recursive_frames[meta.transfer_id]
        else:
            record = manager._reserve_record(71, direction="TX", filename="retained.bin")
            meta = MetaMessage(71, "retained.bin", 681, 681, Compression.NONE, 227, b"x" * 32)
            end = EndMessage(71, 3, b"x" * 32)
            frame = recursive._Frame(record, meta=meta)
            manager._recursive_frames[71] = frame
            manager._recursive_root_id = 71
        frame.request_id = 900
        frame.previous_missing = 2
        frame.no_progress = 1
        frame.last_end = end
        frame.child_id = 901
        before = dict(frame.__dict__)
        manager._handle_meta(replace(meta, original_sha256=b"z" * 32))
        assert manager._recursive_frames[meta.transfer_id] is frame
        assert frame.__dict__ == before
        assert manager._active_id == meta.transfer_id
        frame.child_id = None
    finally:
        manager.close()


def test_valid_duplicate_meta_refreshes_activity_but_conflict_does_not(tmp_path):
    manager = FileTransferManager(CaptureTransport(), receive_dir=tmp_path)
    try:
        meta, _, _ = fixture(manager)
        incoming = manager._incoming_for(meta.transfer_id)
        incoming.last_activity_monotonic -= 60
        old = incoming.last_activity_monotonic
        manager._handle_meta(replace(meta, original_sha256=b"z" * 32))
        assert incoming.last_activity_monotonic == old
        manager._handle_meta(meta)
        assert incoming.last_activity_monotonic > old + 50
        assert manager._incoming_for(meta.transfer_id) is incoming
    finally:
        manager.close()


@pytest.mark.parametrize("activity_during_child", [False, True])
def test_parent_idle_clock_excludes_child_duration(tmp_path, monkeypatch, activity_during_child):
    manager = FileTransferManager(CaptureTransport(), receive_dir=tmp_path, incoming_idle_timeout_s=10)
    try:
        meta, _, _ = fixture(manager)
        incoming = manager._incoming_for(meta.transfer_id)
        root = manager._recursive_frames[meta.transfer_id]
        incoming.last_activity_monotonic = 95 if activity_during_child else 75
        root.child_started_monotonic = 80
        root.child_id = 801
        child = core._TransferRecord(801, direction="TX", filename="list", event_retention=16)
        manager._records[801] = child
        manager._recursive_frames[801] = recursive._Frame(child, parent_id=meta.transfer_id, depth=1)
        with monkeypatch.context() as clock:
            clock.setattr(recursive.time, "monotonic", lambda: 100)
            manager._terminal_record_settled(child, "completed")
            assert incoming.last_activity_monotonic == (100 if activity_during_child else 95)
            manager._expire_stale_incoming()
        assert manager._records[meta.transfer_id].state == "receiving"
        assert manager._incoming_for(meta.transfer_id) is incoming
    finally:
        manager.close()


@pytest.mark.parametrize("state", ["completed", "failed", "cancelled"])
def test_forty_sequential_root_settlements_leave_no_orphan_frames(tmp_path, state):
    manager = FileTransferManager(CaptureTransport(), receive_dir=tmp_path)
    try:
        for transfer_id in range(100, 140):
            record = manager._reserve_record(transfer_id, direction="TX", filename="root")
            manager._recursive_root_id = transfer_id
            manager._recursive_frames[transfer_id] = recursive._Frame(record)
            manager._terminal_record(record, state)
            assert not manager._recursive_frames
            assert manager._active_id is None
        assert len(manager._records) == manager.max_retained_terminal
        assert len(manager._terminal_order) == manager.max_retained_terminal
        assert manager.display_snapshot()["transfer_id"] == f"{139:016x}"
    finally:
        manager.close()


def test_forty_real_rx_publications_retire_frames_and_replay_completed_end(tmp_path):
    transport = CaptureTransport()
    manager = FileTransferManager(transport, receive_dir=tmp_path)
    try:
        for transfer_id in range(100, 140):
            meta, chunks, end = fixture(manager, transfer_id=transfer_id, count=1)
            manager._handle_data(DataMessage(transfer_id, 0, chunks[0]))
            manager._handle_end(end)
            assert manager._records[transfer_id].state == "completed"
            assert not manager._recursive_frames
        assert len(manager._records) == manager.max_retained_terminal
        assert len(list(tmp_path.glob("retained*.bin"))) == 40
        count = len(transport.sent)
        manager._handle_end(end)
        assert manager._outbox.wait_idle(1)
        assert any(isinstance(message, ResultMessage) and message.ok for message in transport.sent[count:])
        assert len(list(tmp_path.glob("retained*.bin"))) == 40
    finally:
        manager.close()


def test_live_root_replay_history_stays_one_entry_after_five_thousand_children(tmp_path):
    transport = CaptureTransport()
    manager = FileTransferManager(transport, receive_dir=tmp_path)
    root_record = manager._reserve_record(100, direction="TX", filename="root")
    root_record.set_sizes(original_bytes=2270, wire_bytes=2270, chunks_total=10)
    root = recursive._Frame(root_record, last_end=EndMessage(100, 10, b"x" * 32))
    manager._recursive_frames[100] = root
    manager._recursive_root_id = 100
    oldest = None
    previous_id = 0
    try:
        for child_id in range(1001, 11001, 2):
            meta = MetaMessage(child_id, "list", 28, 28, Compression.NONE, 227, b"x" * 32,
                               parent_transfer_id=100, depth=1, previous_repair_id=previous_id)
            oldest = oldest or meta
            record = core._TransferRecord(child_id, direction="RX", filename="list", event_retention=16)
            request = MissingMessage(100, (MissingRange(1, 1),), request_id=child_id)
            child = recursive._Frame(record, parent_id=100, depth=1, meta=meta, service_request=request)
            manager._records[child_id] = record
            manager._recursive_frames[child_id] = child
            root.child_id = child_id
            manager._terminal_record_settled(record, "completed")
            assert len(root.processed) == len(root.requests) == 1
            assert root.requests.popleft() == request
            root.last_end = replace(root.last_end, repair_id=child_id)
            previous_id = child_id
        assert set(manager._recursive_frames) == {100}
        assert len(manager._records) <= manager.max_retained_terminal + 1
        manager._handle_meta(meta)
        assert manager._outbox.wait_idle(1)
        assert not root.requests and root.child_id is None
        assert transport.sent[-1].ok
        manager._handle_meta(oldest)
        assert manager._outbox.wait_idle(1)
        assert not root.requests and root.child_id is None
        assert not transport.sent[-1].ok
        assert manager._recursive_frames[100] is root
    finally:
        manager.close()


@pytest.mark.parametrize("invalid", ["not-hex", "", -1, True])
def test_invalid_cancel_id_is_normalized_without_descendant_side_effects(tmp_path, invalid):
    manager = FileTransferManager(CaptureTransport(), receive_dir=tmp_path)
    try:
        record = manager._reserve_record(100, direction="TX", filename="root")
        frame = recursive._Frame(record)
        manager._recursive_frames[100] = frame
        manager._recursive_root_id = 100
        with pytest.raises(FileTransferError) as caught:
            manager.cancel(invalid)
        assert caught.value.code == "invalid_transfer_id"
        assert not record.cancel_event.is_set()
        assert manager._recursive_frames[100] is frame
    finally:
        manager.close()


def test_end_to_end_delayed_child_result_needs_no_root_end_replay(tmp_path):
    import itertools
    import random
    from test_ft1_recursive_missing import Wire
    from serialterminal.file_transfer import decode_message

    class DelayedResultWire(Wire):
        def __init__(self):
            super().__init__(holes={1, 3})
            self.pending_result = None
            self.saw_deferred_end = False
        def send_binary(self, payload, *, cancel_event=None):
            message = decode_message(payload)
            child_meta = self.peer.metadata.get(message.transfer_id)
            if isinstance(message, ResultMessage) and message.ok and child_meta is not None and child_meta.depth:
                self.messages.append(message)
                self.pending_result = bytes(payload)
                from serialterminal.file_transfer import BinarySendReceipt
                return BinarySendReceipt(len(self.messages))
            receipt = super().send_binary(payload, cancel_event=cancel_event)
            if isinstance(message, EndMessage) and message.repair_id and self.pending_result is not None:
                target = self.peer.receiver.__self__
                self.saw_deferred_end = wait_until(lambda: (
                    (frame := target._recursive_frames.get(message.transfer_id)) is not None
                    and frame.deferred_end == message
                ))
                target.feed_binary(self.pending_result)
                self.pending_result = None
            return receipt

    source = tmp_path / "root.bin"
    expected = random.Random(111).randbytes(227 * 40)
    source.write_bytes(expected)
    left, right = DelayedResultWire(), Wire()
    left.peer, right.peer = right, left
    ids = itertools.count(7000)
    tx = FileTransferManager(left, receive_dir=tmp_path / "tx", id_factory=lambda: next(ids),
                             max_control_replays=0, control_replay_interval_s=3)
    rx = FileTransferManager(right, receive_dir=tmp_path / "rx", id_factory=lambda: next(ids),
                             max_control_replays=0, control_replay_interval_s=3)
    try:
        started = tx.start_send(source)
        transfer_id = int(started["transfer_id"], 16)
        assert wait_until(lambda: tx._records[transfer_id].state == "completed")
        assert left.saw_deferred_end
        assert (tmp_path / "rx" / source.name).read_bytes() == expected
        ends = [message for message in left.messages if isinstance(message, EndMessage) and message.transfer_id == transfer_id]
        assert len(ends) == 2 and ends[0].repair_id == 0 and ends[1].repair_id != 0
    finally:
        tx.close()
        rx.close()


@pytest.mark.parametrize("depth", [0, 1])
def test_huge_missing_declaration_is_counted_and_planned_without_index_expansion(tmp_path, depth):
    from types import SimpleNamespace

    count = 0xFFFFFFFF
    record = core._TransferRecord(100, direction="RX", filename="virtual", event_retention=16)
    record.set_sizes(original_bytes=count, wire_bytes=count, chunks_total=count)
    meta = MetaMessage(100, "virtual", count, count, Compression.NONE, 1, b"x" * 32,
                       parent_transfer_id=99 if depth else 0, depth=depth)
    incoming = core._IncomingState(meta, record, tmp_path / "unused.part", {}, 0)
    frame = recursive._Frame(record, parent_id=99 if depth else 0, depth=depth, meta=meta, incoming=incoming)
    lists = []
    failures = []
    manager = SimpleNamespace(
        _recursive_frames={100: frame}, _incoming_for=lambda transfer_id: incoming,
        _checkpoint_incoming=lambda *args, **kwargs: None,
        _start_list=lambda parent, ranges: lists.append(ranges),
        _fail_incoming=lambda current, failure: failures.append(failure),
        max_missing_percent=30, max_no_progress_cycles=3, max_recursion_depth=8,
    )
    recursive._handle_end(manager, EndMessage(100, count, b"x" * 32))
    if depth == 0:
        assert not lists
        assert failures[0].code == "missing_percent_exceeded"
    else:
        assert not failures
        assert lists == [(MissingRange(0, count),)]
        assert record.snapshot()["repair"]["missing_total"] == count


def test_child_allocator_never_reuses_creator_ids_after_history_eviction(tmp_path, monkeypatch):
    tx = FileTransferManager(CaptureTransport(), receive_dir=tmp_path / "tx", id_factory=lambda: 100)
    rx = FileTransferManager(CaptureTransport(), receive_dir=tmp_path / "rx", id_factory=lambda: 100)
    monkeypatch.setattr(recursive.secrets, "randbits", lambda bits: 500)
    try:
        for manager, direction in ((tx, "TX"), (rx, "RX")):
            record = manager._reserve_record(100, direction=direction, filename="root")
            manager._recursive_frames[100] = recursive._Frame(record)
            manager._recursive_root_id = 100
        left_root = tx._recursive_frames[100]
        right_root = rx._recursive_frames[100]
        left = [tx._new_child_id(left_root) for _ in range(5000)]
        right = [rx._new_child_id(right_root) for _ in range(5000)]
        assert len(set(left)) == len(set(right)) == 5000
        assert not set(left).intersection(right)
        assert all(value % 2 == 0 for value in left)
        assert all(value % 2 == 1 for value in right)
        assert not left_root.processed and not right_root.processed
        left_root.next_child_id = 0x10000000000000000
        with pytest.raises(FileTransferError) as caught:
            tx._new_child_id(left_root)
        assert caught.value.code == "transfer_id_exhausted"
    finally:
        tx.close()
        rx.close()


def test_list_creation_failure_releases_lease_before_any_child_is_published(tmp_path, monkeypatch):
    manager = FileTransferManager(CaptureTransport(), receive_dir=tmp_path)
    try:
        meta, _, _ = fixture(manager)
        parent = manager._recursive_frames[meta.transfer_id]
        def fail(*args):
            raise OSError('list fsync failed')
        monkeypatch.setattr(recursive, 'write_missing_list', fail)
        with pytest.raises(OSError, match='fsync failed'):
            manager._start_list(parent, (MissingRange(1, 1),))
        assert parent.child_id is None
        assert set(manager._recursive_frames) == {meta.transfer_id}
        assert not list((manager._resume_store.root / 'recursive').glob('*.missing'))
        assert set(manager._resume_store._owned_leases) == {('incoming', meta.transfer_id)}
    finally:
        manager.close()
