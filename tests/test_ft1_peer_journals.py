import errno
import random
from types import SimpleNamespace

import pytest

from serialterminal.file_transfer import FileTransferManager, MetaMessage, ResultMessage, encode_message
from serialterminal.file_transfer import core
from serialterminal.file_transfer.resume_store import ResumeStateStore
from test_file_transfer_failure_retention import CaptureTransport, wait_until


def failed_sender(root, source, peer_key=None, number=101):
    transport = CaptureTransport()
    manager = FileTransferManager(transport, receive_dir=root, peer_key=peer_key, id_factory=lambda: number,
                                  resume_handshake_timeout_s=.02, control_replay_interval_s=1.0, max_control_replays=0)
    transport.on_send = lambda message: manager.feed_binary(encode_message(ResultMessage(message.transfer_id, False, 'storage_failed', 'retain for retry'), 243)) if isinstance(message, MetaMessage) else None
    manager.start_send(source)
    assert wait_until(lambda: manager._records[number].state == 'failed')
    manager.join_all(1)
    return manager, transport


def source_file(tmp_path):
    source = tmp_path / 'source.bin'
    source.write_bytes(random.Random(510).randbytes(100))
    return source


@pytest.mark.parametrize('action', ['complete', 'cancel', 'failure', 'close'])
def test_two_peers_same_source_and_id_never_change_each_others_journal(tmp_path, action):
    source = source_file(tmp_path)
    first, _ = failed_sender(tmp_path / 'shared', source, 'serial:node-A')
    second, transport = failed_sender(tmp_path / 'shared', source, 'ble-address:node-B')
    path = first._resume_store.outgoing_manifest(101)
    other = second._resume_store.outgoing_manifest(101)
    previous = path.read_bytes()
    try:
        assert path != other and path.is_file() and other.is_file()
        assert first._sender_resume_candidate(source)['parsed_transfer_id'] == 101
        assert second._sender_resume_candidate(source)['parsed_transfer_id'] == 101
        if action == 'complete':
            transport.on_send = lambda m: second.feed_binary(encode_message(ResultMessage(m.transfer_id, True, 'ok', ''), 243)) if isinstance(m, MetaMessage) else None
        elif action in {'cancel', 'close'}:
            transport.on_send = lambda m: None
        started = second.start_send(source)
        assert started['resumed'] and started['transfer_id'] == '0000000000000065'
        if action == 'cancel':
            second.cancel(101)
        elif action == 'close':
            second.close()
        assert wait_until(lambda: second._records[101].state in core._TERMINAL_STATES)
        second.join_all(1)
        assert path.read_bytes() == previous and first._records[101].state == 'failed'
        if action in {'complete', 'cancel'}:
            assert not other.exists()
        else:
            assert other.exists()
    finally:
        first.close()
        second.close()


def test_explicit_peer_resumes_same_id_after_restart(tmp_path):
    source = source_file(tmp_path)
    first, _ = failed_sender(tmp_path / 'shared', source, 'serial:node-A')
    first.close()
    transport = CaptureTransport()
    second = FileTransferManager(transport, receive_dir=tmp_path / 'shared', peer_key='serial:node-A', id_factory=lambda: 202)
    transport.on_send = lambda m: second.feed_binary(encode_message(ResultMessage(m.transfer_id, True, 'ok', ''), 243)) if isinstance(m, MetaMessage) else None
    try:
        started = second.start_send(source)
        assert started['resumed'] and started['transfer_id'] == '0000000000000065'
        assert wait_until(lambda: second._records[101].state == 'completed')
        assert not second._resume_store.outgoing_manifest(101).exists()
    finally:
        second.close()


