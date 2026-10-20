import threading
import pytest

from serialterminal.file_transfer import FileTransferManager, DataMessage, encode_message
from serialterminal.file_transfer import core
from serialterminal.file_transfer.outbox import Outbox, OutboxError
from test_file_transfer_failure_retention import CaptureTransport, fixture, wait_until


def test_rx_stores_data_while_control_transport_is_blocked(tmp_path):
    transport=CaptureTransport();blocked=threading.Event();release=threading.Event()
    def on_send(message):
        blocked.set();release.wait(2)
    manager=FileTransferManager(transport,receive_dir=tmp_path)
    meta,chunks,end=fixture(manager,count=3)
    # fixture uses direct entry points; submit an actual RX replay next.
    transport.on_send=None
    manager._outbox.queue.join()
    transport.on_send=on_send
    try:
        manager.feed_binary(encode_message(meta,243))
        assert blocked.wait(1)
        for index, chunk in enumerate(chunks): manager.feed_binary(encode_message(DataMessage(meta.transfer_id,index,chunk),243))
        assert wait_until(lambda: manager._records[meta.transfer_id].chunks_completed==3)
        assert not release.is_set()
        assert manager._rx_thread.is_alive()
    finally:
        release.set();manager.close()


def test_outbox_is_bounded_and_shutdown_never_executes_queued_jobs():
    box=Outbox(capacity=2);entered=threading.Event();release=threading.Event();calls=[]
    def blocked(): entered.set();release.wait(1)
    box.submit(blocked);assert entered.wait(1)
    queued=box.submit(lambda:calls.append(1));box.submit(lambda:calls.append(2))
    with pytest.raises(OutboxError): box.submit(lambda:calls.append(3))
    box.discard_pending();assert queued.done.is_set()
    assert isinstance(queued.error,OutboxError)
    release.set();box.close(1)
    assert calls==[];assert not box.worker.is_alive()


def test_outbox_callback_exception_is_visible_and_worker_survives():
    box=Outbox()
    def fail(): raise OSError("backend failed")
    def broken_callback(exc): raise RuntimeError("callback failed")
    job=box.submit(fail,on_error=broken_callback);assert job.done.wait(1)
    assert box.last_error=="backend failed" and box.callback_error=="callback failed"
    assert box.call(lambda:7)==7;box.close()


def test_completed_service_meta_replay_does_not_enqueue_old_repair(tmp_path):
    import hashlib
    from serialterminal.file_transfer import MetaMessage, Compression, ResultMessage
    from serialterminal.file_transfer.recursive import _Frame
    transport = CaptureTransport()
    manager = FileTransferManager(transport, receive_dir=tmp_path)
    record = manager._reserve_record(100, direction="TX", filename="x")
    meta = MetaMessage(101, "missing.bin", 28, 28, Compression.NONE, 227,
                       hashlib.sha256(b"list").digest(), parent_transfer_id=100, depth=1)
    frame = _Frame(record, processed={101: meta})
    manager._recursive_frames[100] = frame
    try:
        for _ in range(core.FILE_CONTROL_QUEUE_CAPACITY + 1):
            manager._handle_meta(meta)
            assert manager._outbox.wait_idle(1)
        assert not frame.requests and frame.child_id is None
        assert manager._incoming is None
        assert record.remote_result is None
        assert not record.remote_failure_event.is_set()
        replies = transport.sent
        assert len(replies) == core.FILE_CONTROL_QUEUE_CAPACITY + 1
        assert all(isinstance(reply, ResultMessage) and reply.transfer_id == 101 and reply.ok for reply in replies)
    finally:
        manager.close()


def test_rx_overflow_retains_partial_and_worker_survives(tmp_path,monkeypatch):
    monkeypatch.setattr(core,"FILE_RX_QUEUE_CAPACITY",2)
    manager=FileTransferManager(CaptureTransport(),receive_dir=tmp_path)
    meta,chunks,end=fixture(manager,count=3)
    blocked=threading.Event();release=threading.Event()
    original=manager._handle_data
    def store(message):
        blocked.set();release.wait(2);original(message)
    manager._handle_data=store
    try:
        manager.feed_binary(encode_message(DataMessage(meta.transfer_id,0,chunks[0]),243))
        assert blocked.wait(1)
        for index in range(1,5):
            manager.feed_binary(encode_message(DataMessage(meta.transfer_id,index%3,chunks[index%3]),243))
        assert manager._rx_queue.qsize()==2 and manager._rx_overflow.is_set()
        release.set()
        record=manager._records[meta.transfer_id]
        assert wait_until(lambda:record.state=="failed")
        assert record.failure["code"]=="receiver_overflow"
        assert manager._resume_store.incoming_part(meta.transfer_id).read_bytes().startswith(chunks[0])
        assert manager._rx_thread.is_alive()
    finally: release.set();manager.close()


def test_close_finalizes_discarded_terminal_job_without_losing_publication(tmp_path):
    transport=CaptureTransport();manager=FileTransferManager(transport,receive_dir=tmp_path)
    meta,chunks,end=fixture(manager,count=1)
    entered=threading.Event();release=threading.Event()
    def send(message): entered.set();release.wait(3)
    transport.on_send=send
    try:
        manager.feed_binary(encode_message(meta,243));assert entered.wait(1)
        manager.feed_binary(encode_message(DataMessage(meta.transfer_id,0,chunks[0]),243))
        manager.feed_binary(encode_message(end,243))
        destination=tmp_path/meta.filename
        assert wait_until(lambda:destination.exists() and manager._incoming is None)
        assert destination.read_bytes()==chunks[0]
        closer=threading.Thread(target=manager.close);closer.start()
        record=manager._records[meta.transfer_id]
        assert wait_until(lambda:record.state=="failed")
        assert record.failure["code"]=="local_ownership_unsettled"
        assert record.final_path==str(destination)
        assert manager._active_id==meta.transfer_id
        release.set();closer.join(3);assert not closer.is_alive()
        assert destination.read_bytes()==chunks[0]
        assert manager._resume_store.load_completed(meta.transfer_id) is not None
    finally: release.set();manager.close()


def test_callbacks_start_only_after_all_storage_policies_are_ready(tmp_path):
    import hashlib
    from serialterminal.file_transfer import MetaMessage,EndMessage,Compression
    from serialterminal.file_transfer.manager import _DurableResumeStateStore
    payload=b"early RX"
    meta=MetaMessage(901,"early.bin",len(payload),len(payload),Compression.NONE,227,hashlib.sha256(payload).digest())
    end=EndMessage(901,1,hashlib.sha256(payload).digest())
    class EarlyTransport(CaptureTransport):
        def set_receiver(self,receiver):
            self.receiver=receiver
            if receiver is not None:
                assert isinstance(receiver.__self__._resume_store,_DurableResumeStateStore)
                receiver(encode_message(meta,243))
        def start(self):
            self.receiver(encode_message(DataMessage(901,0,payload),243))
            self.receiver(encode_message(end,243))
    manager=FileTransferManager(EarlyTransport(),receive_dir=tmp_path)
    try:
        assert wait_until(lambda:manager._records.get(901) is not None and manager._records[901].state=="completed")
        assert (tmp_path/"early.bin").read_bytes()==payload
        assert manager._rx_thread.is_alive()
    finally: manager.close()
