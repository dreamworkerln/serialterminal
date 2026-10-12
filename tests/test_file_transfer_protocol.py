import hashlib
import struct

import pytest

from serialterminal.file_transfer.recursive import read_missing_list, write_missing_list

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
    payload[2] = 255

    with pytest.raises(FileProtocolError, match="version"):
        decode_message(bytes(payload))



def test_service_missing_list_roundtrip_one_and_multiple_ranges(tmp_path):
    one = MissingMessage(transfer_id=7, ranges=(MissingRange(101, 6),),request_id=99)
    many = MissingMessage(
        transfer_id=8,
        request_id=99,
        ranges=(
            MissingRange(1, 2),
            MissingRange(10, 1),
            MissingRange(1000, 7),
        ),
    )

    for message in (one,many):
        path = tmp_path / str(message.transfer_id)
        assert write_missing_list(path,message.transfer_id,message.ranges) == sum(r.count for r in message.ranges)
        assert read_missing_list(path,message.transfer_id,5000,99) == message


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
def test_service_list_rejects_noncanonical_or_invalid_ranges(tmp_path,ranges):
    path = tmp_path / "missing"
    with pytest.raises(FileProtocolError):
        write_missing_list(path,1,ranges)
    # Проверяем входящий бинарный файл независимо от валидирующего writer.
    total = sum(item.count for item in ranges)
    path.write_bytes(struct.pack(">4sQII", b"MRF2", 1, total, len(ranges)) +
                     b"".join(struct.pack(">II", item.start_chunk, item.count) for item in ranges))
    with pytest.raises(FileProtocolError):
        read_missing_list(path,1,100,99)


def test_service_range_count_is_independent_of_one_packet_capacity(tmp_path):
    ranges = tuple(MissingRange(index*2,1) for index in range(80))
    path = tmp_path / "missing"
    assert write_missing_list(path,1,ranges) == 80
    assert path.stat().st_size > 243
    result = read_missing_list(path,1,400,99)
    assert result.ranges == ranges
    assert result.request_id == 99


def test_canonical_missing_ranges_rejects_out_of_declared_chunk_count():
    with pytest.raises(FileProtocolError, match="outside declared"):
        canonical_missing_ranges([0, 5], chunk_count=5)


@pytest.mark.parametrize("status,code", [(0, 1), (0, 255), (1, 0)])
def test_result_decoder_rejects_contradictory_status_and_code(status, code):
    payload = bytearray(encode_message(ResultMessage(1, True, "ok", ""), 243))
    payload[-3] = status
    payload[-2] = code
    with pytest.raises(FileProtocolError, match="conflicts"):
        decode_message(bytes(payload))
