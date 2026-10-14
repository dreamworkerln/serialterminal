"""Короткие регрессии recursive FT1; подробная матрица передаётся Luna."""
import itertools
import random
import time

import pytest

from serialterminal.file_transfer import (
    BinarySendReceipt, DataMessage, FileTransferManager, MetaMessage, decode_message,
)


class Wire:
    payload_capacity = 243

    def __init__(self, *, holes=(), repeat=False, drop_service=False, fail_service=False, drop_service_depths=()):
        self.peer = None
        self.receiver = None
        self.holes = set(holes)
        self.repeat = repeat
        self.drop_service = drop_service
        self.drop_service_depths = set(drop_service_depths)
        self.fail_service = fail_service
        self.metadata = {}
        self.messages = []

    def set_receiver(self, receiver):
        self.receiver = receiver

    def send_binary(self, payload, *, cancel_event=None):
        from serialterminal.file_transfer import BinaryUserCancelled
        if cancel_event is not None and cancel_event.is_set():
            raise BinaryUserCancelled()
        message = decode_message(payload)
        self.messages.append(message)
        if isinstance(message, MetaMessage):
            self.metadata[message.transfer_id] = message
        drop = False
        if isinstance(message, DataMessage):
            meta = self.metadata[message.transfer_id]
            if meta.depth and self.fail_service:
                from serialterminal.file_transfer import BinaryUserError
                raise BinaryUserError("send_rejected", "injected service admission rejection")
            if meta.depth == 0 and message.chunk_index in self.holes:
                drop = True
                if not self.repeat:
                    self.holes.remove(message.chunk_index)
            elif meta.depth == 1 and self.drop_service and message.chunk_index == 0:
                drop = True
                self.drop_service = False
            elif meta.depth in self.drop_service_depths and message.chunk_index == 0:
                drop = True
                self.drop_service_depths.remove(meta.depth)
        if not drop and self.peer.receiver is not None:
            self.peer.receiver(bytes(payload))
            # Fake wire не имеет физического ToA; ограничиваем его очередью,
            # чтобы smoke не создавал невозможный мгновенный burst500 DATA.
            target = self.peer.receiver.__self__
            while target._rx_queue.qsize() > 8:
                if cancel_event is not None and cancel_event.is_set():
                    raise BinaryUserCancelled()
                time.sleep(.001)
        return BinarySendReceipt(tx_id=len(self.messages))


def run_transfer(tmp_path, *, holes=(), repeat=False, nested=False, nested_depth=0):
    source = tmp_path / 'payload.bin'
    source.write_bytes(random.Random(420).randbytes(227 * 500))
    left = Wire(holes=holes, repeat=repeat, drop_service_depths=range(1, nested_depth))
    right = Wire(drop_service=nested, drop_service_depths=range(1, nested_depth))
    left.peer, right.peer = right, left
    claims, releases = [], []
    ids = itertools.count(100)
    tx = FileTransferManager(left, receive_dir=tmp_path / 'a', id_factory=lambda: next(ids),
                             control_replay_interval_s=.1,
                             claim_transfer=lambda *args: claims.append(args),
                             release_transfer=lambda *args: releases.append(args))
    rx = FileTransferManager(right, receive_dir=tmp_path / 'b', id_factory=lambda: next(ids),
                             control_replay_interval_s=.1)
    try:
        tx.start_send(source)
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline:
            result = tx.display_snapshot()
            if result['state'] in {'completed', 'failed'}:
                break
            time.sleep(.01)
        assert result['state'] in {'completed', 'failed'}, result
        assert tx._outbox.wait_idle(1)
        assert len(claims) == len(releases) == 1
        return result, source.read_bytes(), list((tmp_path / 'b').glob('payload.bin')), left, right
    finally:
        tx.close()
        rx.close()


