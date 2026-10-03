import threading

from serialterminal.file_transfer import (
    BinarySendReceipt,
    DataMessage,
    FileTransferManager,
    decode_message,
)


class _DataProbeTransport:
    payload_capacity = 200

    def __init__(self):
        self.receiver = None
        self.data_seen = threading.Event()

    def set_receiver(self, receiver):
        self.receiver = receiver

    def send_binary(self, data, *, cancel_event=None):
        if isinstance(decode_message(data), DataMessage):
            self.data_seen.set()
        return BinarySendReceipt(tx_id=1)


def test_new_transfer_skips_resume_handshake_wait(tmp_path):
    source = tmp_path / "source.bin"
    source.write_bytes(bytes(range(251)) * 4)
    transport = _DataProbeTransport()
    manager = FileTransferManager(
        transport,
        receive_dir=tmp_path / "rx",
        id_factory=lambda: 0x5150,
        resume_handshake_timeout_s=5.0,
        result_timeout_s=0.2,
    )

    try:
        started = manager.start_send(source)
        assert started.get("resumed") is not True
        assert transport.data_seen.wait(timeout=0.75)
    finally:
        manager.close()
