from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import threading
import time
from typing import Any

from ...file_transfer.transport import (
    BinarySendReceipt,
    BinaryUserCancelled,
    BinaryUserError,
)
from .binary_user import (
    BinaryUserParseError,
    ChatterBinaryUserAdapter,
    _REJECTION_MARKERS,
    _tx_id_from_result,
    encode_binary_command,
    parse_binary_tx_line,
)


CHATTER_BINARY_PIPELINE_CAPACITY = 2


@dataclass(frozen=True)
class ChatterBinarySubmission:
    payload: bytes
    binary_seq: int
    tx_id: int | None
    generation: int | None
    controller_epoch: int
    cursor: int
    deadline: float


class PipelinedChatterBinaryUserAdapter(ChatterBinaryUserAdapter):
    """Chatter BINARY adapter with an explicit bounded submit/settle pipeline.

    The inherited send_binary() contract stays synchronous and still settles on the
    exact local > [BINARY] presentation. FT1 may opt into submit_binary() /
    settle_binary() and keep at most two controller-local submissions outstanding.
    """

    pipeline_capacity = CHATTER_BINARY_PIPELINE_CAPACITY

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._pipeline_submit_lock = threading.Lock()
        self._pipeline_state_lock = threading.Lock()
        self._pipeline_pending: deque[ChatterBinarySubmission] = deque()
        self._pipeline_cursor_floor = 0

    def submit_binary(
        self,
        data: bytes,
        *,
        cancel_event: threading.Event | None = None,
    ) -> ChatterBinarySubmission:
        payload = bytes(data)
        command = encode_binary_command(payload)

        with self._pipeline_submit_lock:
            if cancel_event is not None and cancel_event.is_set():
                raise BinaryUserCancelled()

            with self._pipeline_state_lock:
                if len(self._pipeline_pending) >= self.pipeline_capacity:
                    raise BinaryUserError(
                        "binary_pipeline_full",
                        "Chatter BINARY pipeline capacity is exhausted",
                    )

            with self._condition:
                binary_seq = self._next_binary_timing_seq
                self._next_binary_timing_seq += 1

            tx_id: int | None = None
            generation = self._generation()
            try:
                generation = self._ensure_binary_presentation_available(
                    generation=generation,
                    cancel_event=cancel_event,
                )

                with self._condition:
                    cursor = self._next_seq - 1
                    controller_epoch = self._controller_epoch

                self._timing(
                    "binary_submit",
                    binary_seq=binary_seq,
                    payload_bytes=len(payload),
                    command_chars=len(command),
                    generation=generation,
                    controller_epoch=controller_epoch,
                    pipelined=True,
                )
                result = self._send_line(command)
                tx_id = _tx_id_from_result(result)
                self._timing(
                    "binary_tx_queued",
                    binary_seq=binary_seq,
                    tx_id=tx_id,
                    pipelined=True,
                )
                deadline = time.monotonic() + self._presentation_timeout_s
                self._wait_tx_written(
                    tx_id,
                    deadline,
                    cancel_event=cancel_event,
                )
                self._timing(
                    "binary_tx_written",
                    binary_seq=binary_seq,
                    tx_id=tx_id,
                    pipelined=True,
                )

                submission = ChatterBinarySubmission(
                    payload=payload,
                    binary_seq=binary_seq,
                    tx_id=tx_id,
                    generation=generation,
                    controller_epoch=controller_epoch,
                    cursor=cursor,
                    deadline=deadline,
                )
                with self._pipeline_state_lock:
                    self._pipeline_pending.append(submission)
                return submission
            except BinaryUserError as exc:
                self._timing(
                    "binary_error",
                    binary_seq=binary_seq,
                    tx_id=tx_id,
                    code=exc.code,
                    pipelined=True,
                )
                raise

    def settle_binary(
        self,
        submission: ChatterBinarySubmission,
        *,
        cancel_event: threading.Event | None = None,
    ) -> BinarySendReceipt:
        if not isinstance(submission, ChatterBinarySubmission):
            raise BinaryUserError(
                "binary_pipeline_ticket",
                "invalid Chatter BINARY pipeline submission token",
            )

        with self._pipeline_state_lock:
            if not self._pipeline_pending or self._pipeline_pending[0] is not submission:
                raise BinaryUserError(
                    "binary_pipeline_order",
                    "Chatter BINARY pipeline must settle submissions in order",
                )
            cursor = max(submission.cursor, self._pipeline_cursor_floor)

        generation_reader = self._connection_generation
        cancel_sent = False
        try:
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
                    if presented == submission.payload:
                        with self._pipeline_state_lock:
                            if (
                                not self._pipeline_pending
                                or self._pipeline_pending[0] is not submission
                            ):
                                raise BinaryUserError(
                                    "binary_pipeline_order",
                                    "Chatter BINARY pipeline settlement order changed",
                                )
                            self._pipeline_pending.popleft()
                            self._pipeline_cursor_floor = max(
                                self._pipeline_cursor_floor,
                                seq,
                            )
                        self._timing(
                            "binary_presentation_match",
                            binary_seq=submission.binary_seq,
                            tx_id=submission.tx_id,
                            line_chars=len(value),
                            pipelined=True,
                        )
                        self._timing(
                            "binary_return",
                            binary_seq=submission.binary_seq,
                            tx_id=submission.tx_id,
                            pipelined=True,
                        )
                        return BinarySendReceipt(tx_id=submission.tx_id)

                with self._condition:
                    reset_seen = self._controller_epoch != submission.controller_epoch
                if reset_seen:
                    self._wait_until_controller_ready(
                        generation=submission.generation,
                        cancel_event=cancel_event,
                        allow_reconnect_probe=True,
                    )
                    raise BinaryUserError(
                        "local_controller_reset",
                        (
                            "Chatter controller reset before exact pipelined BINARY "
                            "presentation became observable"
                        ),
                    )

                if (
                    generation_reader is not None
                    and submission.generation is not None
                    and generation_reader() != submission.generation
                ):
                    raise BinaryUserError(
                        "local_disconnect",
                        (
                            "local connection changed before exact pipelined Chatter "
                            "BINARY presentation became observable"
                        ),
                    )

                current_generation = self._generation()
                if (
                    self._known_output_mode_for_generation(current_generation)
                    == "TELEMETRY"
                ):
                    raise self._presentation_unavailable_error()

                remaining = submission.deadline - time.monotonic()
                if remaining <= 0:
                    raise BinaryUserError(
                        "binary_presentation_timeout",
                        (
                            "exact local Chatter BINARY presentation did not arrive "
                            "before pipeline timeout"
                        ),
                    )
                if not available:
                    with self._condition:
                        self._condition.wait(timeout=min(0.1, remaining))
        except BinaryUserError as exc:
            self._timing(
                "binary_error",
                binary_seq=submission.binary_seq,
                tx_id=submission.tx_id,
                code=exc.code,
                pipelined=True,
            )
            self.discard_binary_pipeline()
            raise

    def discard_binary_pipeline(self) -> None:
        # После ошибки DATA replay принадлежит FT1. Adapter только забывает
        # локальную correlation state, чтобы новый bounded pass начал с чистого окна.
        with self._condition:
            cursor = self._next_seq - 1
        with self._pipeline_state_lock:
            discarded = len(self._pipeline_pending)
            self._pipeline_pending.clear()
            self._pipeline_cursor_floor = max(self._pipeline_cursor_floor, cursor)
        if discarded:
            self._timing(
                "binary_pipeline_discard",
                discarded=discarded,
            )