@pytest.mark.parametrize('nested', [False, True])
def test_full_missing_list_and_one_nested_service_repair(tmp_path, nested):
    result, original, files, left, right = run_transfer(tmp_path, holes=range(1, 160, 2), nested=nested)
    assert result['state'] == 'completed', result
    assert len(files) == 1 and files[0].read_bytes() == original
    depths = [m.depth for wire in (left, right) for m in wire.messages if isinstance(m, MetaMessage)]
    assert max(depths) == (2 if nested else 1)
    assert not list((tmp_path / 'b').glob('*.missing'))


def test_three_completed_no_progress_cycles_fail_root(tmp_path):
    result, _, files, _, right = run_transfer(tmp_path, holes=range(1, 160, 2), repeat=True)
    assert result['state'] == 'failed'
    assert result['failure']['details']['remote_code'] == 'repair_no_progress'
    assert not files
    lists = {m.transfer_id for m in right.messages if isinstance(m, MetaMessage) and m.depth == 1}
    assert len(lists) == 3
    assert list((tmp_path / 'b').glob('*.part'))


def test_root_percent_gate_fails_before_service_file(tmp_path):
    result, _, files, _, right = run_transfer(tmp_path, holes=range(160))
    assert result['state'] == 'failed'
    assert result['failure']['details']['remote_code'] == 'missing_percent_exceeded'
    assert not files
    assert not any(isinstance(m, MetaMessage) and m.depth for m in right.messages)


def test_shared_receive_dir_service_failure_cancels_children_and_keeps_root_partial(tmp_path):
    source = tmp_path / 'root.bin'
    source.write_bytes(random.Random(721).randbytes(227 * 20))
    left, right = Wire(holes={2, 4}), Wire(fail_service=True)
    left.peer, right.peer = right, left
    ids = itertools.count(2000)
    shared = tmp_path / 'received'
    tx = FileTransferManager(left, receive_dir=shared, id_factory=lambda: next(ids), control_replay_interval_s=.1)
    rx = FileTransferManager(right, receive_dir=shared, id_factory=lambda: next(ids), control_replay_interval_s=.1)
    try:
        started = tx.start_send(source)
        root_id = int(started['transfer_id'], 16)
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if tx._records[root_id].state == 'failed' and not any(f.parent_id for f in tx._recursive_frames.values()):
                break
            time.sleep(.01)
        assert tx._records[root_id].state == 'failed'
        assert not any(f.parent_id for f in tx._recursive_frames.values())
        assert rx._resume_store.incoming_part(root_id).is_file()
        assert rx._resume_store.load_incoming(root_id)[0]['status'] == 'suspended'
        assert not any('could not persist' in str(e) for r in tx._records.values() for e in r._events)
        assert tx._outbox.wait_idle(1)
        assert tx._incoming is None
        shown = tx.display_snapshot()
        assert shown['transfer_id'] == started['transfer_id'] and shown['state'] == 'failed'
        assert not (shared / 'root.bin').exists()
    finally:
        tx.close()
        rx.close()


@pytest.mark.parametrize('remote_code', [
    'recursion_depth_limit', 'repair_no_progress', 'missing_percent_exceeded',
])
def test_nested_remote_failure_preserves_root_reason(remote_code):
    from types import SimpleNamespace
    from serialterminal.file_transfer import core, recursive

    root_record = core._TransferRecord(9000, direction='TX', filename='root.bin', event_retention=16)
    child_record = core._TransferRecord(9001, direction='TX', filename='list.missing', event_retention=16)
    child_record.state = 'failed'
    root = recursive._Frame(root_record)
    child = recursive._Frame(child_record, parent_id=9000, depth=1)
    manager = SimpleNamespace(_recursive_root_id=9000, _recursive_frames={9000: root, 9001: child})
    failure = core.FileTransferError('remote_failed', 'nested remote rejection',
                                    phase='waiting_result', details={'remote_code': remote_code})

    recursive._abort_recursive(manager, failure, child_record.transfer_id)

    assert root_record.remote_result.code == remote_code
    assert root_record.remote_result.reason == 'nested remote rejection'
    assert root_record.remote_result.ok is False


