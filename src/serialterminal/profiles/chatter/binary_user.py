from __future__ import annotations

import base64
from collections import deque
import re
import threading
import time
from typing import Any, Callable

from ...file_transfer.transport import (
    BinaryDelivery,
    BinaryReceiver,
    BinaryUserCancelled,
    BinaryUserError,
)


BINARY_USER_MAX_BYTES = 200
_BINARY_MARKER = " [BINARY] "

_WAIT_ACK_RE = re.compile(
    r"DELIVERY WAIT_ACK user=(?P<user>[0-9A-Fa-f]+/\d+)"
)
_ACK_RE = re.compile(
    r"DELIVERY ACK user=(?P<user>[0-9A-Fa-f]+/\d+)"
)
_FAILED_RE = re.compile(
    r"DELIVERY FAILED user=(?P<user>[0-9A-Fa-f]+/\d+)"
)
_CANCEL_RE = re.compile(
    r"DELIVERY CANCEL(?:LED)? user=(?P<user>[0-9A-Fa-f]+/\d+)"
)
_REJECTION_MARKERS = (
    "[SYS] INPUT TOO LONG",
    "[SYS] SEND QUEUE FULL",
    "[SYS] RADIO UNAVAILABLE",
    "[SYS] BINARY ",
    "TX FATAL ",
    "TX FRAME BUILD ERROR ",
)


class BinaryUserParseError(ValueError):
    pass


def encode_binary_command(data: bytes) -> str:
    payload = bytes(data)
    if not 1 <= len(payload) <= BINARY_USER_MAX_BYTES:
        raise ValueError(
            f"BINARY USER payload must be 1..{BINARY_USER_MAX_BYTES} bytes"
        )
    encoded = base64.b64encode(payload).decode("ascii")
    return f"/bin {encoded}"


def _decode_binary_base64(encoded: str) -> bytes:
    if not encoded:
        raise BinaryUserParseError("BINARY presentation has empty base64 payload")
    try:
        payload = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise BinaryUserParseError(
            "BINARY presentation contains invalid base64"
        ) from exc
    if not 1 <= len(payload) <= BINARY_USER_MAX_BYTES:
        raise BinaryUserParseError(
            "BINARY presentation decoded outside 1..200 bytes"
        )
    return payload


def parse_binary_rx_line(line: str) -> bytes | None:
    value = line.rstrip("\r\n")
    if not value.startswith("< ") or _BINARY_MARKER not in value:
        return None
    prefix, encoded = value.rsplit(_BINARY_MARKER, 1)
    if not prefix.startswith("< [") or not prefix.endswith("]"):
        return None
    return _decode_binary_base64(encoded)


def parse_binary_tx_line(line: str) -> bytes | None:
    value = line.rstrip("\r\n")
    prefix = "> [BINARY] "
    if not value.startswith(prefix):
        return None
    return _decode_binary_base64(value[len(prefix) :])


def _tx_id_from_result(result: Any) -> int | None:
    if isinstance(result, bool):
        return None
    if isinstance(result, int):
        return result
    if isinstance(result, dict):
        tx_id = result.get("tx_id")
        if isinstance(tx_id, int) and not isinstance(tx_id, bool):
            return tx_id
    return None


class ChatterBinaryUserAdapter:
    """Chatter /bin + presentation/DELIVERY adapter for opaque raw bytes."""

    payload_capacity = BINARY_USER_MAX_BYTES

    def __init__(
        self,
        send_line: Callable[[str], Any],
        *,
        delivery_timeout_s: float = 3600.0,
        line_retention: int = 4096,
    ) -> None:
        if delivery_timeout_s <= 0:
            raise ValueError("delivery_timeout_s must be positive")
        self._send_line = send_line
        self._delivery_timeout_s = float(delivery_timeout_s)
        self._receiver: BinaryReceiver | None = None
        self._receiver_lock = threading.Lock()
        self._send_lock = threading.Lock()
        self._condition = threading.Condition()
        self._lines: deque[tuple[int, str]] = deque(maxlen=line_retention)
        self._next_seq = 1
        self.last_parse_error: str | None = None

    def set_receiver(self, receiver: BinaryReceiver | None) -> None:
        with self._receiver_lock:
            self._receiver = receiver

    def feed_line(self, stream: str, line: str) -> None:
        del stream
        with self._condition:
            seq = self._next_seq
            self._next_seq += 1
            self._lines.append((seq, line))
            self._condition.notify_all()

        try:
            payload = parse_binary_rx_line(line)
        except BinaryUserParseError as exc:
            self.last_parse_error = str(exc)
            return
        if payload is None:
            return
        with self._receiver_lock:
            receiver = self._receiver
        if receiver is not None:
            try:
                receiver(payload)
            except Exception:
                # The profile adapter must never let application code kill the
                # ManagedSession RX notifier path.
                return

    def _lines_after(self, cursor: int) -> list[tuple[int, str]]:
        return [
            (seq, line)
            for seq, line in self._lines
            if seq > cursor
        ]

    def send_binary(
        self,
        data: bytes,
        *,
        cancel_event: threading.Event | None = None,
    ) -> BinaryDelivery:
        command = encode_binary_command(data)
        with self._send_lock:
            with self._condition:
                cursor = self._next_seq - 1

            result = self._send_line(command)
            tx_id = _tx_id_from_result(result)
            deadline = time.monotonic() + self._delivery_timeout_s
            user_id: str | None = None
            cancel_sent = False

            while True:
                if cancel_event is not None and cancel_event.is_set():
                    if not cancel_sent:
                        try:
                            self._send_line("/cancel all")
                        except Exception:
                            pass
                        cancel_sent = True
                    raise BinaryUserCancelled()

                with self._condition:
                    available = self._lines_after(cursor)
                    if not available:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise BinaryUserError(
                                "delivery_timeout",
                                "BINARY USER delivery settlement timed out",
                            )
                        self._condition.wait(timeout=min(0.25, remaining))
                        continue

                for seq, line in available:
                    cursor = max(cursor, seq)
                    value = line.rstrip("\r\n")
                    if any(marker in value for marker in _REJECTION_MARKERS):
                        raise BinaryUserError(
                            "send_rejected",
                            f"Chatter rejected BINARY USER: {value}",
                        )

                    wait_match = _WAIT_ACK_RE.search(value)
                    if wait_match is not None and user_id is None:
                        user_id = wait_match.group("user")
                        continue

                    if user_id is None:
                        continue

                    ack = _ACK_RE.search(value)
                    if ack is not None and ack.group("user") == user_id:
                        return BinaryDelivery(tx_id=tx_id, user_id=user_id)

                    failed = _FAILED_RE.search(value)
                    if failed is not None and failed.group("user") == user_id:
                        raise BinaryUserError(
                            "link_failed",
                            f"BINARY USER delivery failed: {user_id}",
                        )

                    cancelled = _CANCEL_RE.search(value)
                    if cancelled is not None and cancelled.group("user") == user_id:
                        raise BinaryUserCancelled(
                            f"BINARY USER delivery cancelled: {user_id}"
                        )
