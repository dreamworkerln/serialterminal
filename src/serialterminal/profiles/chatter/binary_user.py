from __future__ import annotations

import base64
from collections import deque
import re
import threading
import time
from typing import Any, Callable

from ...file_transfer.transport import (
    BinaryReceiver,
    BinarySendReceipt,
    BinaryUserCancelled,
    BinaryUserError,
)
from ...log_redaction import redact_base64_text


BINARY_USER_MAX_BYTES = 243
_BINARY_MARKER = " [BINARY] "

_OUTPUT_MODE_RE = re.compile(
    r"\[SYS\] OUTPUT (?P<mode>CHAT|TELEMETRY|BOTH)\b"
)
_CURRENT_MODE_RE = re.compile(
    r"\[SYS\]\s+current=(?P<mode>CHAT|TELEMETRY|BOTH)\b"
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
            f"BINARY presentation decoded outside 1..{BINARY_USER_MAX_BYTES} bytes"
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


def is_binary_presentation_line(line: str) -> bool:
    value = line.rstrip("\r\n")
    return value.startswith("> [BINARY] ") or (
        value.startswith("< [") and _BINARY_MARKER in value
    )


def redact_binary_human_text(text: str) -> str:
    return redact_base64_text(text)


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
    """Chatter /bin adapter with controller-local presentation settlement.

    DELIVERY telemetry is intentionally not part of the send state machine.
    Exact local > [BINARY] presentation is bounded backpressure after first
    physical TxDone; FT1 RESULT/MISSING owns remote application truth.
    """

    payload_capacity = BINARY_USER_MAX_BYTES

    def __init__(
        self,
        send_line: Callable[[str], Any],
        *,
        presentation_timeout_s: float = 3600.0,
        line_retention: int = 4096,
        wait_tx_outcome: Callable[[int, float], str | None] | None = None,
        connection_generation: Callable[[], int] | None = None,
    ) -> None:
        if presentation_timeout_s <= 0:
            raise ValueError("presentation_timeout_s must be positive")
        self._send_line = send_line
        self._presentation_timeout_s = float(presentation_timeout_s)
        self._wait_tx_outcome = wait_tx_outcome
        self._connection_generation = connection_generation
        self._receiver: BinaryReceiver | None = None
        self._receiver_lock = threading.Lock()
        self._send_lock = threading.Lock()
        self._condition = threading.Condition()
        self._lines: deque[tuple[int, str]] = deque(maxlen=line_retention)
        self._next_seq = 1
        self._output_mode: str | None = None
        self._output_mode_generation: int | None = None
        self.last_parse_error: str | None = None

    def set_receiver(self, receiver: BinaryReceiver | None) -> None:
        with self._receiver_lock:
            self._receiver = receiver

    def feed_line(self, stream: str, line: str) -> None:
        del stream
        value = line.rstrip("\r\n")
        mode_match = _OUTPUT_MODE_RE.search(value) or _CURRENT_MODE_RE.search(value)
        with self._condition:
            if mode_match is not None:
                self._output_mode = mode_match.group("mode")
                generation_reader = self._connection_generation
                self._output_mode_generation = (
                    generation_reader()
                    if generation_reader is not None
                    else None
                )
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
                # Profile adapter не должен позволять application callback
                # остановить общий ManagedSession RX notifier path.
                return

    def _lines_after(self, cursor: int) -> list[tuple[int, str]]:
        return [(seq, line) for seq, line in self._lines if seq > cursor]

    def _known_output_mode_for_generation(self, generation: int | None) -> str | None:
        with self._condition:
            if self._output_mode is None:
                return None
            if self._connection_generation is None:
                return self._output_mode
            if self._output_mode_generation != generation:
                return None
            return self._output_mode

    @staticmethod
    def _presentation_unavailable_error() -> BinaryUserError:
        return BinaryUserError(
            "binary_presentation_unavailable",
            (
                "Chatter BINARY presentation is unavailable in TELEMETRY-only "
                "human output mode; select CHAT or BOTH explicitly before FT1"
            ),
        )

    def send_binary(
        self,
        data: bytes,
        *,
        cancel_event: threading.Event | None = None,
    ) -> BinarySendReceipt:
        payload = bytes(data)
        command = encode_binary_command(payload)

        with self._send_lock:
            if cancel_event is not None and cancel_event.is_set():
                raise BinaryUserCancelled()

            generation_reader = self._connection_generation
            generation = (
                generation_reader()
                if generation_reader is not None
                else None
            )
            if self._known_output_mode_for_generation(generation) == "TELEMETRY":
                raise self._presentation_unavailable_error()

            with self._condition:
                cursor = self._next_seq - 1

            result = self._send_line(command)
            tx_id = _tx_id_from_result(result)
            deadline = time.monotonic() + self._presentation_timeout_s

            waiter = self._wait_tx_outcome
            if waiter is not None and tx_id is not None:
                remaining = max(0.0, deadline - time.monotonic())
                local_outcome = waiter(tx_id, remaining)
                if local_outcome is None:
                    raise BinaryUserError(
                        "local_tx_timeout",
                        "local BINARY USER write did not settle before timeout",
                    )
                if local_outcome in {"unknown", "expired"}:
                    raise BinaryUserError(
                        "local_tx_unknown",
                        "local BINARY USER write outcome is ambiguous",
                    )
                if local_outcome != "written":
                    raise BinaryUserError(
                        "local_tx_failed",
                        f"unexpected local TX outcome: {local_outcome}",
                    )

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

                for seq, line in available:
                    cursor = max(cursor, seq)
                    value = line.rstrip("\r\n")
                    if any(marker in value for marker in _REJECTION_MARKERS):
                        raise BinaryUserError(
                            "send_rejected",
                            f"Chatter rejected BINARY USER: {value}",
                        )
                    try:
                        presented = parse_binary_tx_line(line)
                    except BinaryUserParseError as exc:
                        self.last_parse_error = str(exc)
                        continue
                    if presented == payload:
                        return BinarySendReceipt(tx_id=tx_id)

                if (
                    generation_reader is not None
                    and generation is not None
                    and generation_reader() != generation
                ):
                    raise BinaryUserError(
                        "local_disconnect",
                        (
                            "local connection changed before exact Chatter "
                            "BINARY presentation became observable"
                        ),
                    )

                current_generation = (
                    generation_reader()
                    if generation_reader is not None
                    else None
                )
                if (
                    self._known_output_mode_for_generation(current_generation)
                    == "TELEMETRY"
                ):
                    raise self._presentation_unavailable_error()

                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise BinaryUserError(
                        "binary_presentation_timeout",
                        (
                            "exact local Chatter BINARY presentation did not "
                            "arrive before timeout"
                        ),
                    )
                if not available:
                    with self._condition:
                        # feed_line() будит condition сразу. Короткий timeout
                        # ограничивает только cancel/disconnect observation и
                        # не является per-message pacing delay.
                        self._condition.wait(timeout=min(0.25, remaining))
