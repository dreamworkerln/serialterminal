from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import threading


CHATTER_TEXT_COMMANDS = frozenset(
    {
        "/help",
        "/id",
        "/chat",
        "/tele",
        "/both",
        "/echo",
        "/reboot",
    }
)

# Match the firmware's command-only boundary trim: ASCII C0/space plus DEL.
_COMMAND_TRIM_CHARS = "".join(chr(value) for value in range(0x21)) + "\x7f"

# Deliberately aligned with the current Chatter firmware INPUT_QUEUE_DEPTH.
# This is a host presentation safety bound, not a wire-protocol constant.
PENDING_PRESENTATION_LIMIT = 4

_SUCCESS_ECHO_PREFIX = "> [ECHO TX] "
_SUCCESS_USER_PREFIX = "> "
_EXACT_FAILURE_LINES = frozenset(
    {
        "[SYS] RADIO UNAVAILABLE, message not sent",
        "[ECHO] RADIO UNAVAILABLE",
        "[ECHO] REQUEST PENDING, message not sent",
    }
)
_FAILURE_PREFIXES = (
    "[SYS] INPUT TOO LONG:",
    "[SYS] RADIO FATAL ",
    "TX FRAME BUILD ERROR ",
    "TX FATAL state=",
)


def recognized_chatter_command(line: str) -> str | None:
    """Return the canonical local command if firmware-style trim recognizes it."""
    candidate = line.strip(_COMMAND_TRIM_CHARS)
    return candidate if candidate in CHATTER_TEXT_COMMANDS else None


@dataclass
class _PendingPresentation:
    text: str
    sent: bool = False


class PresentationTracker:
    """Track submitted payloads separately from the transport retry queue."""

    def __init__(self, limit: int = PENDING_PRESENTATION_LIMIT):
        if limit <= 0:
            raise ValueError("presentation limit must be positive")
        self._limit = limit
        self._pending: deque[_PendingPresentation] = deque()
        self._lock = threading.Lock()

    def submit_payload(self, text: str) -> bool:
        """Register a payload before transport queueing; false means do not hide it."""
        with self._lock:
            if len(self._pending) >= self._limit:
                return False
            self._pending.append(_PendingPresentation(text=text))
            return True

    def cancel_unsent_payload(self, text: str) -> None:
        """Remove the newest unsent matching payload if transport queueing failed."""
        with self._lock:
            for index in range(len(self._pending) - 1, -1, -1):
                pending = self._pending[index]
                if not pending.sent and pending.text == text:
                    del self._pending[index]
                    return

    def mark_sent(self, text: str) -> None:
        """Mark the first queued matching payload after the transport write succeeds."""
        with self._lock:
            for pending in self._pending:
                if not pending.sent and pending.text == text:
                    pending.sent = True
                    return

    @staticmethod
    def _success_payload_candidates(line: str) -> tuple[str, ...]:
        """Return possible payloads without assuming whether echo mode was active."""
        line = line.rstrip("\r\n")
        candidates: list[str] = []
        if line.startswith(_SUCCESS_ECHO_PREFIX):
            candidates.append(line[len(_SUCCESS_ECHO_PREFIX) :])
        if line.startswith(_SUCCESS_USER_PREFIX):
            candidates.append(line[len(_SUCCESS_USER_PREFIX) :])
        return tuple(candidates)

    @staticmethod
    def _is_failure_line(line: str) -> bool:
        line = line.rstrip("\r\n")
        if line in _EXACT_FAILURE_LINES:
            return True
        return any(line.startswith(prefix) for prefix in _FAILURE_PREFIXES)

    def consume_firmware_line(self, line: str) -> str | None:
        """Resolve one firmware line; return local text to reveal before a failure."""
        candidates = self._success_payload_candidates(line)
        if candidates:
            with self._lock:
                for candidate in candidates:
                    for index, pending in enumerate(self._pending):
                        if pending.sent and pending.text == candidate:
                            del self._pending[index]
                            return None
            return None

        if not self._is_failure_line(line):
            return None

        with self._lock:
            for index, pending in enumerate(self._pending):
                if pending.sent:
                    text = pending.text
                    del self._pending[index]
                    return text
        return None

    def consume_sent_on_disconnect(self) -> list[str]:
        """Reveal sent-but-unresolved submissions when their result channel is lost."""
        with self._lock:
            reveal = [pending.text for pending in self._pending if pending.sent]
            self._pending = deque(
                pending for pending in self._pending if not pending.sent
            )
            return reveal

    def pending_count(self) -> int:
        with self._lock:
            return len(self._pending)
