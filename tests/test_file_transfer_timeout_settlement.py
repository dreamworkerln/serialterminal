from contextlib import contextmanager
from dataclasses import replace
import threading

import pytest

from serialterminal.file_transfer import (
    BinaryUserError, DataMessage, FileTransferError, FileTransferManager,
    MetaMessage, ResultMessage, ResumeMessage, encode_message,
)
from test_file_transfer_failure_retention import CaptureTransport, fixture, wait_until


@contextmanager
def timed_out_receiver(tmp_path, monkeypatch, boundary, *, failure=False):
    transport = CaptureTransport()
    claims = []
    manager = FileTransferManager(
        transport, receive_dir=tmp_path / "rx", peer_key="fixture-peer",
        incoming_idle_timeout_s=60,
        claim_transfer=lambda *args: claims.append(args),
    )
    entered = threading.Event()
    proceed = threading.Event()

    def barrier():
        entered.set()
        assert proceed.wait(5), "settlement gate was not released"

    try:
        meta, chunks, end = fixture(manager, transfer_id=0x5151, count=4)
        manager._handle_data(DataMessage(meta.transfer_id, 0, chunks[0]))
        if boundary == "drain":
            def drain(timeout):
                barrier()
                if failure:
                    raise BinaryUserError("local_tx_drain_timeout", "write still active")
                return {}
            monkeypatch.setattr(transport, "drain_binary", drain, raising=False)
        elif boundary == "release":
            release = manager._release

            def blocked_release(*args):
                barrier()
                if failure:
                    raise OSError("release failed")
                release(*args)
            monkeypatch.setattr(manager, "_release", blocked_release)
        else:
            abort = manager._abort_recursive

            def blocked_abort(*args):
                barrier()
                abort(*args)
            monkeypatch.setattr(manager, "_abort_recursive", blocked_abort)

        transport.sent.clear()
        manager._incoming.last_activity_monotonic -= 120
        assert entered.wait(2), "receiver did not start timeout settlement"
        yield manager, transport, meta, chunks, end, proceed, claims
    finally:
        proceed.set()
        manager.close()


def flush_rx(manager, monkeypatch):
    processed = threading.Event()
    handle_data = manager._handle_data

    def marker(message):
        if message.transfer_id == 0xFFFF:
            processed.set()
        else:
            handle_data(message)

    monkeypatch.setattr(manager, "_handle_data", marker)
    manager.feed_binary(encode_message(DataMessage(0xFFFF, 0, b"marker"), 243))
    assert processed.wait(2), "RX blocked behind settlement"


@pytest.mark.parametrize("boundary", ["drain", "release", "context"])
def test_matching_meta_during_timeout_settlement_preserves_sender_identity(
    tmp_path, monkeypatch, boundary,
):
    with timed_out_receiver(tmp_path, monkeypatch, boundary) as setup:
        rx, transport, meta, chunks, _, proceed, claims = setup
        source = tmp_path / meta.filename
        source.write_bytes(b"".join(chunks))
        tx_transport = CaptureTransport()
        tx = FileTransferManager(
            tx_transport, receive_dir=tmp_path / "tx", peer_key="fixture-peer",
            id_factory=lambda: meta.transfer_id, resume_handshake_timeout_s=5,
        )
        meta_sent = threading.Event()
        data_sent = threading.Event()
        allow_data = threading.Event()

        def to_receiver(message):
            if isinstance(message, MetaMessage):
                assert message == meta
                meta_sent.set()
            if isinstance(message, DataMessage):
                data_sent.set()
                assert allow_data.wait(5), "sender DATA gate was not released"
            rx.feed_binary(encode_message(message, 243))

        tx_transport.on_send = to_receiver
        transport.on_send = lambda message: tx.feed_binary(encode_message(message, 243))
        try:
            tx.start_send(source)
            assert meta_sent.wait(2)
            for _ in range(20):
                rx.feed_binary(encode_message(meta, 243))
            flush_rx(rx, monkeypatch)
            assert rx._outbox.queue.qsize() == 1
            assert len(claims) == 1
            assert rx._resume_store.load_incoming(meta.transfer_id)[0]["status"] == "suspended"
            assert rx._resume_store.incoming_part(meta.transfer_id).read_bytes() == chunks[0]
            journal = tx._resume_store.outgoing_manifest(meta.transfer_id)
            assert tx._resume_store.read_json(journal)["status"] == "active"
            assert not transport.sent
            with pytest.raises(FileTransferError) as caught:
                rx.close_transfer(meta.transfer_id)
            assert caught.value.code == "file_transfer_active"
            assert rx._records[meta.transfer_id].rx_meta == meta

            proceed.set()
            assert data_sent.wait(2)
            assert rx._incoming.record.transfer_id == meta.transfer_id
            assert rx._incoming.record.chunks_completed == 1
            assert rx._incoming.record.failure is None
            assert len(claims) == 2
            resumes = [m for m in transport.sent if isinstance(m, ResumeMessage)]
            assert resumes and all(m.next_chunk == 1 for m in resumes)
            assert tx._resume_store.read_json(journal)["status"] == "active"
            assert [m.chunk_index for m in tx_transport.sent if isinstance(m, DataMessage)] == [1]

            allow_data.set()
            assert wait_until(lambda: tx._records[meta.transfer_id].state == "completed")
            assert wait_until(lambda: rx._records[meta.transfer_id].state == "completed")
            assert (rx.receive_dir / meta.filename).read_bytes() == source.read_bytes()
            assert len(list(rx.receive_dir.glob("*.bin"))) == 1
            assert not any(isinstance(m, ResultMessage) and not m.ok for m in transport.sent)
        finally:
            proceed.set()
            allow_data.set()
            tx.close()
            transport.on_send = None