def test_anonymous_managers_do_not_attribute_state_across_restart(tmp_path):
    source = source_file(tmp_path)
    first, _ = failed_sender(tmp_path / 'shared', source)
    first.close()
    second = FileTransferManager(CaptureTransport(), receive_dir=tmp_path / 'shared')
    try:
        assert second.peer_key != first.peer_key
        assert second._sender_resume_candidate(source) is None
        assert first._resume_store.outgoing_manifest(101).exists()
    finally:
        second.close()


def test_old_unbound_and_wrong_binding_documents_are_not_candidates_or_mutable(tmp_path):
    source = source_file(tmp_path)
    manager, _ = failed_sender(tmp_path / 'shared', source, 'serial:node-A')
    store = manager._resume_store
    path = store.outgoing_manifest(101)
    payload = store.read_json(path)
    try:
        unbound = dict(payload)
        unbound.pop('peer_key')
        store.atomic_json(store.outgoing_dir / '0000000000000065.json', unbound)
        store.delete_outgoing(101)
        assert manager._sender_resume_candidate(source) is None
        store.atomic_json(path, {**payload, 'peer_key': 'another-peer'})
        before = path.read_bytes()
        assert manager._sender_resume_candidate(source) is None
        with pytest.raises(OSError) as error:
            store.save_outgoing(101, payload)
        assert error.value.errno == errno.EACCES
        with pytest.raises(OSError):
            store.delete_outgoing(101)
        assert path.read_bytes() == before
    finally:
        manager.close()


def test_shared_cleanup_uses_each_outgoing_namespace_lease(tmp_path):
    first = ResumeStateStore(tmp_path / '.serialterminal-state', peer_key='serial:node-A')
    second = ResumeStateStore(first.root, peer_key='ble-address:node-B', ttl_s=0)
    try:
        for store in [first, second]:
            store.claim('outgoing', 101)
            store.save_outgoing(101, {'status': 'active'})
        second.cleanup()
        assert first.outgoing_manifest(101).exists() and second.outgoing_manifest(101).exists()
        first.release_all()
        second.cleanup()
        assert not first.outgoing_manifest(101).exists()
        assert second.outgoing_manifest(101).exists()
    finally:
        first.release_all()
        second.release_all()


def test_same_peer_concurrent_owner_is_rejected_until_release(tmp_path):
    first = FileTransferManager(CaptureTransport(), receive_dir=tmp_path, peer_key='serial:node-A')
    second = FileTransferManager(CaptureTransport(), receive_dir=tmp_path, peer_key='serial:node-A')
    try:
        record = first._reserve_record(101, direction='TX', filename='source')
        with pytest.raises(core.FileTransferError) as error:
            second._reserve_record(101, direction='TX', filename='source')
        assert error.value.code == 'file_transfer_busy'
        assert second._active_id is None and not second._records
        first._terminal_record(record, 'failed', failure=core.FileTransferError('local_shutdown', 'retain'))
        second._reserve_record(101, direction='TX', filename='source')
    finally:
        first.close()
        second.close()


def _bound_process(root, signal):
    store = ResumeStateStore(root, peer_key='serial:node-A')
    store.claim('outgoing', 101)
    store.save_outgoing(101, {'status': 'active'})
    signal.send(str(store.outgoing_manifest(101)))
    signal.recv()


def test_processes_can_own_same_id_for_different_peers(tmp_path):
    import multiprocessing
    from pathlib import Path
    context = multiprocessing.get_context('fork')
    parent, child = context.Pipe()
    process = context.Process(target=_bound_process, args=(tmp_path / '.serialterminal-state', child))
    store = None
    try:
        process.start()
        assert parent.poll(3)
        other = Path(parent.recv())
        previous = other.read_bytes()
        store = ResumeStateStore(tmp_path / '.serialterminal-state', peer_key='ble-address:node-B', ttl_s=0)
        store.claim('outgoing', 101)
        store.save_outgoing(101, {'status': 'active'})
        store.delete_outgoing(101)
        store.cleanup()
        assert other.read_bytes() == previous and process.is_alive()
    finally:
        if store is not None:
            store.release_all()
        if process.is_alive():
            process.terminate()
        process.join(3)
        parent.close()
        child.close()


