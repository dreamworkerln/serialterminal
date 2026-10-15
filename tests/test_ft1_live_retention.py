import errno
import hashlib
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from serialterminal.file_transfer import Compression, DataMessage, EndMessage, FileTransferManager, MetaMessage
from serialterminal.file_transfer import resume_store
from serialterminal.file_transfer.resume_store import ResumeStateStore
from test_file_transfer_failure_retention import CaptureTransport


def identity(number, size=8, chunk=4):
    return MetaMessage(number, f'file-{number}.bin', size, size, Compression.NONE, chunk, b'x' * 32)


def retained(store, number, data=b'oldbytes'):
    store.claim('incoming', number)
    part = store.incoming_part(number)
    part.write_bytes(data)
    store.save_incoming(meta=identity(number, len(data)), received={}, status='suspended')
    store.release('incoming', number)
    return part


@pytest.mark.parametrize('kind,maximum', [('incoming', 32), ('outgoing', 32), ('completed', 64)])
def test_counts_bounded_without_reconstructing_store(tmp_path, kind, maximum):
    store = ResumeStateStore(tmp_path / '.serialterminal-state')
    for number in range(1, maximum + 9):
        if kind == 'incoming':
            retained(store, number)
        elif kind == 'outgoing':
            store.save_outgoing(number, {'status': 'active'})
        else:
            store.save_completed(meta=identity(number), end=EndMessage(number, 2, b'x' * 32), final_path=tmp_path / f'final-{number}')
    paths = list((store.root / kind).glob('*.json'))
    assert len(paths) == maximum
    assert not (store.root / kind / '0000000000000001.json').exists()
    if kind == 'incoming':
        assert len(list(tmp_path.glob('.serialterminal-*.part'))) == maximum


def test_ttl_enforced_on_next_save_of_another_kind(tmp_path, monkeypatch):
    store = ResumeStateStore(tmp_path / '.serialterminal-state', ttl_s=10)
    now = [100.0]
    monkeypatch.setattr(resume_store.time, 'time', lambda: now[0])
    part = retained(store, 1)
    store.save_outgoing(2, {'status': 'active'})
    now[0] = 111
    store.save_completed(meta=identity(3), end=EndMessage(3, 2, b'x' * 32), final_path=tmp_path / 'final')
    assert not part.exists() and not store.incoming_manifest(1).exists()
    assert not store.outgoing_manifest(2).exists()
    assert store.completed_manifest(3).exists()


def test_growth_evicts_oldest_inactive_parts_and_keeps_final_files(tmp_path):
    store = ResumeStateStore(tmp_path / '.serialterminal-state')
    oldest = retained(store, 1)
    newer = retained(store, 2)
    os.utime(oldest, (1, 1))
    final = tmp_path / 'downloaded.bin'
    final.write_bytes(b'user file')
    store.claim('incoming', 3)
    target = store.incoming_part(3)
    target.touch()
    store.max_part_bytes = 16
    try:
        store.write_part(3, 0, b'newbytes')
        assert not oldest.exists() and not store.incoming_manifest(1).exists()
        assert newer.read_bytes() == b'oldbytes'
        assert target.read_bytes() == b'newbytes'
        assert final.read_bytes() == b'user file'
        assert store._part_bytes() == 16
    finally:
        store.release_all()


@pytest.mark.parametrize('code', [errno.ENOSPC, errno.EDQUOT])
def test_failed_partial_write_reclaims_then_retries_same_offset(tmp_path, monkeypatch, code):
    store = ResumeStateStore(tmp_path / '.serialterminal-state')
    old = retained(store, 1)
    store.claim('incoming', 2)
    target = store.incoming_part(2)
    target.write_bytes(b'prefix')
    original = Path.open
    attempts = []
    class FailingFile:
        def __init__(self, file):
            self.file = file
        def __enter__(self):
            return self
        def __exit__(self, *args):
            self.file.close()
        def __getattr__(self, name):
            return getattr(self.file, name)
        def write(self, data):
            attempts.append(self.file.tell())
            self.file.write(data[:2])
            self.file.flush()
            raise OSError(code, 'injected full storage')
    def open_path(path, mode='r', *args, **kwargs):
        file = original(path, mode, *args, **kwargs)
        if path == target and mode == 'r+b' and not attempts:
            return FailingFile(file)
        return file
    monkeypatch.setattr(Path, 'open', open_path)
    try:
        store.write_part(2, 6, b'newbytes')
        assert attempts == [6]
        assert target.read_bytes() == b'prefixnewbytes'
        assert not old.exists() and not store.incoming_manifest(1).exists()
    finally:
        store.release_all()