def test_conflicting_meta_and_other_admission_stay_rejected_during_settlement(
    tmp_path, monkeypatch,
):
    with timed_out_receiver(tmp_path, monkeypatch, "release") as setup:
        rx, transport, meta, chunks, _, proceed, claims = setup
        rx.feed_binary(encode_message(replace(meta, filename="conflict.bin"), 243))
        rx.feed_binary(encode_message(replace(meta, transfer_id=99), 243))
        flush_rx(rx, monkeypatch)
        assert len(claims) == 1
        assert rx._resume_store.incoming_part(meta.transfer_id).read_bytes() == chunks[0]
        proceed.set()
        assert rx._outbox.wait_idle(2)
        results = [m for m in transport.sent if isinstance(m, ResultMessage)]
        assert [(m.transfer_id, m.ok, m.code) for m in results] == [
            (meta.transfer_id, False, "invalid_metadata"), (99, False, "busy"),
        ]
        assert rx._active_id is None
        assert rx._incoming is None


@pytest.mark.parametrize("boundary", ["drain", "release"])
def test_failed_timeout_settlement_keeps_owner_and_retained_partial(
    tmp_path, monkeypatch, boundary,
):
    with timed_out_receiver(tmp_path, monkeypatch, boundary, failure=True) as setup:
        rx, transport, meta, chunks, _, proceed, claims = setup
        rx.feed_binary(encode_message(meta, 243))
        flush_rx(rx, monkeypatch)
        proceed.set()
        assert wait_until(lambda: any(isinstance(m, ResultMessage) for m in transport.sent))
        assert rx._outbox.wait_idle(2)
        assert rx._active_id == meta.transfer_id
        assert rx._incoming is None
        assert len(claims) == 1
        assert rx._resume_store.load_incoming(meta.transfer_id)[0]["status"] == "suspended"
        assert rx._resume_store.incoming_part(meta.transfer_id).read_bytes() == chunks[0]
        results = [m for m in transport.sent if isinstance(m, ResultMessage)]
        assert [(m.ok, m.code) for m in results] == [(False, "busy")]
        with pytest.raises(FileTransferError) as caught:
            rx._reserve_record(99, direction="TX", filename="other.bin")
        assert caught.value.code == "file_transfer_busy"
        assert rx._rx_thread.is_alive()


def test_new_owner_before_deferred_meta_gets_busy_without_losing_resume(
    tmp_path, monkeypatch,
):
    with timed_out_receiver(tmp_path, monkeypatch, "context") as setup:
        rx, transport, meta, chunks, _, proceed, claims = setup
        other = rx._reserve_record(99, direction="TX", filename="other.bin")
        rx.feed_binary(encode_message(meta, 243))
        flush_rx(rx, monkeypatch)
        proceed.set()
        assert wait_until(lambda: any(isinstance(m, ResultMessage) for m in transport.sent))
        assert rx._outbox.wait_idle(2)
        assert [(m.ok, m.code) for m in transport.sent if isinstance(m, ResultMessage)] == [(False, "busy")]
        assert rx._active_id == 99
        assert len(claims) == 2
        assert rx._resume_store.incoming_part(meta.transfer_id).read_bytes() == chunks[0]

        rx._terminal_record(other, "failed")
        rx.feed_binary(encode_message(meta, 243))
        assert wait_until(lambda: rx._incoming is not None)
        assert rx._incoming.record.transfer_id == meta.transfer_id
        assert rx._incoming.record.chunks_completed == 1


def test_close_during_timeout_settlement_does_not_reopen_deferred_meta(
    tmp_path, monkeypatch,
):
    with timed_out_receiver(tmp_path, monkeypatch, "release") as setup:
        rx, transport, meta, chunks, _, proceed, claims = setup
        rx.feed_binary(encode_message(meta, 243))
        flush_rx(rx, monkeypatch)
        closer = threading.Thread(target=rx.close)
        closer.start()
        try:
            assert rx._stopping.wait(2)
            proceed.set()
            closer.join(3)
            assert not closer.is_alive()
            assert not rx._rx_thread.is_alive()
            assert not rx._outbox.worker.is_alive()
            assert rx._incoming is None
            assert len(claims) == 1
            assert rx._resume_store.incoming_part(meta.transfer_id).read_bytes() == chunks[0]
            assert rx._resume_store.load_incoming(meta.transfer_id)[0]["status"] == "suspended"
            assert not transport.sent
        finally:
            proceed.set()
            closer.join(3)


def test_full_outbox_during_meta_deferral_preserves_partial_for_next_replay(
    tmp_path, monkeypatch,
):
    with timed_out_receiver(tmp_path, monkeypatch, "release") as setup:
        rx, transport, meta, chunks, _, proceed, claims = setup
        for _ in range(rx._outbox.queue.maxsize):
            rx._outbox.submit(lambda: None)
        rx.feed_binary(encode_message(meta, 243))
        flush_rx(rx, monkeypatch)
        events = rx.observe(meta.transfer_id, cursor=0, window=100)["events"]
        assert any(e["kind"] == "meta_replay_failed" for e in events)
        assert len(claims) == 1
        assert rx._resume_store.incoming_part(meta.transfer_id).read_bytes() == chunks[0]
        proceed.set()
        assert rx._outbox.wait_idle(2)
        assert not transport.sent

        rx.feed_binary(encode_message(meta, 243))
        assert wait_until(lambda: rx._incoming is not None)
        assert rx._incoming.record.chunks_completed == 1
        assert wait_until(lambda: any(isinstance(m, ResumeMessage) for m in transport.sent))
        assert [m.next_chunk for m in transport.sent if isinstance(m, ResumeMessage)] == [1]
