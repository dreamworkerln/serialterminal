import hashlib

import pytest

from serialterminal.file_transfer.protocol import (
    Compression,
    DataMessage,
    EndMessage,
    FileProtocolError,
    MetaMessage,
    MissingMessage,
    MissingRange,
    ResultMessage,
    canonical_missing_ranges,
    data_payload_capacity,
    decode_message,
    missing_range_capacity,
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



def test_ft1_missing_roundtrip_one_and_multiple_ranges():
    one = MissingMessage(transfer_id=7, ranges=(MissingRange(101, 6),))
    many = MissingMessage(
        transfer_id=8,
        ranges=(
            MissingRange(1, 2),
            MissingRange(10, 1),
            MissingRange(1000, 7),
        ),
    )

    assert decode_message(encode_message(one, 200)) == one
    assert decode_message(encode_message(many, 200)) == many


def test_canonical_missing_ranges_sorts_deduplicates_and_coalesces():
    assert canonical_missing_ranges(
        [12, 10, 11, 3, 3, 4],
        chunk_count=20,
    ) == (
        MissingRange(3, 2),
        MissingRange(10, 3),
    )


@pytest.mark.parametrize(
    "ranges",
    [
        (MissingRange(4, 0),),
        (MissingRange(4, 2), MissingRange(5, 1)),
        (MissingRange(4, 2), MissingRange(6, 1)),
        (MissingRange(9, 1), MissingRange(2, 1)),
    ],
)
def test_missing_rejects_noncanonical_or_invalid_ranges(ranges):
    with pytest.raises(FileProtocolError):
        encode_message(MissingMessage(1, ranges), 200)


def test_missing_range_set_uses_advertised_transport_capacity_without_pagination():
    assert missing_range_capacity(200) == 23
    fits = MissingMessage(
        1,
        tuple(MissingRange(index * 2, 1) for index in range(23)),
    )
    assert len(encode_message(fits, 200)) <= 200

    too_many = MissingMessage(
        1,
        tuple(MissingRange(index * 2, 1) for index in range(24)),
    )
    with pytest.raises(FileProtocolError, match="does not fit"):
        encode_message(too_many, 200)

    assert missing_range_capacity(100) == 10


def test_canonical_missing_ranges_rejects_out_of_declared_chunk_count():
    with pytest.raises(FileProtocolError, match="outside declared"):
        canonical_missing_ranges([0, 5], chunk_count=5)
