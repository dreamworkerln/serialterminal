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
from ...log_redaction import redact_base64_text


BINARY_USER_MAX_BYTES = 243
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
_OUTPUT_MODE_RE = re.compile(
    r"\[SYS\] OUTPUT (?P<mode>CHAT|TELEMETRY|BOTH)\b"
)
_CURRENT_MODE_RE = re.compile(
    r"\[SYS\]\s+current=(?P<mode>CHAT|TELEMETRY|BOTH)\b"
)
_OUTPUT_MODE_COMMANDS = {
    "CHAT": "/chat",
    "TELEMETRY": "/tele",
    "BOTH": "/both",
}

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
    """Chatter /bin + presentation/DELIVERY adapter for opaque raw bytes."""

    payload_capacity = BINARY_USER_MAX_BYTES

    def __init__(
        self,
        send_line: Callable[[str], Any],
        *,
        delivery_timeout_s: float = 3600.0,
        mode_switch_timeout_s: float = 5.0,
        line_retention: int = 4096,
        wait_tx_outcome: Callable[[int, float], str | None] | None = None,
        connection_generation: Callable[[], int] | None = None,
    ) -> None:
        if delivery_timeout_s <= 0:
            raise ValueError("delivery_timeout_s must be positive")
        if mode_switch_timeout_s <= 0:
            raise ValueError("mode_switch_timeout_s must be positive")
        self._send_line = send_line
        self._delivery_timeout_s = float(delivery_timeout_s)
        self._mode_switch_timeout_s = float(mode_switch_timeout_s)
        self._wait_tx_outcome = wait_tx_outcome
        self._connection_generation = connection_generation
        self._receiver: BinaryReceiver | None = None
        self._receiver_lock = threading.Lock()
        self._send_lock = threading.Lock()
        self._condition = threading.Condition()
        self._lines: deque[tuple[int, str]] = deque(maxlen=line_retention)
        self._next_seq = 1
        # Chatter firmware стартует в CHAT. Подтверждённые строки
        # [SYS] OUTPUT/current обновляют это значение при смене режима.
        self._output_mode = "CHAT"
        # Поколение неизвестно, пока controller не подтвердит режим на текущем
        # соединении: кешированный boot default не является подтверждением
        # после reconnect.
        self._output_mode_generation: int | None = None
        self._transfer_restore_mode: str | None = None
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
                # The profile adapter must never let application code kill the
                # ManagedSession RX notifier path.
                return

    def _lines_after(self, cursor: int) -> list[tuple[int, str]]:
        return [
            (seq, line)
            for seq, line in self._lines
            if seq > cursor
        ]

    def _set_output_mode_locked(self, mode: str) -> None:
        command = _OUTPUT_MODE_COMMANDS[mode]
        generation_reader = self._connection_generation
        target_generation = (
            generation_reader()
            if generation_reader is not None
            else None
        )
        with self._condition:
            if (
                self._output_mode == mode
                and (
                    generation_reader is None
                    or self._output_mode_generation == target_generation
                )
            ):
                return
            if self._output_mode == mode:
                # После reconnect кеш может помнить прежний режим, хотя
                # controller снова загрузился в CHAT. Перед BINARY USER нужна
                # свежая фиксация режима на текущем поколении соединения.
                self._output_mode_generation = None

        result = self._send_line(command)
        tx_id = _tx_id_from_result(result)
        deadline = time.monotonic() + self._mode_switch_timeout_s

        waiter = self._wait_tx_outcome
        if waiter is not None and tx_id is not None:
            remaining = max(0.0, deadline - time.monotonic())
            local_outcome = waiter(tx_id, remaining)
            if local_outcome is None:
                raise BinaryUserError(
                    "output_mode_tx_timeout",
                    f"Chatter {command} write did not settle before timeout",
                )
            if local_outcome in {"unknown", "expired"}:
                raise BinaryUserError(
                    "output_mode_tx_unknown",
                    f"Chatter {command} write outcome is ambiguous",
                )
            if local_outcome != "written":
                raise BinaryUserError(
                    "output_mode_tx_failed",
                    f"unexpected Chatter {command} TX outcome: {local_outcome}",
                )

        while True:
            with self._condition:
                if (
                    self._output_mode == mode
                    and (
                        generation_reader is None
                        or self._output_mode_generation == target_generation
                    )
                ):
                    return

                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise BinaryUserError(
                        "output_mode_timeout",
                        f"Chatter did not confirm output mode {mode}",
                    )
                self._condition.wait(timeout=min(0.25, remaining))

            if (
                generation_reader is not None
                and target_generation is not None
                and generation_reader() != target_generation
            ):
                raise BinaryUserError(
                    "local_disconnect",
                    "local connection changed during Chatter output-mode switch",
                )

    def _ensure_transfer_mode_locked(self) -> None:
        if self._transfer_restore_mode is not None:
            self._set_output_mode_locked("BOTH")

    def begin_transfer(self) -> None:
        with self._send_lock:
            if self._transfer_restore_mode is not None:
                raise BinaryUserError(
                    "transfer_mode_busy",
                    "binary file-transfer output-mode lease is already active",
                )
            with self._condition:
                restore_mode = self._output_mode
            self._transfer_restore_mode = restore_mode
            try:
                self._set_output_mode_locked("BOTH")
            except Exception:
                self._transfer_restore_mode = None
                raise

    def end_transfer(self) -> None:
        with self._send_lock:
            restore_mode = self._transfer_restore_mode
            if restore_mode is None:
                return
            try:
                if restore_mode != "BOTH":
                    self._set_output_mode_locked(restore_mode)
            finally:
                self._transfer_restore_mode = None

    def send_binary(
        self,
        data: bytes,
        *,
        cancel_event: threading.Event | None = None,
    ) -> BinaryDelivery:
        command = encode_binary_command(data)
        with self._send_lock:
            self._ensure_transfer_mode_locked()
            with self._condition:
                cursor = self._next_seq - 1

            result = self._send_line(command)
            tx_id = _tx_id_from_result(result)
            deadline = time.monotonic() + self._delivery_timeout_s

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

            generation_reader = self._connection_generation
            delivery_generation = (
                generation_reader()
                if generation_reader is not None
                else None
            )
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

                if (
                    generation_reader is not None
                    and delivery_generation is not None
                    and generation_reader() != delivery_generation
                ):
                    raise BinaryUserError(
                        "local_disconnect",
                        (
                            "local connection changed before BINARY USER "
                            "delivery settlement became observable"
                        ),
                    )

                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise BinaryUserError(
                        "delivery_timeout",
                        "BINARY USER delivery settlement timed out",
                    )
                if not available:
                    with self._condition:
                        self._condition.wait(timeout=min(0.25, remaining))
