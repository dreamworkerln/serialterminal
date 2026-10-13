from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from enum import IntEnum
import struct
import zlib


class Kind(IntEnum):
    HELLO = 1
    WELCOME = 2
    SUBMIT = 3
    ACCEPTED = 4
    TX_DONE = 5
    LINK_OK = 6
    LINK_FAIL = 7
    REJECTED = 8
    RX = 9
    STATUS = 10
    QUERY = 11
    CLOSE = 12
    CLOSED = 13
    UNKNOWN = 14
    UNAVAILABLE = 15


HEADER = struct.Struct("<2sBBQIH")
MAX_PAYLOAD = 243
MAX_LINE = 360  # 4 prefix bytes + 356 base64 bytes
PREFIX = b"/m1 "


class FrameError(ValueError):
    pass


@dataclass(frozen=True)
class Frame:
    kind: Kind
    epoch: int
    request: int
    payload: bytes = b""


def encode(frame: Frame) -> bytes:
    if len(frame.payload) > MAX_PAYLOAD:
        raise FrameError("oversize machine payload")
    try:
        header = HEADER.pack(b"CM", 1, Kind(frame.kind), frame.epoch, frame.request, len(frame.payload))
    except (ValueError, struct.error) as exc:
        raise FrameError("invalid machine header") from exc
    body = header + frame.payload
    body += struct.pack("<I", zlib.crc32(body))
    return PREFIX + base64.b64encode(body) + b"\n"


def decode(line: bytes | str) -> Frame:
    if isinstance(line, str):
        try:
            line = line.encode("ascii")
        except UnicodeError as exc:
            raise FrameError("non-ASCII machine frame") from exc
    line = line.removesuffix(b"\n").removesuffix(b"\r")
    if len(line) > MAX_LINE or not line.startswith(PREFIX):
        raise FrameError("invalid machine line")
    try:
        body = base64.b64decode(line[len(PREFIX):], validate=True)
    except (ValueError, binascii.Error) as exc:
        raise FrameError("invalid machine base64") from exc
    if base64.b64encode(body) != line[len(PREFIX):] or len(body) < HEADER.size + 4:
        raise FrameError("noncanonical or truncated machine frame")
    magic, version, kind, epoch, request, length = HEADER.unpack_from(body)
    if magic != b"CM" or version != 1 or length > MAX_PAYLOAD or len(body) != HEADER.size + length + 4:
        raise FrameError("invalid machine header/length")
    if zlib.crc32(body[:-4]) != struct.unpack_from("<I", body, len(body) - 4)[0]:
        raise FrameError("machine checksum mismatch")
    try:
        return Frame(Kind(kind), epoch, request, body[HEADER.size:-4])
    except ValueError as exc:
        raise FrameError("unknown machine type") from exc


class Parser:
    """Bounded line parser; framing failures never enter the human USER path."""

    def __init__(self) -> None:
        self.buffer = bytearray()
        self.dropping = False
        self.errors = 0

    def feed(self, data: bytes) -> list[Frame]:
        frames = []
        for byte in data:
            if byte == 10:
                if self.buffer.startswith(PREFIX) and not self.dropping:
                    try:
                        frames.append(decode(bytes(self.buffer)))
                    except FrameError:
                        self.errors += 1
                self.buffer.clear()
                self.dropping = False
                continue
            if byte == 13:
                continue
            # Новый prefix восстанавливает границу после потерянного LF.
            self.buffer.append(byte)
            if self.buffer.endswith(PREFIX):
                if len(self.buffer) > len(PREFIX):
                    self.errors += 1
                self.buffer[:] = PREFIX
                self.dropping = False
            elif len(self.buffer) > MAX_LINE:
                if not self.dropping:
                    self.errors += 1
                self.dropping = True
                self.buffer[:] = self.buffer[-len(PREFIX):]
        return frames
