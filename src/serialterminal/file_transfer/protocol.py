from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
import struct


MAGIC = b"FT"
VERSION = 1

_COMMON = struct.Struct(">2sBBQ")
_META_FIXED = struct.Struct(">QQBH32sB")
_DATA_FIXED = struct.Struct(">I")
_END_FIXED = struct.Struct(">I32s")
_RESULT_FIXED = struct.Struct(">BBB")


class MessageType(IntEnum):
    META = 1
    DATA = 2
    END = 3
    RESULT = 4


class Compression(IntEnum):
    NONE = 0
    GZIP = 1


_RESULT_CODE_TO_INT = {
    "ok": 0,
    "busy": 1,
    "invalid_metadata": 2,
    "invalid_chunk": 3,
    "missing_chunks": 4,
    "wire_hash_mismatch": 5,
    "decompression_failed": 6,
    "original_hash_mismatch": 7,
    "storage_failed": 8,
    "cancelled": 9,
    "protocol_error": 10,
    "remote_failed": 11,
}
_RESULT_INT_TO_CODE = {value: key for key, value in _RESULT_CODE_TO_INT.items()}


class FileProtocolError(ValueError):
    pass


@dataclass(frozen=True)
class MetaMessage:
    transfer_id: int
    filename: str
    original_size: int
    wire_size: int
    compression: Compression
    chunk_size: int
    original_sha256: bytes


@dataclass(frozen=True)
class DataMessage:
    transfer_id: int
    chunk_index: int
    payload: bytes


@dataclass(frozen=True)
class EndMessage:
    transfer_id: int
    chunk_count: int
    wire_sha256: bytes


@dataclass(frozen=True)
class ResultMessage:
    transfer_id: int
    ok: bool
    code: str
    reason: str


FileMessage = MetaMessage | DataMessage | EndMessage | ResultMessage


def transfer_id_text(transfer_id: int) -> str:
    return f"{transfer_id:016x}"


def parse_transfer_id(value: str | int) -> int:
    if isinstance(value, bool):
        raise FileProtocolError("transfer_id must not be boolean")
    if isinstance(value, int):
        if 0 <= value <= 0xFFFFFFFFFFFFFFFF:
            return value
        raise FileProtocolError("transfer_id integer is out of uint64 range")
    if not isinstance(value, str) or not value:
        raise FileProtocolError("transfer_id must be a non-empty hex string")
    try:
        parsed = int(value, 16)
    except ValueError as exc:
        raise FileProtocolError("transfer_id is not valid hex") from exc
    if not 0 <= parsed <= 0xFFFFFFFFFFFFFFFF:
        raise FileProtocolError("transfer_id is out of uint64 range")
    return parsed


def data_payload_capacity(binary_payload_capacity: int) -> int:
    if (
        isinstance(binary_payload_capacity, bool)
        or not isinstance(binary_payload_capacity, int)
    ):
        raise FileProtocolError("binary payload capacity must be an integer")
    capacity = binary_payload_capacity - _COMMON.size - _DATA_FIXED.size
    if capacity <= 0:
        raise FileProtocolError("binary payload capacity is too small for FT1 DATA")
    return capacity


def _common(message_type: MessageType, transfer_id: int) -> bytes:
    if not 0 <= transfer_id <= 0xFFFFFFFFFFFFFFFF:
        raise FileProtocolError("transfer_id is out of uint64 range")
    return _COMMON.pack(MAGIC, VERSION, int(message_type), transfer_id)


def encode_meta(message: MetaMessage, capacity: int) -> bytes:
    filename = message.filename.encode("utf-8")
    if len(message.original_sha256) != 32:
        raise FileProtocolError("META original_sha256 must be 32 bytes")
    if not 0 <= message.original_size <= 0xFFFFFFFFFFFFFFFF:
        raise FileProtocolError("META original_size is out of range")
    if not 0 <= message.wire_size <= 0xFFFFFFFFFFFFFFFF:
        raise FileProtocolError("META wire_size is out of range")
    if not 1 <= message.chunk_size <= 0xFFFF:
        raise FileProtocolError("META chunk_size is out of range")
    max_filename = capacity - _COMMON.size - _META_FIXED.size
    if not filename or len(filename) > min(255, max_filename):
        raise FileProtocolError("META filename does not fit one binary USER")
    payload = (
        _common(MessageType.META, message.transfer_id)
        + _META_FIXED.pack(
            message.original_size,
            message.wire_size,
            int(message.compression),
            message.chunk_size,
            message.original_sha256,
            len(filename),
        )
        + filename
    )
    if len(payload) > capacity:
        raise FileProtocolError("META exceeds binary payload capacity")
    return payload


def encode_data(message: DataMessage, capacity: int) -> bytes:
    if not 0 <= message.chunk_index <= 0xFFFFFFFF:
        raise FileProtocolError("DATA chunk_index is out of range")
    usable = data_payload_capacity(capacity)
    if not message.payload or len(message.payload) > usable:
        raise FileProtocolError(
            f"DATA payload must be 1..{usable} bytes for this transport"
        )
    return (
        _common(MessageType.DATA, message.transfer_id)
        + _DATA_FIXED.pack(message.chunk_index)
        + bytes(message.payload)
    )


