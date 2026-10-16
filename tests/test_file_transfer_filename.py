import hashlib
import time

import pytest

from serialterminal.file_transfer import FileTransferError, FileTransferManager, BinarySendReceipt
from serialterminal.file_transfer.protocol import (
    Compression, MetaMessage, FileProtocolError, encode_message, decode_message,
    encode_filename, meta_filename_capacity,
)


class Transport:
    payload_capacity = 243
    def __init__(self):
        self.receiver = None
        self.peer = None
        self.sent = []
    def set_receiver(self, receiver): self.receiver = receiver
    def send_binary(self, data, *, cancel_event=None):
        self.sent.append(bytes(data))
        if self.peer and self.peer.receiver: self.peer.receiver(bytes(data))
        return BinarySendReceipt(tx_id=len(self.sent))


@pytest.mark.parametrize("name", ["a" * 163, "a" * 255, "я" * 82])
def test_overlong_name_is_rejected_before_resume_lookup_claim_prepare_or_send(tmp_path, name):
    source = tmp_path / name
    source.write_bytes(b"content")
    transport = Transport()
    calls = []
    manager = FileTransferManager(transport, receive_dir=tmp_path / "receive",
                                  claim_transfer=lambda *args: calls.append("claim"),
                                  event_sink=lambda event: calls.append("event"))
    def forbidden(*args): raise AssertionError("rejected filename must have no admission/preparation side effects")
    manager._sender_resume_candidate = forbidden
    manager._prepare_source = forbidden
    manager._reserve_record = forbidden
    try:
        with pytest.raises(FileTransferError) as error: manager.start_send(source)
        assert error.value.code == "filename_too_long"
        assert "Имя файла слишком длинное" in error.value.message
        assert error.value.details == {"filename_bytes": len(name.encode('utf-8')), "max_filename_bytes": 162}
        assert not calls and not transport.sent and not manager.snapshots() and not manager.busy
        assert not list((tmp_path / "receive").rglob('*.json'))
    finally: manager.close()


@pytest.mark.parametrize("name", ["a" * 158 + ".bin", "я" * 81])
def test_boundary_filename_transfers_without_renaming(tmp_path, name):
    source = tmp_path / name
    source.write_bytes(b"0123456789" * 5)
    left, right = Transport(), Transport()
    left.peer, right.peer = right, left
    sender = FileTransferManager(left, receive_dir=tmp_path / 'sender')
    receiver = FileTransferManager(right, receive_dir=tmp_path / 'receiver')
    try:
        sender.start_send(source)
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            state = sender.display_snapshot()
            if state and state['state'] in {'completed', 'failed'}: break
            time.sleep(.01)
        assert state['state'] == 'completed', state
        target = tmp_path / 'receiver' / name
        assert target.read_bytes() == source.read_bytes()
        meta = next(decode_message(data) for data in left.sent if isinstance(decode_message(data), MetaMessage))
        assert meta.filename == name
        assert state['elapsed'] >= 0
    finally:
        sender.close()
        receiver.close()


@pytest.mark.parametrize("capacity,limit", [(80, 0), (100, 19), (200, 119), (243, 162), (500, 255)])
def test_filename_preflight_and_codec_share_transport_derived_budget(capacity, limit):
    assert meta_filename_capacity(capacity) == limit
    if limit:
        name = 'a' * limit
        message = MetaMessage(1, name, 0, 0, Compression.NONE, 1, hashlib.sha256(b'').digest())
        assert decode_message(encode_message(message, capacity)).filename == name
    with pytest.raises(FileProtocolError): encode_filename('a' * (limit + 1), capacity)


def test_non_utf8_filename_is_rejected_by_preflight_codec():
    with pytest.raises(FileProtocolError, match='UTF-8'): encode_filename('bad\udcff', 243)


def test_elapsed_advances_while_active_and_freezes_at_terminal(monkeypatch):
    from serialterminal.file_transfer.core import _TransferRecord
    clock = [10.0]
    monkeypatch.setattr("serialterminal.file_transfer.core.time.monotonic", lambda: clock[0])
    record = _TransferRecord(1, direction="TX", filename="file.bin", event_retention=10)
    clock[0] = 13.0
    assert record.snapshot()["elapsed"] == 3.0
    record.terminal("completed")
    clock[0] = 100.0
    assert record.snapshot()["elapsed"] == 3.0
