import hashlib
import time

import pytest

from serialterminal.file_transfer import (
    BinarySendReceipt,
    Compression,
    FileTransferError,
    FileTransferManager,
    MetaMessage,
    ResultMessage,
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


def _outgoing_payload(source):
    payload = source.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    return {
        "status": "active",
        "source_path": str(source.resolve()),
        "filename": source.name,
        "original_size": len(payload),
        "original_sha256": digest,
        "wire_size": len(payload),
        "wire_sha256": digest,
        "compression": int(Compression.NONE),
        "chunk_size": data_payload_capacity(_CaptureTransport.payload_capacity),
    }


def _meta(transport, *, transfer_id, payload=b"resume-hardening"):
    return MetaMessage(
        transfer_id=transfer_id,
        filename="resume.bin",
        original_size=len(payload),
        wire_size=len(payload),
        compression=Compression.NONE,
        chunk_size=data_payload_capacity(transport.payload_capacity),
        original_sha256=hashlib.sha256(payload).digest(),
    )


def _wait_result(transport, transfer_id, timeout=1.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for raw in transport.sent:
            message = decode_message(raw)
            if isinstance(message, ResultMessage) and message.transfer_id == transfer_id:
                return message
        time.sleep(0.01)
    return None


def test_multiple_matching_sender_journals_fail_explicitly(tmp_path):
    source = tmp_path / "source.bin"
    source.write_bytes(bytes(range(251)) * 5)
    transport = _CaptureTransport()
    manager = FileTransferManager(
        transport,
        receive_dir=tmp_path / "rx",
        id_factory=lambda: 0x9000,
        resume_handshake_timeout_s=0.05,
    )
    payload = _outgoing_payload(source)
    manager._resume_store.save_outgoing(0x1111, payload)
    manager._resume_store.save_outgoing(0x2222, payload)

    try:
        with pytest.raises(FileTransferError) as raised:
            manager.start_send(source)
        assert raised.value.code == "ambiguous_resume_state"
        assert raised.value.details["transfer_ids"] == [
            "0000000000001111",
            "0000000000002222",
        ]
        assert transport.sent == []
    finally:
        manager.close()


def test_symlinked_sender_journal_is_not_reused(tmp_path):
    source = tmp_path / "source.bin"
    source.write_bytes(bytes(range(239)) * 5)
    transport = _CaptureTransport()
    manager = FileTransferManager(
        transport,
        receive_dir=tmp_path / "rx",
        id_factory=lambda: 0x3333,
        resume_handshake_timeout_s=0.05,
        result_timeout_s=0.1,
    )
    transfer_id = 0x1111
    manager._resume_store.save_outgoing(transfer_id, _outgoing_payload(source))
    manifest = manager._resume_store.outgoing_manifest(transfer_id)
    target = tmp_path / "outside-journal.json"
    manifest.replace(target)
    manifest.symlink_to(target)

    try:
        started = manager.start_send(source)
        assert started["transfer_id"] == "0000000000003333"
        assert started.get("resumed") is not True
    finally:
        manager.close()


def test_symlinked_receiver_part_is_not_restored(tmp_path):
    transport = _CaptureTransport()
    receive_dir = tmp_path / "rx"
    manager = FileTransferManager(transport, receive_dir=receive_dir)
    payload = b"resume-hardening"
    meta = _meta(transport, transfer_id=0x4444, payload=payload)
    part = manager._resume_store.incoming_part(meta.transfer_id)
    part.write_bytes(payload)
    manager._resume_store.save_incoming(
        meta=meta,
        received={0: len(payload)},
        status="suspended",
    )
    outside = tmp_path / "outside-part.bin"
    outside.write_bytes(payload)
    part.unlink()
    part.symlink_to(outside)

    try:
        manager.feed_binary(encode_message(meta, transport.payload_capacity))
        result = _wait_result(transport, meta.transfer_id)
        assert result is not None
        assert result.ok is False
        assert result.code == "storage_failed"
        assert outside.read_bytes() == payload
    finally:
        manager.close()


def test_symlinked_receiver_manifest_is_not_trusted(tmp_path):
    transport = _CaptureTransport()
    receive_dir = tmp_path / "rx"
    manager = FileTransferManager(transport, receive_dir=receive_dir)
    payload = b"resume-hardening"
    meta = _meta(transport, transfer_id=0x5555, payload=payload)
    part = manager._resume_store.incoming_part(meta.transfer_id)
    part.write_bytes(payload)
    manager._resume_store.save_incoming(
        meta=meta,
        received={0: len(payload)},
        status="suspended",
    )
    manifest = manager._resume_store.incoming_manifest(meta.transfer_id)
    target = tmp_path / "outside-manifest.json"
    manifest.replace(target)
    manifest.symlink_to(target)

    try:
        manager.feed_binary(encode_message(meta, transport.payload_capacity))
        result = _wait_result(transport, meta.transfer_id)
        assert result is not None
        assert result.ok is False
        assert result.code == "storage_failed"
        assert not (receive_dir / meta.filename).exists()
    finally:
        manager.close()