def encode_end(message: EndMessage, capacity: int) -> bytes:
    if not 0 <= message.chunk_count <= 0xFFFFFFFF:
        raise FileProtocolError("END chunk_count is out of range")
    if len(message.wire_sha256) != 32:
        raise FileProtocolError("END wire_sha256 must be 32 bytes")
    payload = (
        _common(MessageType.END, message.transfer_id)
        + _END_FIXED.pack(message.chunk_count, message.wire_sha256)
    )
    if len(payload) > capacity:
        raise FileProtocolError("END exceeds binary payload capacity")
    return payload


def encode_result(message: ResultMessage, capacity: int) -> bytes:
    code_value = _RESULT_CODE_TO_INT.get(message.code)
    if code_value is None:
        raise FileProtocolError(f"unknown RESULT code: {message.code}")
    reason = message.reason.encode("utf-8")
    max_reason = capacity - _COMMON.size - _RESULT_FIXED.size
    if len(reason) > min(255, max_reason):
        reason = reason[: min(255, max_reason)]
        while True:
            try:
                reason.decode("utf-8")
                break
            except UnicodeDecodeError:
                reason = reason[:-1]
    payload = (
        _common(MessageType.RESULT, message.transfer_id)
        + _RESULT_FIXED.pack(0 if message.ok else 1, code_value, len(reason))
        + reason
    )
    if len(payload) > capacity:
        raise FileProtocolError("RESULT exceeds binary payload capacity")
    return payload


def encode_message(message: FileMessage, capacity: int) -> bytes:
    if isinstance(message, MetaMessage):
        return encode_meta(message, capacity)
    if isinstance(message, DataMessage):
        return encode_data(message, capacity)
    if isinstance(message, EndMessage):
        return encode_end(message, capacity)
    if isinstance(message, ResultMessage):
        return encode_result(message, capacity)
    raise TypeError(f"unsupported FT1 message: {type(message)!r}")


def _decode_common(data: bytes) -> tuple[MessageType, int] | None:
    if len(data) < _COMMON.size:
        return None
    magic, version, raw_type, transfer_id = _COMMON.unpack_from(data)
    if magic != MAGIC:
        return None
    if version != VERSION:
        raise FileProtocolError(f"unsupported file-transfer version: {version}")
    try:
        message_type = MessageType(raw_type)
    except ValueError as exc:
        raise FileProtocolError(f"unknown FT1 message type: {raw_type}") from exc
    return message_type, transfer_id


def decode_message(data: bytes) -> FileMessage | None:
    common = _decode_common(data)
    if common is None:
        return None
    message_type, transfer_id = common
    offset = _COMMON.size

    if message_type is MessageType.META:
        minimum = offset + _META_FIXED.size
        if len(data) < minimum:
            raise FileProtocolError("truncated META")
        (
            original_size,
            wire_size,
            compression_value,
            chunk_size,
            original_sha256,
            filename_len,
        ) = _META_FIXED.unpack_from(data, offset)
        if len(data) != minimum + filename_len:
            raise FileProtocolError("META filename length mismatch")
        try:
            compression = Compression(compression_value)
        except ValueError as exc:
            raise FileProtocolError(
                f"unknown META compression method: {compression_value}"
            ) from exc
        try:
            filename = data[minimum:].decode("utf-8")
        except UnicodeDecodeError as exc:
            raise FileProtocolError("META filename is not UTF-8") from exc
        if not filename:
            raise FileProtocolError("META filename is empty")
        if chunk_size <= 0:
            raise FileProtocolError("META chunk_size must be positive")
        return MetaMessage(
            transfer_id=transfer_id,
            filename=filename,
            original_size=original_size,
            wire_size=wire_size,
            compression=compression,
            chunk_size=chunk_size,
            original_sha256=original_sha256,
        )

    if message_type is MessageType.DATA:
        minimum = offset + _DATA_FIXED.size
        if len(data) <= minimum:
            raise FileProtocolError("truncated or empty DATA")
        (chunk_index,) = _DATA_FIXED.unpack_from(data, offset)
        return DataMessage(
            transfer_id=transfer_id,
            chunk_index=chunk_index,
            payload=bytes(data[minimum:]),
        )

    if message_type is MessageType.END:
        expected = offset + _END_FIXED.size
        if len(data) != expected:
            raise FileProtocolError("END length mismatch")
        chunk_count, wire_sha256 = _END_FIXED.unpack_from(data, offset)
        return EndMessage(
            transfer_id=transfer_id,
            chunk_count=chunk_count,
            wire_sha256=wire_sha256,
        )

    expected = offset + _RESULT_FIXED.size
    if len(data) < expected:
        raise FileProtocolError("truncated RESULT")
    failed, code_value, reason_len = _RESULT_FIXED.unpack_from(data, offset)
    if failed not in (0, 1):
        raise FileProtocolError("RESULT status is invalid")
    if len(data) != expected + reason_len:
        raise FileProtocolError("RESULT reason length mismatch")
    try:
        reason = data[expected:].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FileProtocolError("RESULT reason is not UTF-8") from exc
    return ResultMessage(
        transfer_id=transfer_id,
        ok=failed == 0,
        code=_RESULT_INT_TO_CODE.get(code_value, f"code_{code_value}"),
        reason=reason,
    )
