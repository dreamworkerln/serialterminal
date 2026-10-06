from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any, Callable

from . import core
from .manager import FileTransferManager as _FileTransferManager
from .protocol import DataMessage, encode_message
from .transport import BinaryUserCancelled, BinaryUserError


FILE_DATA_PIPELINE_WINDOW = 2
_RECOVERABLE_PIPELINE_ERRORS = frozenset(
    {"local_tx_unknown", "local_disconnect", "local_controller_reset"}
)


@dataclass(frozen=True)
class _PendingData:
    chunk_index: int
    payload_bytes: int
    fields: dict[str, Any]
    ticket: Any


class FileTransferManager(_FileTransferManager):
    """Public FT1 manager with an optional bounded DATA submission pipeline."""

    def _data_pipeline(
        self,
    ) -> tuple[int, Callable[..., Any], Callable[..., Any]] | None:
        capacity = getattr(self.transport, "pipeline_capacity", 1)
        submit = getattr(self.transport, "submit_binary", None)
        settle = getattr(self.transport, "settle_binary", None)
        if (
            isinstance(capacity, bool)
            or not isinstance(capacity, int)
            or capacity < 2
            or not callable(submit)
            or not callable(settle)
        ):
            return None
        # Первый production шаг намеренно жёстко bounded двумя DATA. Даже если
        # transport позже объявит больше credit, FT1 не расширяет окно молча.
        return min(FILE_DATA_PIPELINE_WINDOW, capacity), submit, settle

    def _discard_data_pipeline(self) -> None:
        discard = getattr(self.transport, "discard_binary_pipeline", None)
        if callable(discard):
            discard()

    def _pipeline_fallback(
        self,
        record,
        prepared,
        *,
        chunk_size: int,
        replay_index: int,
        reason: str,
        outstanding: int,
    ) -> None:
        self._discard_data_pipeline()
        record.event(
            "binary_pipeline_fallback",
            reason=reason,
            next_chunk=replay_index,
            outstanding=outstanding,
        )
        # DATA имеет stable (transfer_id, chunk_index), поэтому после ambiguous
        # local outcome безопаснее повторить earliest outstanding chunk, чем
        # угадывать, какой из двух controller уже принял. Receiver дедуплицирует.
        super()._send_chunks_from(
            record,
            prepared,
            chunk_size,
            replay_index,
        )

    def _send_chunks_from(self, record, prepared, chunk_size: int, start: int) -> None:
        pipeline = self._data_pipeline()
        if pipeline is None:
            super()._send_chunks_from(record, prepared, chunk_size, start)
            return
        if not 0 <= start <= record.chunks_total:
            raise core.FileTransferError(
                "invalid_resume_request",
                "resume cursor outside prepared stream",
            )

        window, submit, settle = pipeline
        settled_bytes = min(prepared.wire_size, start * chunk_size)
        record.set_progress(bytes_completed=settled_bytes, chunks_completed=start)
        record.event(
            "binary_pipeline_enabled",
            window=window,
            next_chunk=start,
        )

        pending: deque[_PendingData] = deque()
        next_index = start
        with prepared.wire_path.open("rb") as source:
            source.seek(start * chunk_size)
            while next_index < record.chunks_total or pending:
                while next_index < record.chunks_total and len(pending) < window:
                    if record.cancel_event.is_set():
                        self._discard_data_pipeline()
                        raise core.FileTransferCancelled()
                    block = source.read(chunk_size)
                    if not block:
                        self._discard_data_pipeline()
                        raise core.FileTransferError(
                            "local_failure",
                            "prepared wire stream ended early",
                        )

                    message = DataMessage(record.transfer_id, next_index, block)
                    payload = encode_message(message, self.transport.payload_capacity)
                    fields = self._message_event_fields(message)
                    record.event("binary_send_start", **fields)
                    try:
                        ticket = submit(
                            payload,
                            cancel_event=record.cancel_event,
                        )
                    except BinaryUserCancelled as exc:
                        self._discard_data_pipeline()
                        raise core.FileTransferCancelled(str(exc)) from exc
                    except BinaryUserError as exc:
                        if exc.code in _RECOVERABLE_PIPELINE_ERRORS:
                            replay_index = (
                                pending[0].chunk_index if pending else next_index
                            )
                            self._pipeline_fallback(
                                record,
                                prepared,
                                chunk_size=chunk_size,
                                replay_index=replay_index,
                                reason=exc.code,
                                outstanding=len(pending),
                            )
                            return
                        self._discard_data_pipeline()
                        self._raise_binary_failure(record, fields, exc, 0)

                    pending.append(
                        _PendingData(
                            chunk_index=next_index,
                            payload_bytes=len(block),
                            fields=fields,
                            ticket=ticket,
                        )
                    )
                    next_index += 1

                current = pending[0]
                try:
                    settle(
                        current.ticket,
                        cancel_event=record.cancel_event,
                    )
                except BinaryUserCancelled as exc:
                    self._discard_data_pipeline()
                    raise core.FileTransferCancelled(str(exc)) from exc
                except BinaryUserError as exc:
                    if exc.code in _RECOVERABLE_PIPELINE_ERRORS:
                        self._pipeline_fallback(
                            record,
                            prepared,
                            chunk_size=chunk_size,
                            replay_index=current.chunk_index,
                            reason=exc.code,
                            outstanding=len(pending),
                        )
                        return
                    self._discard_data_pipeline()
                    self._raise_binary_failure(record, current.fields, exc, 0)

                pending.popleft()
                settled_bytes += current.payload_bytes
                record.event(
                    "binary_send_settled",
                    **current.fields,
                    local_replays=0,
                    pipeline_window=window,
                )
                record.set_progress(
                    bytes_completed=settled_bytes,
                    chunks_completed=current.chunk_index + 1,
                )