def test_cancel_binding_failure_is_explicit_and_retains_ownership(tmp_path):
    source = source_file(tmp_path)
    manager, transport = failed_sender(tmp_path / 'shared', source, 'serial:node-A')
    transport.on_send = lambda message: None
    try:
        manager.start_send(source)
        assert wait_until(lambda: manager._records[101].state == 'waiting_result')
        path = manager._resume_store.outgoing_manifest(101)
        payload = manager._resume_store.read_json(path)
        manager._resume_store.atomic_json(path, {**payload, 'peer_key': 'another-peer'})
        manager.cancel(101)
        manager.join_all(1)
        assert manager._records[101].failure['code'] == 'local_ownership_unsettled'
        assert manager._active_id == 101 and path.exists()
    finally:
        manager.close()


def test_frontends_pass_selected_device_key_to_file_manager(tmp_path):
    from serialterminal.agent import SessionManager
    from test_agent import FakeSelectorFactory
    factory = FakeSelectorFactory()
    manager = SessionManager(selector_factory=factory, receive_dir=tmp_path)
    manager.discover()
    try:
        opened = manager.open('ble:a', profile='chatter', wait_connected_ms=0)
        assert manager._file_managers[opened['session']].peer_key == 'ble:a'
    finally:
        manager.close_all()

    from serialterminal.tui_core import TerminalTui
    terminal = TerminalTui.__new__(TerminalTui)
    terminal.session = SimpleNamespace(
        wait_tx_outcome=lambda *args, **kwargs: None, cancel_tx=lambda *args: None,
        connection_generation=lambda: 1, record_timing=lambda *args, **kwargs: None,
        _current_transport=lambda: SimpleNamespace(device_key='serial:node-A'),
    )
    terminal.receive_dir = tmp_path
    terminal._claim_file_transfer = lambda *args: None
    terminal._release_file_transfer = lambda *args: None
    terminal._log_file_transfer_event = lambda *args, **kwargs: None
    profile = SimpleNamespace(make_binary_user_transport=lambda *args, **kwargs: CaptureTransport())
    terminal._configure_file_transfer(profile)
    try:
        assert terminal._file_transfer.peer_key == 'serial:node-A'
    finally:
        terminal._file_transfer.close()


def test_retained_outgoing_count_is_global_across_peer_namespaces(tmp_path):
    first = ResumeStateStore(tmp_path / '.serialterminal-state', peer_key='peer-A')
    second = ResumeStateStore(first.root, peer_key='peer-B')
    for store in [first, second]:
        for number in range(1, 21):
            store.save_outgoing(number, {'status': 'active'})
    assert len(list(first.outgoing_dir.glob('*.json'))) == 32
    assert all(second.outgoing_manifest(number).exists() for number in range(1, 21))


def test_live_outgoing_count_includes_other_namespaces(tmp_path, monkeypatch):
    from serialterminal.file_transfer import resume_store
    monkeypatch.setattr(resume_store, 'DEFAULT_MAX_OUTGOING', 2)
    stores = [ResumeStateStore(tmp_path / '.serialterminal-state', peer_key=f'peer-{number}') for number in range(3)]
    try:
        stores[0].claim('outgoing', 101)
        stores[1].claim('outgoing', 101)
        with pytest.raises(OSError) as error:
            stores[2].claim('outgoing', 101)
        assert error.value.errno == errno.ENOSPC
    finally:
        for store in stores:
            store.release_all()


@pytest.mark.parametrize('key', ['', True, 123])
def test_invalid_explicit_peer_key_does_not_start_manager(tmp_path, key):
    with pytest.raises(ValueError, match='peer_key'):
        FileTransferManager(CaptureTransport(), receive_dir=tmp_path, peer_key=key)
    assert not list(tmp_path.iterdir())
