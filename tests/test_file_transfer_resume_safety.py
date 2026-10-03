import hashlib
import time
from types import SimpleNamespace

from serialterminal.file_transfer import (
    BinarySendReceipt,
    Compression,
    EndMessage,
    FileTransferManager,
    MetaMessage,
    ResultMessage,
    ResumeMessage,
    decode_message,
    encode_message,
)
from serialterminal.file_transfer.protocol import data_payload_capacity


class _CaptureTransport:
    payload_capacity = 200

    def __init__(self):
        self.receiver = None
        self.sent = []

    def set_receiver(self, receiver):
        self.receiver = receiver

    def send_binary(self, data, *, cancel_event=None):
        payload = bytes(data)
        self.sent.append(payload)
        return BinarySendReceipt(tx_id=len(self.sent))


def _meta(transport, *, transfer_id=0xD00D, payload=b"durable-state"):
    return MetaMessage(
        transfer_id=transfer_id,
        filename="resume.bin",
        original_size=len(payload),
        wire_size=len(payload),
        compression=Compression.NONE,
        chunk_size=data_payload_capacity(transport.payload_capacity),
        original_sha256=hashlib.sha256(payload).digest(),
    )


def _messages(transport):
    return [decode_message(raw) for raw in transport.sent]


def _wait_for_messages(transport, timeout=1.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and not transport.sent:
        time.sleep(0.01)
    return _messages(transport)


def test_receiver_checkpoint_fsyncs_part_before_manifest(monkeypatch, tmp_path):
    transport = _CaptureTransport()
    manager = FileTransferManager(transport, receive_dir=tmp_path)
    meta = _meta(transport)
    part = manager._resume_store.incoming_part(meta.transfer_id)
    part.write_bytes(b"durable-state")
    incoming = SimpleNamespace(
        meta=meta,
        wire_path=part,
        received={0: len(b"durable-state")},
        _checkpoint_count=0,
        _checkpoint_time=0.0,
        _persistent_status="receiving",
    )
    order = []

    monkeypatch.setattr(
        "serialterminal.file_transfer.manager.os.fsync",
        lambda _fd: order.append("part_fsync"),
    )
    monkeypatch.setattr(
        manager._resume_store,
        "save_incoming",
        lambda **_kwargs: order.append("manifest"),
    )

    try:
        manager._checkpoint_incoming(incoming, force=True)
        assert order == ["part_fsync", "manifest"]
    finally:
        manager.close()


def test_completed_tombstone_outside_receive_dir_is_not_trusted(tmp_path):
    receive_dir = tmp_path / "rx"
    outside = tmp_path / "outside.bin"
    payload = b"published elsewhere"
    outside.write_bytes(payload)
    transport = _CaptureTransport()
    manager = FileTransferManager(transport, receive_dir=receive_dir)
    meta = _meta(transport, transfer_id=0xA101, payload=payload)
    end = EndMessage(meta.transfer_id, 1, hashlib.sha256(payload).digest())
    manager._resume_store.save_completed(meta=meta, end=end, final_path=outside)

    try:
        manager.feed_binary(encode_message(meta, transport.payload_capacity))
        messages = _wait_for_messages(transport)
        assert not any(
            isinstance(item, ResultMessage) and item.ok for item in messages
        )
        assert any(isinstance(item, ResumeMessage) for item in messages)
    finally:
        manager.close()


def test_publishing_manifest_outside_receive_dir_is_not_reconciled(tmp_path):
    receive_dir = tmp_path / "rx"
    outside = tmp_path / "outside.bin"
    payload = b"publishing elsewhere"
    outside.write_bytes(payload)
    transport = _CaptureTransport()
    manager = FileTransferManager(transport, receive_dir=receive_dir)
    meta = _meta(transport, transfer_id=0xA202, payload=payload)
    end = EndMessage(meta.transfer_id, 1, hashlib.sha256(payload).digest())
    part = manager._resume_store.incoming_part(meta.transfer_id)
    part.write_bytes(payload)
    manager._resume_store.save_incoming(
        meta=meta,
        received={0: len(payload)},
        status="publishing",
        end=end,
        destination=outside,
    )

    try:
        manager.feed_binary(encode_message(meta, transport.payload_capacity))
        messages = _wait_for_messages(transport)
        assert not any(
            isinstance(item, ResultMessage) and item.ok for item in messages
        )
        resume = next(item for item in messages if isinstance(item, ResumeMessage))
        assert resume.next_chunk == 1
    finally:
        manager.close()


def test_completed_tombstone_symlink_is_not_trusted(tmp_path):
    receive_dir = tmp_path / "rx"
    receive_dir.mkdir(parents=True)
    payload = b"symlink target"
    target = tmp_path / "target.bin"
    target.write_bytes(payload)
    link = receive_dir / "resume.bin"
    link.symlink_to(target)
    transport = _CaptureTransport()
    manager = FileTransferManager(transport, receive_dir=receive_dir)
    meta = _meta(transport, transfer_id=0xA303, payload=payload)
    end = EndMessage(meta.transfer_id, 1, hashlib.sha256(payload).digest())
    manager._resume_store.save_completed(meta=meta, end=end, final_path=link)

    try:
        manager.feed_binary(encode_message(meta, transport.payload_capacity))
        messages = _wait_for_messages(transport)
        assert not any(
            isinstance(item, ResultMessage) and item.ok for item in messages
        )
        assert any(isinstance(item, ResumeMessage) for item in messages)
    finally:
        manager.close()