def test_disk_free_pressure_reclaims_even_below_partial_budget(tmp_path, monkeypatch):
    store = ResumeStateStore(tmp_path / '.serialterminal-state')
    old = retained(store, 1)
    monkeypatch.setattr(resume_store.shutil, 'disk_usage', lambda path: SimpleNamespace(free=0 if old.exists() else 10000))
    results = []
    store.with_reclamation(lambda: results.append('written'), free_bytes=8)
    assert results == ['written'] and not old.exists()


def test_no_victim_failure_preserves_current_bytes_and_durable_proof(tmp_path):
    manager = FileTransferManager(CaptureTransport(), receive_dir=tmp_path)
    try:
        manager._handle_meta(identity(3, 12))
        manager._handle_data(DataMessage(3, 0, b'abcd'))
        manager._checkpoint_incoming(manager._incoming_for(3), force=True)
        manager._resume_store.max_part_bytes = 4
        manager._handle_data(DataMessage(3, 1, b'efgh'))
        record = manager._records[3]
        assert record.state == 'failed' and record.failure['code'] == 'storage_failed'
        assert manager._resume_store.incoming_part(3).read_bytes() == b'abcd'
        assert manager._resume_store.load_incoming(3)[0]['received_ranges'] == [[0, 1]]
    finally:
        manager.close()


def test_live_owner_of_other_store_is_skipped_during_growth(tmp_path):
    first = ResumeStateStore(tmp_path / '.serialterminal-state')
    second = ResumeStateStore(first.root)
    first.claim('incoming', 1)
    live = first.incoming_part(1)
    live.write_bytes(b'live')
    first.save_incoming(meta=identity(1, 4), received={}, status='receiving')
    old = retained(second, 2, b'old!')
    second.claim('incoming', 3)
    target = second.incoming_part(3)
    target.touch()
    second.max_part_bytes = 8
    try:
        second.write_part(3, 0, b'new!')
        assert live.read_bytes() == b'live' and target.read_bytes() == b'new!'
        assert not old.exists()
    finally:
        first.release_all()
        second.release_all()


def test_non_space_error_does_not_evict_or_retry(tmp_path):
    store = ResumeStateStore(tmp_path / '.serialterminal-state')
    old = retained(store, 1)
    attempts = []
    def fail():
        attempts.append(1)
        raise OSError(errno.EIO, 'io error')
    with pytest.raises(OSError) as error:
        store.with_reclamation(fail)
    assert error.value.errno == errno.EIO
    assert attempts == [1] and old.exists()


def test_live_count_limit_refuses_new_owner_without_deleting_leases(tmp_path, monkeypatch):
    store = ResumeStateStore(tmp_path / '.serialterminal-state')
    monkeypatch.setattr(resume_store, 'DEFAULT_MAX_INCOMING', 2)
    try:
        store.claim('incoming', 1)
        store.claim('incoming', 2)
        with pytest.raises(OSError) as error:
            store.claim('incoming', 3)
        assert error.value.errno == errno.ENOSPC
        assert set(store._owned_leases) == {('incoming', 1), ('incoming', 2)}
    finally:
        store.release_all()


def test_live_receiver_rolls_old_data_out_and_completes_exact_file(tmp_path):
    manager = FileTransferManager(CaptureTransport(), receive_dir=tmp_path)
    try:
        old = retained(manager._resume_store, 1)
        manager._resume_store.max_part_bytes = 12
        data = b'abcdefghijkl'
        digest = hashlib.sha256(data).digest()
        meta = MetaMessage(3, 'complete.bin', 12, 12, Compression.NONE, 4, digest)
        manager._handle_meta(meta)
        for index in range(3):
            manager._handle_data(DataMessage(3, index, data[index*4:index*4+4]))
        manager._handle_end(EndMessage(3, 3, digest))
        assert manager._records[3].state == 'completed'
        assert (tmp_path / 'complete.bin').read_bytes() == data
        assert not old.exists() and manager._resume_store.load_completed(3)
    finally:
        manager.close()