@pytest.mark.parametrize("required_depth,expected_state,actual_depth", [(8, "completed", 8), (9, "failed", 8)])
def test_recursive_depth_boundary_and_service_percent_exemption(tmp_path, required_depth, expected_state, actual_depth):
    from recursive_evidence import service_requests

    result, original, files, left, right = run_transfer(
        tmp_path, holes=range(1, 160, 2), nested_depth=required_depth,
    )
    assert result["state"] == expected_state, result
    metadata = {m.transfer_id: m for wire in (left, right) for m in wire.messages if isinstance(m, MetaMessage)}
    assert max(meta.depth for meta in metadata.values()) == actual_depth
    # Проверяем реально переданные hash-verified LIST, а не только snapshots.
    # Маленькие LIST теряют свой единственный DATA (100%), но не ROOT gate.
    assert any(meta.depth > 1 and meta.wire_size <= meta.chunk_size for meta in metadata.values())
    if expected_state == "completed":
        assert len(files) == 1 and files[0].read_bytes() == original
        assert len({m.transfer_id for m in metadata.values() if m.depth}) >= 8
        root_id = int(result["transfer_id"], 16)
        assert len(service_requests(right.messages, root_id)) == 1
    else:
        assert not files
        assert result["failure"]["details"]["remote_code"] == "recursion_depth_limit"
        assert list((tmp_path / "b").glob("*.part"))
    assert not list((tmp_path / "a").glob("*.missing"))
    assert not list((tmp_path / "b").glob("*.missing"))


@pytest.mark.parametrize("missing_count,expected", [(150, "completed"), (151, "failed")])
def test_root_missing_percent_exact_boundary(tmp_path, missing_count, expected):
    result, original, files, _, right = run_transfer(tmp_path, holes=range(missing_count))
    assert result["state"] == expected, result
    if expected == "completed":
        assert len(files) == 1 and files[0].read_bytes() == original
        assert any(isinstance(m, MetaMessage) and m.depth == 1 for m in right.messages)
    else:
        assert result["failure"]["details"]["remote_code"] == "missing_percent_exceeded"
        assert not files
        assert not any(isinstance(m, MetaMessage) and m.depth for m in right.messages)


def test_any_missing_decrease_resets_counter_without_total_cycle_cap(tmp_path, monkeypatch):
    from test_file_transfer_failure_retention import CaptureTransport, fixture

    manager = FileTransferManager(CaptureTransport(), receive_dir=tmp_path)
    issued_lists = []
    monkeypatch.setattr(manager, "_start_list", lambda parent, ranges: issued_lists.append(tuple(ranges)))
    try:
        meta, chunks, end = fixture(manager, count=20)
        holes = [1, 3, 5, 7]
        for index, chunk in enumerate(chunks):
            if index not in holes:
                manager._handle_data(DataMessage(meta.transfer_id, index, chunk))
        expected = [(4, 0), (4, 1), (3, 0), (3, 1), (2, 0), (2, 1),
                    (2, 2), (1, 0), (1, 1), (1, 2), (1, 3)]
        previous = 4
        for count, no_progress in expected:
            if count < previous:
                recovered = holes.pop()
                manager._handle_data(DataMessage(meta.transfer_id, recovered, chunks[recovered]))
            manager._handle_end(end)
            progress = manager._records[meta.transfer_id].snapshot()["repair"]
            assert progress == {"missing_total": count, "no_progress": no_progress, "depth": 0}
            previous = count
        assert len(issued_lists) == 10
        assert manager._records[meta.transfer_id].failure["code"] == "repair_no_progress"
        assert manager._resume_store.incoming_part(meta.transfer_id).is_file()
        assert not (tmp_path / meta.filename).exists()
    finally:
        manager.close()
