import hashlib
import time

from serialterminal.file_transfer import BinarySendReceipt, FileTransferManager


class _CaptureTransport:
    payload_capacity = 200

    def __init__(self):
        self.receiver = None
        self.sent = []

    def set_receiver(self, receiver):
        self.receiver = receiver

    def send_binary(self, data, *, cancel_event=None):
        self.sent.append(bytes(data))
        return BinarySendReceipt(tx_id=len(self.sent))


def _journal(source, *, transfer_id, wire_chunk_size=184):
    payload = source.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    return {
        "schema": 1,
        "kind": "outgoing",
        "transfer_id": f"{transfer_id:016x}",
        "status": "active",
        "source_path": str(source.resolve()),
        "filename": source.name,
        "original_size": len(payload),
        "original_sha256": digest,
        "wire_size": len(payload),
        "wire_sha256": digest,
        "compression": 0,
        "chunk_size": wire_chunk_size,
        "updated": time.time(),
    }


def test_zero_transfer_id_journal_is_not_reused(tmp_path):
    source = tmp_path / "source.bin"
    source.write_bytes(bytes(range(251)) * 4)
    transport = _CaptureTransport()
    manager = FileTransferManager(
        transport,
        receive_dir=tmp_path / "state",
        id_factory=lambda: 0xBEEF,
        resume_handshake_timeout_s=0.05,
    )
    journal_path = manager._resume_store.outgoing_manifest(0)
    manager._resume_store.atomic_json(journal_path, _journal(source, transfer_id=0))

    try:
        started = manager.start_send(source)
        assert started["transfer_id"] == "000000000000beef"
        assert started.get("resumed") is not True
    finally:
        manager.close()


def test_manifest_filename_and_embedded_transfer_id_must_agree(tmp_path):
    source = tmp_path / "source.bin"
    source.write_bytes(bytes(range(239)) * 5)
    transport = _CaptureTransport()
    manager = FileTransferManager(
        transport,
        receive_dir=tmp_path / "state",
        id_factory=lambda: 0xCAFE,
        resume_handshake_timeout_s=0.05,
    )
    wrong_path = manager._resume_store.outgoing_manifest(0x1111)
    manager._resume_store.atomic_json(
        wrong_path,
        _journal(source, transfer_id=0x2222),
    )

    try:
        started = manager.start_send(source)
        assert started["transfer_id"] == "000000000000cafe"
        assert started.get("resumed") is not True
    finally:
        manager.close()