def test_failed_manifest_retry_keeps_last_document_and_only_retries_after_eviction(tmp_path, monkeypatch):
    store = ResumeStateStore(tmp_path / '.serialterminal-state')
    old = retained(store, 1)
    store.save_outgoing(3, {'status': 'active', 'proof': 1})
    previous = store.outgoing_manifest(3).read_bytes()
    attempts = []
    def fail(*args):
        attempts.append(1)
        raise OSError(errno.ENOSPC, 'full')
    monkeypatch.setattr(store, 'atomic_json', fail)
    with pytest.raises(OSError):
        store.save_outgoing(3, {'status': 'active', 'proof': 2})
    assert len(attempts) == 2 and not old.exists()
    assert store.outgoing_manifest(3).read_bytes() == previous


def test_cleanup_failure_does_not_advance_current_partial(tmp_path, monkeypatch):
    manager = FileTransferManager(CaptureTransport(), receive_dir=tmp_path)
    try:
        old = retained(manager._resume_store, 1)
        old_manifest = manager._resume_store.incoming_manifest(1)
        manager._handle_meta(identity(3, 12))
        manager._handle_data(DataMessage(3, 0, b'abcd'))
        manager._checkpoint_incoming(manager._incoming_for(3), force=True)
        manager._resume_store.max_part_bytes = 12
        original = Path.unlink
        def unlink(path, *args, **kwargs):
            if path == old_manifest:
                raise OSError(errno.EACCES, 'cleanup denied')
            return original(path, *args, **kwargs)
        monkeypatch.setattr(Path, 'unlink', unlink)
        manager._handle_data(DataMessage(3, 1, b'efgh'))
        assert manager._records[3].failure['code'] == 'storage_failed'
        assert manager._resume_store.incoming_part(3).read_bytes() == b'abcd'
        assert manager._resume_store.load_incoming(3)[0]['received_ranges'] == [[0, 1]]
        assert old.exists() and old_manifest.exists()
    finally:
        manager.close()


def test_concurrent_growth_reserves_shared_budget_before_write(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    stores = [ResumeStateStore(tmp_path / '.serialterminal-state', max_part_bytes=8) for _ in range(2)]
    for number, store in enumerate(stores, 1):
        store.claim('incoming', number)
        store.incoming_part(number).touch()
    def write(number):
        try:
            stores[number-1].write_part(number, 0, b'abcdefgh')
            return 'written'
        except OSError as error:
            assert error.errno == errno.ENOSPC
            return 'full'
    try:
        with ThreadPoolExecutor(2) as workers:
            results = list(workers.map(write, [1, 2]))
        assert sorted(results) == ['full', 'written']
        assert sum(stores[0].incoming_part(i).stat().st_size for i in [1, 2]) == 8
    finally:
        for store in stores:
            store.release_all()


def test_growth_cannot_evict_live_partial_of_other_process(tmp_path):
    import multiprocessing
    from test_ft1_durable_ownership import _owned_partial_process
    context = multiprocessing.get_context('fork')
    parent, child = context.Pipe()
    process = context.Process(target=_owned_partial_process, args=(str(tmp_path / '.serialterminal-state'), child))
    store = None
    try:
        process.start()
        assert parent.poll(3) and parent.recv() == 'owned'
        store = ResumeStateStore(tmp_path / '.serialterminal-state')
        live = store.incoming_part(701)
        old = retained(store, 2, b'old!')
        store.claim('incoming', 3)
        store.incoming_part(3).touch()
        store.max_part_bytes = len(live.read_bytes()) + 4
        store.write_part(3, 0, b'new!')
        assert live.read_bytes() == b'process-owned part'
        assert not old.exists() and process.is_alive()
    finally:
        if store is not None:
            store.release_all()
        if process.is_alive():
            process.terminate()
        process.join(3)
        parent.close()
        child.close()


def test_rollback_lease_release_preserves_untrusted_manifest_for_explicit_rejection(tmp_path):
    store = ResumeStateStore(tmp_path / '.serialterminal-state')
    manifest = store.incoming_manifest(9)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text('{broken-json')
    part = store.incoming_part(9)
    part.write_bytes(b'previous partial')
    store.claim('incoming', 9)
    store.release('incoming', 9)
    assert manifest.read_text() == '{broken-json'
    assert part.read_bytes() == b'previous partial'
