import hashlib

import pytest

from serialterminal.file_transfer.protocol import (
    Compression,
    DataMessage,
    EndMessage,
    FileProtocolError,
    MetaMessage,
    ResultMessage,
    data_payload_capacity,
    decode_message,
    encode_message,
)


def test_ft1_meta_roundtrip():
    digest = hashlib.sha256(b"source").digest()
    message = MetaMessage(
        transfer_id=0x1122334455667788,
        filename="пример.bin",
        original_size=12345,
        wire_size=6789,
        compression=Compression.GZIP,
        chunk_size=data_payload_capacity(200),
        original_sha256=digest,
    )

    encoded = encode_message(message, 200)

    assert len(encoded) <= 200
    assert decode_message(encoded) == message


def test_ft1_data_uses_transport_capacity_minus_compact_header():
    usable = data_payload_capacity(200)
    assert usable == 184
    payload = bytes(range(184))
    message = DataMessage(transfer_id=9, chunk_index=123, payload=payload)

    encoded = encode_message(message, 200)

    assert len(encoded) == 200
    assert decode_message(encoded) == message


def test_ft1_end_and_result_roundtrip():
    digest = hashlib.sha256(b"wire").digest()
    end = EndMessage(transfer_id=3, chunk_count=77, wire_sha256=digest)
    ok = ResultMessage(transfer_id=3, ok=True, code="ok", reason="")
    failed = ResultMessage(
        transfer_id=3,
        ok=False,
        code="original_hash_mismatch",
        reason="bad original hash",
    )

    assert decode_message(encode_message(end, 200)) == end
    assert decode_message(encode_message(ok, 200)) == ok
    assert decode_message(encode_message(failed, 200)) == failed


def test_non_file_binary_payload_is_not_claimed_by_ft1():
    assert decode_message(b"opaque application bytes") is None


def test_unknown_ft1_version_is_rejected_not_guessed():
    payload = bytearray(encode_message(
        ResultMessage(transfer_id=1, ok=True, code="ok", reason=""),
        200,
    ))
    payload[2] = 2

    with pytest.raises(FileProtocolError, match="version"):
        decode_message(bytes(payload))
