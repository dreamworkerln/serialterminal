import hashlib
import random
import time

from serialterminal.file_transfer import (
    BinarySendReceipt,
    Compression,
    DataMessage,
    FileTransferManager,
    MetaMessage,
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


def _wait_until(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.01)
    return predicate()


def test_timed_out_receiver_reopens_same_transfer_in_same_process(tmp_path):
    transport = _CaptureTransport()
    manager = FileTransferManager(
        transport,
        receive_dir=tmp_path,
        incoming_idle_timeout_s=0.05,
    )
    payload = random.Random(20).randbytes(700)
    chunk_size = data_payload_capacity(transport.payload_capacity)
    transfer_id = 0x5151
    meta = MetaMessage(
        transfer_id=transfer_id,
        filename="resume.bin",
        original_size=len(payload),
        wire_size=len(payload),
        compression=Compression.NONE,
        chunk_size=chunk_size,
        original_sha256=hashlib.sha256(payload).digest(),
    )
    chunks = [
        payload[offset : offset + chunk_size]
        for offset in range(0, len(payload), chunk_size)
    ]

    try:
        manager.feed_binary(encode_message(meta, transport.payload_capacity))
        manager.feed_binary(
            encode_message(
                DataMessage(transfer_id, 0, chunks[0]),
                transport.payload_capacity,
            )
        )
        failed = _wait_until(
            lambda: (
                item
                if (item := manager.display_snapshot())
                and item["state"] == "failed"
                else None
            )
        )
        assert failed["failure"]["code"] == "remote_sender_timeout"

        transport.sent.clear()
        manager.feed_binary(encode_message(meta, transport.payload_capacity))
        reopened = _wait_until(
            lambda: (
                item
                if (item := manager.display_snapshot())
                and item["state"] == "receiving"
                else None
            )
        )
        assert reopened["transfer_id"] == f"{transfer_id:016x}"
        assert reopened["chunks_completed"] == 1
        assert reopened["failure"] is None

        resume = _wait_until(
            lambda: next(
                (
                    message
                    for raw in transport.sent
                    if isinstance((message := decode_message(raw)), ResumeMessage)
                ),
                None,
            )
        )
        assert resume.next_chunk == 1
    finally:
        manager.close()
