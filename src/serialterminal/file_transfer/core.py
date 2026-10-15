from __future__ import annotations

from contextlib import contextmanager
from collections import deque
from dataclasses import dataclass
import gzip
import hashlib
import math
import os
from pathlib import Path
import queue
import secrets
import tempfile
import threading
import time
from typing import Any, Callable

from .outbox import Outbox, OutboxError

from .protocol import (
    Compression,
    DataMessage,
    EndMessage,
    FileMessage,
    FileProtocolError,
    MetaMessage,
    MissingMessage,
    ResultMessage,
    canonical_missing_ranges,
    checked_chunk_count,
    data_payload_capacity,
    decode_message,
    encode_message,
    validate_missing_ranges,
    parse_transfer_id,
    transfer_id_text,
)
from .transport import (
    BinaryUserCancelled,
    BinaryUserError,
    BinaryUserTransport,
)


FILE_EVENT_RETENTION = 1024
FILE_MAX_WINDOW = 100
FILE_MAX_RETAINED_TERMINAL = 16
FILE_RESULT_TIMEOUT_S = None
FILE_LOCAL_TX_DRAIN_TIMEOUT_S = 10.0
FILE_CONTROL_REPLAY_INTERVAL_S = 30.0
FILE_MAX_CONTROL_REPLAYS = 3
FILE_MAX_REPAIR_ROUNDS = 8
FILE_MAX_LOCAL_MESSAGE_REPLAYS = 4
FILE_INCOMING_IDLE_TIMEOUT_S = 120.0
FILE_RX_IDLE_SWEEP_S = 1.0
FILE_RX_QUEUE_CAPACITY = 256
FILE_CONTROL_QUEUE_CAPACITY = 16
_IO_CHUNK = 256 * 1024

_TERMINAL_STATES = frozenset({"completed", "failed", "cancelled"})


class _SubmissionStop:
    """Сигнал остановки FT1 wait без изменения operator cancel state."""

    def __init__(self, record, cancel_event):
        self.record = record
        self.cancel_event = cancel_event

    def is_set(self) -> bool:
        return (
            self.record.remote_failure_event.is_set()
            or (self.cancel_event is not None and self.cancel_event.is_set())
        )

    def wait(self, timeout: float | None = None) -> bool:
        deadline = None if timeout is None else time.monotonic() + timeout
        with self.record._condition:
            while not self.is_set():
                remaining = None if deadline is None else deadline - time.monotonic()
                if remaining is not None and remaining <= 0:
                    return False
                # Remote RESULT уведомляет condition сразу; внешний Event может
                # не уведомлять её, поэтому проверка operator cancel ограничена.
                self.record._condition.wait(
                    timeout=0.05 if remaining is None else min(0.05, remaining)
                )
            return True


class FileTransferError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        phase: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.phase = phase
        self.details = details or {}


class FileTransferCancelled(FileTransferError):
    def __init__(self, message: str = "file transfer cancelled"):
        super().__init__("cancelled", message)


@dataclass
class _PreparedSource:
    source_path: Path
    wire_path: Path
    remove_wire_path: bool
    filename: str
    original_size: int
    wire_size: int
    compression: Compression
    original_sha256: bytes
    wire_sha256: bytes


@dataclass
class _IncomingState:
    meta: MetaMessage
    record: "_TransferRecord"
    wire_path: Path
    received: dict[int, int]
    last_activity_monotonic: float


@dataclass(frozen=True)
class _CancelIncoming:
    transfer_id: int


@dataclass(frozen=True)
class _OutboundFailure:
    transfer_id: int
    error: Exception


def default_receive_dir() -> Path:
    source_root = Path(__file__).resolve().parents[3]
    if (source_root / "pyproject.toml").is_file():
        return source_root / "files"
    return Path.cwd() / "files"


def safe_received_filename(filename: str) -> str:
    """Validate a remote filename as a basename, never as a filesystem path."""
    if not isinstance(filename, str) or not filename:
        raise FileTransferError(
            "invalid_metadata",
            "received filename is empty",
            phase="receiving",
        )
    if filename in {".", ".."}:
        raise FileTransferError(
            "invalid_metadata",
            "received filename is not a valid basename",
            phase="receiving",
        )
    if any(character in filename for character in ("/", "\\", "\x00", ":")):
        raise FileTransferError(
            "invalid_metadata",
            "received filename contains path syntax",
            phase="receiving",
        )
    if any(ord(character) < 32 or ord(character) == 127 for character in filename):
        raise FileTransferError(
            "invalid_metadata",
            "received filename contains control characters",
            phase="receiving",
        )
    if Path(filename).is_absolute() or Path(filename).name != filename:
        raise FileTransferError(
            "invalid_metadata",
            "received filename escapes receive directory",
            phase="receiving",
        )
    return filename


def _sha256_file(
    path: Path,
    cancel_event: threading.Event | None = None,
) -> bytes:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while True:
            if cancel_event is not None and cancel_event.is_set():
                raise FileTransferCancelled()
            block = source.read(_IO_CHUNK)
            if not block:
                break
            digest.update(block)
    return digest.digest()


def _unique_destination(directory: Path, filename: str, *, reserved: set[Path] | None = None) -> Path:
    def occupied(path: Path) -> bool:
        return path.exists() or path.is_symlink() or (reserved is not None and path.parent.resolve() / path.name in reserved)

    candidate = directory / filename
    if not occupied(candidate):
        return candidate
    stem = candidate.stem
    suffix = candidate.suffix
    for index in range(1, 10000):
        alternate = directory / f"{stem} ({index}){suffix}"
        if not occupied(alternate):
            return alternate
    raise FileTransferError(
        "storage_failed",
        "could not choose a unique destination filename",
        phase="verifying",
    )


class _TransferRecord:
    def __init__(
        self,
        transfer_id: int,
        *,
        direction: str,
        filename: str,
        event_retention: int,
        event_sink: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.transfer_id = transfer_id
        self.direction = direction
        self.filename = filename
        self.state = "preparing" if direction == "TX" else "receiving"
        self.original_bytes = 0
        self.wire_bytes = 0
        self.chunks_total = 0
        self.chunks_completed = 0
        self.bytes_completed = 0
        self.failure: dict[str, Any] | None = None
        self.final_path: str | None = None
        self.cancel_event = threading.Event()
        self.remote_result: ResultMessage | None = None
        self.remote_failure_event = threading.Event()
        self.remote_missing: deque[MissingMessage] = deque()
        self.rx_meta: MetaMessage | None = None
        self.rx_end: EndMessage | None = None
        self.started_monotonic = time.monotonic()
        self.ended_monotonic: float | None = None
        self._condition = threading.Condition()
        self._events: deque[dict[str, Any]] = deque(maxlen=event_retention)
        self._next_event_seq = 1
        self._thread: threading.Thread | None = None
        self._event_sink = event_sink

    def _percentage_locked(self) -> float:
        if self.state == "completed":
            return 100.0
        if self.wire_bytes > 0:
            # 100% is reserved for remote verified completion. Sending or
            # receiving every DATA byte still leaves END/RESULT verification.
            return min(99.9, 100.0 * self.bytes_completed / self.wire_bytes)
        if self.original_bytes > 0 and self.state == "compressing":
            return min(99.9, 100.0 * self.bytes_completed / self.original_bytes)
        return 0.0

    def _snapshot_locked(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "transfer_id": transfer_id_text(self.transfer_id),
            "direction": self.direction,
            "filename": self.filename,
            "state": self.state,
            "original_bytes": self.original_bytes,
            "wire_bytes": self.wire_bytes,
            "chunks_total": self.chunks_total,
            "chunks_completed": self.chunks_completed,
            "bytes_completed": self.bytes_completed,
            "percentage": round(self._percentage_locked(), 2),
        }
        if hasattr(self, "repair_progress"):
            result["repair"] = dict(self.repair_progress)
        if self.failure is not None:
            result["failure"] = dict(self.failure)
        if self.final_path is not None:
            result["final_path"] = self.final_path
        end = self.ended_monotonic
        if end is not None:
            result["elapsed"] = round(end - self.started_monotonic, 3)
        return result

    def snapshot(self) -> dict[str, Any]:
        with self._condition:
            return self._snapshot_locked()

    def event(self, kind: str, **fields: Any) -> dict[str, Any]:
        with self._condition:
            event = {
                "seq": self._next_event_seq,
                "kind": kind,
                "timestamp": time.time(),
                **fields,
            }
            self._next_event_seq += 1
            self._events.append(event)
            self._condition.notify_all()

        sink = self._event_sink
        if sink is not None:
            envelope = {
                "transfer_id": transfer_id_text(self.transfer_id),
                "direction": self.direction,
                "filename": self.filename,
                **event,
            }
            try:
                sink(envelope)
            except Exception:
                # Forensic logging не является частью FT1 correctness path.
                pass
        return event

    def set_state(self, state: str) -> None:
        with self._condition:
            if self.state in _TERMINAL_STATES:
                return
            self.state = state
            self._condition.notify_all()
        self.event("state", state=state)

    def set_sizes(
        self,
        *,
        original_bytes: int,
        wire_bytes: int,
        chunks_total: int,
    ) -> None:
        with self._condition:
            self.original_bytes = original_bytes
            self.wire_bytes = wire_bytes
            self.chunks_total = chunks_total
            self.bytes_completed = 0
            self.chunks_completed = 0
            self._condition.notify_all()
        self.event("progress", progress=self.snapshot())

    def set_progress(self, *, bytes_completed: int, chunks_completed: int) -> None:
        with self._condition:
            self.bytes_completed = bytes_completed
            self.chunks_completed = chunks_completed
            self._condition.notify_all()
        self.event("progress", progress=self.snapshot())

    def terminal(
        self,
        state: str,
        *,
        failure: FileTransferError | None = None,
        final_path: Path | None = None,
    ) -> None:
        if state not in _TERMINAL_STATES:
            raise ValueError(f"invalid terminal file-transfer state: {state}")
        with self._condition:
            if self.state in _TERMINAL_STATES:
                return
            self.state = state
            self.ended_monotonic = time.monotonic()
            if state == "completed":
                self.bytes_completed = self.wire_bytes
                self.chunks_completed = self.chunks_total
            if failure is not None:
                details: dict[str, Any] = {
                    "code": failure.code,
                    "message": failure.message,
                }
                if failure.phase is not None:
                    details["phase"] = failure.phase
                if failure.details:
                    details["details"] = dict(failure.details)
                self.failure = details
            if final_path is not None:
                self.final_path = str(final_path)
            snapshot = self._snapshot_locked()
            self._condition.notify_all()
        self.event("transfer_" + state, progress=snapshot)

    def set_remote_result(self, result: ResultMessage) -> None:
        with self._condition:
            if self.remote_result is not None:
                return
            self.remote_result = result
            if not result.ok:
                self.remote_failure_event.set()
            self._condition.notify_all()
        self.event(
            "remote_result",
            ok=result.ok,
            code=result.code,
            reason=result.reason,
        )

    def set_remote_missing(self, message: MissingMessage) -> None:
        with self._condition:
            if len(self.remote_missing) >= FILE_CONTROL_QUEUE_CAPACITY:
                self.control_overflow = True
                self.remote_failure_event.set()
                self._condition.notify_all()
                self.event("control_queue_overflow")
                return
            self.remote_missing.append(message)
            self._condition.notify_all()
        self.event(
            "missing_detected",
            ranges=len(message.ranges),
            chunks=sum(item.count for item in message.ranges),
        )

    def observe(
        self,
        *,
        cursor: int,
        window: int,
        timeout_ms: int,
    ) -> dict[str, Any]:
        if isinstance(cursor, bool) or not isinstance(cursor, int) or cursor < 0:
            raise FileTransferError(
                "invalid_file_cursor",
                "cursor must be a non-negative integer",
            )
        if isinstance(window, bool) or not isinstance(window, int) or window <= 0:
            raise FileTransferError(
                "invalid_file_window",
                "window must be a positive integer",
            )
        if (
            isinstance(timeout_ms, bool)
            or not isinstance(timeout_ms, int)
            or timeout_ms < 0
        ):
            raise FileTransferError(
                "invalid_timeout",
                "timeout_ms must be a non-negative integer",
            )

        deadline = time.monotonic() + timeout_ms / 1000.0
        with self._condition:
            while True:
                head = self._next_event_seq - 1
                if cursor > head:
                    raise FileTransferError(
                        "invalid_file_cursor",
                        "cursor is newer than current transfer event head",
                        details={"requested_cursor": cursor, "head_cursor": head},
                    )
                if self._events:
                    oldest = self._events[0]["seq"]
                    oldest_valid = oldest - 1
                else:
                    oldest = self._next_event_seq
                    oldest_valid = head
                if cursor < oldest_valid:
                    raise FileTransferError(
                        "file_cursor_expired",
                        "requested transfer cursor is older than retained history",
                        details={
                            "requested_cursor": cursor,
                            "oldest_valid_cursor": oldest_valid,
                            "oldest_retained_event_seq": oldest,
                            "head_cursor": head,
                        },
                    )

                available = [event for event in self._events if event["seq"] > cursor]
                if available or self.state in _TERMINAL_STATES or timeout_ms == 0:
                    selected = available[: min(window, FILE_MAX_WINDOW)]
                    response_cursor = selected[-1]["seq"] if selected else cursor
                    return {
                        "events": [dict(event) for event in selected],
                        "cursor": response_cursor,
                        "head_cursor": head,
                        "state": self.state,
                        "progress": self._snapshot_locked(),
                        "timed_out": False,
                    }

                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return {
                        "events": [],
                        "cursor": cursor,
                        "head_cursor": head,
                        "state": self.state,
                        "progress": self._snapshot_locked(),
                        "timed_out": True,
                    }
                self._condition.wait(timeout=remaining)


class FileTransferManager:
    """One-session FT1 sender/receiver over an opaque BINARY application transport."""

    def __init__(
        self,
        transport: BinaryUserTransport,
        *,
        receive_dir: str | Path | None = None,
        claim_transfer: Callable[[int, str], None] | None = None,
        release_transfer: Callable[[int, str], None] | None = None,
        id_factory: Callable[[], int] | None = None,
        event_retention: int = FILE_EVENT_RETENTION,
        max_retained_terminal: int = FILE_MAX_RETAINED_TERMINAL,
        result_timeout_s: float | None = None,
        control_replay_interval_s: float | None = None,
        max_control_replays: int = FILE_MAX_CONTROL_REPLAYS,
        max_repair_rounds: int = FILE_MAX_REPAIR_ROUNDS,
        max_local_message_replays: int = FILE_MAX_LOCAL_MESSAGE_REPLAYS,
        incoming_idle_timeout_s: float | None = None,
        event_sink: Callable[[dict[str, Any]], None] | None = None,
        _defer_start: bool = False,
    ) -> None:
        self.transport = transport
        self.receive_dir = (
            default_receive_dir()
            if receive_dir is None
            else Path(receive_dir).expanduser()
        )
        self.claim_transfer = claim_transfer
        self.release_transfer = release_transfer
        self.id_factory = id_factory or (lambda: secrets.randbits(64))
        self.event_retention = event_retention
        self.max_retained_terminal = max_retained_terminal
        if result_timeout_s is not None and (not math.isfinite(result_timeout_s) or result_timeout_s <= 0):
            raise ValueError("result_timeout_s must be positive")
        if control_replay_interval_s is not None and (not math.isfinite(control_replay_interval_s) or control_replay_interval_s <= 0):
            raise ValueError("control_replay_interval_s must be positive")
        if max_control_replays < 0:
            raise ValueError("max_control_replays must be non-negative")
        if max_repair_rounds <= 0:
            raise ValueError("max_repair_rounds must be positive")
        if max_local_message_replays < 0:
            raise ValueError("max_local_message_replays must be non-negative")
        if incoming_idle_timeout_s is not None and (not math.isfinite(incoming_idle_timeout_s) or incoming_idle_timeout_s <= 0):
            raise ValueError("incoming_idle_timeout_s must be positive")
        self.result_timeout_s = None if result_timeout_s is None else float(result_timeout_s)
        self.control_replay_interval_s = None if control_replay_interval_s is None else float(control_replay_interval_s)
        self.max_control_replays = int(max_control_replays)
        self.max_repair_rounds = int(max_repair_rounds)
        self.max_local_message_replays = int(max_local_message_replays)
        self.incoming_idle_timeout_s = None if incoming_idle_timeout_s is None else float(incoming_idle_timeout_s)
        self.event_sink = event_sink

        # Рекурсивный admission сохраняет ROOT lease под тем же lock, пока
        # существующая RX policy резервирует дочерний контекст.
        self._lock = threading.RLock()
        self._control_admission = threading.local()
        self._records: dict[int, _TransferRecord] = {}
        self._terminal_order: deque[int] = deque()
        self._active_id: int | None = None
        self._incoming: _IncomingState | None = None
        self._rx_queue: queue.Queue = queue.Queue(maxsize=FILE_RX_QUEUE_CAPACITY)
        self._rx_overflow = threading.Event()
        self._outbox = Outbox()
        self._stopping = threading.Event()
        self._rx_thread = threading.Thread(
            target=self._rx_loop,
            name=f"serialterminal-file-rx-{id(self):x}",
            daemon=True,
        )
        self._runtime_started = False
        if not _defer_start:
            self._start_workers()

    @contextmanager
    def _control_admission_scope(self):
        with self._lock:
            previous = getattr(self._control_admission, "depth", 0)
            self._control_admission.depth = previous + 1
            try:
                yield
            finally:
                self._control_admission.depth = previous

    def _timing_budget_s(self, purpose: str, override: float | None = None) -> float:
        if override is not None:
            return override
        provider = getattr(self.transport, "timing_budget_s", None)
        if callable(provider):
            try:
                value = float(provider(purpose))
            except BinaryUserError as exc:
                raise FileTransferError(exc.code, str(exc), phase="timing") from exc
            if not math.isfinite(value) or value <= 0:
                raise FileTransferError("invalid_timing_budget", "transport timing budget must be finite and positive", phase="timing")
            return value
        # У opaque transports без timing capability остаётся прикладная policy.
        # Это не оценка радио: физический profile обязан предоставить свои бюджеты.
        return {"control": FILE_CONTROL_REPLAY_INTERVAL_S, "resume": 1.0,
                "drain": FILE_LOCAL_TX_DRAIN_TIMEOUT_S}[purpose]

    def _incoming_idle_budget_s(self) -> float:
        if self.incoming_idle_timeout_s is not None:
            return self.incoming_idle_timeout_s
        if not callable(getattr(self.transport, "timing_budget_s", None)):
            return FILE_INCOMING_IDLE_TIMEOUT_S
        # Receiver ждёт весь bounded цикл META/END replay отправителя; один
        # интервал нельзя считать исчезновением peer, пока тот ещё ждёт ответ.
        return ((self.max_control_replays + 1) * self._timing_budget_s("control", self.control_replay_interval_s)
                + self._timing_budget_s("drain"))

    def _start_workers(self) -> None:
        # Receiver может синхронно доставить META при регистрации: все storage
        # policies должны быть готовы до callback и запуска RX/controller worker.
        with self._lock:
            if self._runtime_started:
                return
            self._runtime_started = True
        self.transport.set_receiver(self.feed_binary)
        self._rx_thread.start()
        initialize = getattr(self.transport, "start", None)
        if callable(initialize):
            initialize()

    @property
    def payload_capacity(self) -> int:
        return self.transport.payload_capacity

    def _new_transfer_id_locked(self) -> int:
        for _ in range(100):
            transfer_id = int(self.id_factory()) & 0xFFFFFFFFFFFFFFFF
            if transfer_id != 0 and transfer_id not in self._records:
                return transfer_id
        raise FileTransferError(
            "transfer_id_exhausted",
            "could not allocate a unique transfer id",
        )

    def _claim(self, transfer_id: int, direction: str) -> None:
        callback = self.claim_transfer
        if callback is not None:
            callback(transfer_id, direction)

    def _release(self, transfer_id: int, direction: str) -> None:
        callback = self.release_transfer
        if callback is not None:
            callback(transfer_id, direction)

    def _restart_record(self, record: _TransferRecord, state: str) -> None:
        # История и cursor сохраняются, terminal outcome относится к попытке.
        # Новая попытка не наследует RESULT/cancel/repair предыдущей.
        with record._condition:
            record.failure = None
            record.final_path = None
            record.ended_monotonic = None
            record.started_monotonic = time.monotonic()
            record.cancel_event.clear()
            record.remote_result = None
            record.remote_failure_event.clear()
            record.remote_missing.clear()
            record.control_overflow = False
            record.remote_resume = None
            record.state = state
            record._condition.notify_all()

    def _reserve_record(
        self,
        transfer_id: int,
        *,
        direction: str,
        filename: str,
        resume_existing: _TransferRecord | None = None,
    ) -> _TransferRecord:
        with self._lock:
            if self._stopping.is_set():
                raise FileTransferError("local_shutdown", "file transfer manager is closed")
            if self._active_id is not None:
                raise FileTransferError(
                    "file_transfer_busy",
                    "another file transfer is active on this session",
                    details={"active_transfer_id": transfer_id_text(self._active_id)},
                )
            existing = self._records.get(transfer_id)
            if existing is not None:
                if existing is not resume_existing or existing.direction != "TX" or existing.state != "failed":
                    raise FileTransferError("duplicate_transfer_id", "transfer id already exists")
                if existing._thread is not None and existing._thread.is_alive():
                    raise FileTransferError("file_transfer_busy", "previous sender attempt is still settling")
            record = existing or _TransferRecord(
                transfer_id,
                direction=direction,
                filename=filename,
                event_retention=self.event_retention,
                event_sink=self.event_sink,
            )
            # Резервируем admission, но failed record не оживает до claim.
            self._active_id = transfer_id
        claimed = False
        try:
            self._claim(transfer_id, direction)
            claimed = True
            with self._lock:
                if self._stopping.is_set():
                    raise FileTransferError("local_shutdown", "manager closed during transfer claim")
                if existing is not None:
                    self._restart_record(record, "preparing")
                    while transfer_id in self._terminal_order:
                        self._terminal_order.remove(transfer_id)
                self._records[transfer_id] = record
        except Exception:
            if claimed:
                try:
                    self._release(transfer_id, direction)
                except Exception as exc:
                    with self._lock:
                        self._records[transfer_id] = record
                    failure = FileTransferError("local_ownership_unsettled", str(exc), phase="preparing")
                    record.event("resume_rollback_failed", error=str(exc))
                    if existing is None:
                        record.terminal("failed", failure=failure)
                    raise failure from exc
            with self._lock:
                if self._active_id == transfer_id:
                    self._active_id = None
            raise
        record.event("transfer_started", progress=record.snapshot())
        return record

    def _terminal_record(
        self,
        record: _TransferRecord,
        state: str,
        *,
        failure: FileTransferError | None = None,
        final_path: Path | None = None,
    ) -> None:
        action = lambda: self._terminal_record_settled(record, state, failure=failure, final_path=final_path)
        try:
            if threading.current_thread() is self._rx_thread or getattr(self._control_admission, "depth", 0):
                self._outbox.submit(action, on_error=lambda exc: self._terminal_outbox_failed(record, exc, final_path))
            else:
                self._outbox.call(action)
        except OutboxError as exc:
            record.event("outbox_overflow", error=str(exc))
            record.terminal("failed", failure=FileTransferError("local_ownership_unsettled", str(exc), phase="settling"))

    def _terminal_outbox_failed(self, record, exc, final_path) -> None:
        # Durable publication не отменяется, но lease без drain не освобождается.
        record.event("terminal_outbox_failed", error=str(exc))
        record.terminal("failed", failure=FileTransferError("local_ownership_unsettled", str(exc), phase="settling"), final_path=final_path)

    def _terminal_record_settled(self, record, state, *, failure=None, final_path=None) -> None:
        drain = getattr(self.transport, "drain_binary", None)
        if callable(drain):
            try:
                outcomes = drain(self._timing_budget_s("drain"))
                if outcomes:
                    record.event("local_tx_drained", outcomes=outcomes)
            except (BinaryUserError, FileTransferError) as exc:
                # Пока host write живёт, lease остаётся занятой. Закрытие session
                # завершает этот путь; неизвестный исход не является отменой bytes.
                record.event("local_tx_drain_failed", code=exc.code, error=str(exc))
                record.terminal(
                    "failed",
                    failure=failure or FileTransferError(exc.code, str(exc), phase="settling"),
                    final_path=final_path,
                )
                return
        record.terminal(state, failure=failure, final_path=final_path)
        try:
            self._release(record.transfer_id, record.direction)
        finally:
            with self._lock:
                if self._active_id == record.transfer_id:
                    self._active_id = None
                self._terminal_order.append(record.transfer_id)
                while len(self._terminal_order) > self.max_retained_terminal:
                    evicted = self._terminal_order.popleft()
                    if self._active_id != evicted:
                        self._records.pop(evicted, None)

    def _prepare_source(
        self,
        path: Path,
        record: _TransferRecord,
    ) -> _PreparedSource:
        from .resume_source import prepare_source

        return prepare_source(path, record)

    @staticmethod
    def _message_event_fields(message: FileMessage) -> dict[str, Any]:
        fields: dict[str, Any] = {"message_type": type(message).__name__.removesuffix("Message").upper()}
        if isinstance(message, DataMessage):
            fields["chunk_index"] = message.chunk_index
        elif isinstance(message, MissingMessage):
            fields["ranges"] = len(message.ranges)
            fields["chunks"] = sum(item.count for item in message.ranges)
        return fields

    @staticmethod
    def _check_remote_failure(record: _TransferRecord | None) -> None:
        if record is None or record.direction != "TX":
            return
        if getattr(record, "control_overflow", False):
            raise FileTransferError("control_queue_overflow", "bounded FT1 control queue overflow", phase="waiting_result")
        with record._condition:
            result = record.remote_result
        if result is not None and not result.ok:
            raise FileTransferError(
                "remote_failed",
                result.reason or result.code,
                phase=record.state,
                details={"remote_code": result.code},
            )

    @staticmethod
    def _check_send_deadline(deadline: float | None) -> None:
        if deadline is not None and time.monotonic() >= deadline:
            raise FileTransferError(
                "remote_result_timeout", "remote completion deadline expired", phase="waiting_result",
            )

    def _send_message(self, message, *, cancel_event, deadline=None) -> None:
        action = lambda: self._send_message_direct(message, cancel_event=cancel_event, deadline=deadline)
        try:
            # Outbox action берёт manager lock для correlation. Admission под
            # тем же lock ставит control в очередь, иначе два потока ждут друг друга.
            if threading.current_thread() is self._rx_thread or getattr(self._control_admission, "depth", 0):
                self._outbox.submit(action, on_error=lambda exc: self._outbound_error(message.transfer_id, exc))
            else:
                self._outbox.call(action, deadline=deadline)
        except OutboxError as exc:
            self._check_send_deadline(deadline)
            raise FileTransferError("local_outbox_unsettled", str(exc), phase="sending") from exc

    def _outbound_error(self, transfer_id: int, exc: Exception) -> None:
        with self._lock:
            record = self._records.get(transfer_id)
        if record is not None:
            record.event("control_delivery_failed", error=str(exc))
        self._enqueue_rx(_OutboundFailure(transfer_id, exc))

    def _enqueue_rx(self, item) -> None:
        if self._stopping.is_set():
            return
        try:
            self._rx_queue.put_nowait(item)
        except queue.Full:
            self.last_rx_worker_error = "bounded FT1 RX queue overflow"
            self._rx_overflow.set()
            with self._lock:
                record = self._records.get(getattr(item, "transfer_id", None))
            if record is not None:
                record.event("rx_queue_overflow", partial_retained=True)

    def _send_message_direct(
        self,
        message: FileMessage,
        *,
        cancel_event: threading.Event | None,
        deadline: float | None = None,
    ) -> None:
        payload = encode_message(message, self.transport.payload_capacity)
        fields = self._message_event_fields(message)
        with self._lock:
            record = self._records.get(message.transfer_id)
        if record is not None:
            record.event("binary_send_start", **fields)

        replay = 0
        while True:
            if self._stopping.is_set():
                raise FileTransferError("local_shutdown", "file manager is closing")
            self._check_remote_failure(record)
            self._check_send_deadline(deadline)
            try:
                send_until = getattr(self.transport, "send_binary_until", None)
                if deadline is not None and callable(send_until):
                    send_until(payload, deadline=deadline, cancel_event=cancel_event)
                else:
                    self.transport.send_binary(payload, cancel_event=cancel_event)
                if record is not None:
                    record.event(
                        "binary_send_settled",
                        **fields,
                        local_replays=replay,
                    )
                return
            except BinaryUserCancelled as exc:
                raise FileTransferCancelled(str(exc)) from exc
            except BinaryUserError as exc:
                self._check_send_deadline(deadline)
                if (
                    exc.code in {
                        "local_tx_unknown",
                        "local_disconnect",
                        "local_controller_reset",
                    }
                    and replay < self.max_local_message_replays
                ):
                    replay += 1
                    if record is not None:
                        record.event(
                            "binary_send_replay",
                            **fields,
                            reason=exc.code,
                            attempt=replay,
                            maximum=self.max_local_message_replays,
                        )
                    continue
                if record is not None:
                    record.event(
                        "binary_send_failed",
                        **fields,
                        binary_error=exc.code,
                        local_replays=replay,
                    )
                raise FileTransferError(
                    "binary_send_failed",
                    exc.message,
                    phase="sending",
                    details={
                        "binary_error": exc.code,
                        "local_replays": replay,
                    },
                ) from exc

    def start_send(self, local_path: str | Path) -> dict[str, Any]:
        path = Path(local_path).expanduser()
        if not path.exists():
            raise FileTransferError(
                "file_not_found",
                f"local file does not exist: {path}",
                phase="preparing",
            )
        if not path.is_file():
            raise FileTransferError(
                "not_a_file",
                f"local path is not a regular file: {path}",
                phase="preparing",
            )
        with self._lock:
            transfer_id = self._new_transfer_id_locked()
        record = self._reserve_record(
            transfer_id,
            direction="TX",
            filename=path.name,
        )
        thread = threading.Thread(
            target=self._send_worker,
            args=(record, path),
            name=f"serialterminal-file-tx-{transfer_id_text(transfer_id)}",
            daemon=True,
        )
        record._thread = thread
        thread.start()
        result = record.snapshot()
        result["events"] = {
            "cursor": 0,
            "max_window": FILE_MAX_WINDOW,
            "retention": self.event_retention,
        }
        return result

    def _send_worker(self, record: _TransferRecord, path: Path) -> None:
        prepared: _PreparedSource | None = None
        try:
            prepared = self._prepare_source(path, record)
            chunk_size = data_payload_capacity(self.transport.payload_capacity)
            try:
                chunks_total = checked_chunk_count(prepared.wire_size, chunk_size)
            except FileProtocolError as exc:
                raise FileTransferError("invalid_metadata", str(exc), phase="preparing") from exc
            record.set_sizes(
                original_bytes=prepared.original_size,
                wire_bytes=prepared.wire_size,
                chunks_total=chunks_total,
            )
            meta = MetaMessage(
                transfer_id=record.transfer_id,
                filename=prepared.filename,
                original_size=prepared.original_size,
                wire_size=prepared.wire_size,
                compression=prepared.compression,
                chunk_size=chunk_size,
                original_sha256=prepared.original_sha256,
            )
            end = EndMessage(
                transfer_id=record.transfer_id,
                chunk_count=chunks_total,
                wire_sha256=prepared.wire_sha256,
            )

            record.set_state("sending")
            self._send_message(meta, cancel_event=record.cancel_event)
            self._send_all_chunks(
                record,
                prepared,
                chunk_size=chunk_size,
            )
            self._send_message(end, cancel_event=record.cancel_event)
            result = self._await_remote_completion(
                record,
                prepared,
                meta=meta,
                end=end,
                chunk_size=chunk_size,
            )
            if not result.ok:
                raise FileTransferError(
                    "remote_failed",
                    result.reason or result.code,
                    phase="waiting_result",
                    details={"remote_code": result.code},
                )
            self._terminal_record(record, "completed")
        except FileTransferCancelled as exc:
            self._terminal_record(record, "cancelled", failure=exc)
        except FileTransferError as exc:
            self._terminal_record(record, "failed", failure=exc)
        except Exception as exc:
            failure = FileTransferError(
                "local_failure",
                str(exc),
                phase=record.state,
            )
            self._terminal_record(record, "failed", failure=failure)
        finally:
            if prepared is not None and prepared.remove_wire_path:
                prepared.wire_path.unlink(missing_ok=True)

    def _send_all_chunks(
        self,
        record: _TransferRecord,
        prepared: _PreparedSource,
        *,
        chunk_size: int,
    ) -> None:
        sent_bytes = 0
        chunk_index = 0
        with prepared.wire_path.open("rb") as source:
            while True:
                if record.cancel_event.is_set():
                    raise FileTransferCancelled()
                block = source.read(chunk_size)
                if not block:
                    break
                self._send_message(
                    DataMessage(
                        transfer_id=record.transfer_id,
                        chunk_index=chunk_index,
                        payload=block,
                    ),
                    cancel_event=record.cancel_event,
                )
                sent_bytes += len(block)
                chunk_index += 1
                record.set_progress(
                    bytes_completed=sent_bytes,
                    chunks_completed=chunk_index,
                )

    def _send_requested_chunks(
        self,
        record: _TransferRecord,
        prepared: _PreparedSource,
        message: MissingMessage,
        *,
        chunk_size: int,
        deadline: float | None = None,
    ) -> None:
        try:
            validate_missing_ranges(
                message.ranges,
                chunk_count=record.chunks_total,
            )
        except FileProtocolError as exc:
            raise FileTransferError(
                "invalid_repair_request",
                str(exc),
                phase="repairing",
            ) from exc

        chunks_requested = sum(item.count for item in message.ranges)
        record.set_state("repairing")
        record.event(
            "repair_requested",
            ranges=len(message.ranges),
            chunks=chunks_requested,
        )
        with prepared.wire_path.open("rb") as source:
            for item in message.ranges:
                for chunk_index in range(
                    item.start_chunk,
                    item.start_chunk + item.count,
                ):
                    if record.cancel_event.is_set():
                        raise FileTransferCancelled()
                    source.seek(chunk_index * chunk_size)
                    block = source.read(chunk_size)
                    if not block:
                        raise FileTransferError(
                            "invalid_repair_request",
                            f"requested chunk {chunk_index} is outside prepared stream",
                            phase="repairing",
                        )
                    self._send_message(
                        DataMessage(
                            transfer_id=record.transfer_id,
                            chunk_index=chunk_index,
                            payload=block,
                        ),
                        cancel_event=record.cancel_event,
                        deadline=deadline,
                    )
        record.event(
            "repair_round_sent",
            ranges=len(message.ranges),
            chunks=chunks_requested,
        )

    def _wait_remote_outcome(
        self,
        record: _TransferRecord,
        *,
        timeout_s: float,
    ) -> ResultMessage | MissingMessage | None:
        deadline = time.monotonic() + timeout_s
        with record._condition:
            while True:
                if record.cancel_event.is_set():
                    raise FileTransferCancelled()
                if record.remote_result is not None:
                    return record.remote_result
                if record.remote_missing:
                    return record.remote_missing.popleft()
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                # cancel() и remote outcome сами notify тот же condition, поэтому
                # здесь нет периодического pacing/polling на fast path.
                record._condition.wait(timeout=remaining)

    def _await_remote_completion(
        self,
        record: _TransferRecord,
        prepared: _PreparedSource,
        *,
        meta: MetaMessage,
        end: EndMessage,
        chunk_size: int,
    ) -> ResultMessage:
        overall_deadline = None if self.result_timeout_s is None else time.monotonic() + self.result_timeout_s
        control_replays = 0
        repair_rounds = 0

        while True:
            record.set_state("waiting_result")
            remaining_total = math.inf if overall_deadline is None else overall_deadline - time.monotonic()
            if remaining_total <= 0:
                raise FileTransferError(
                    "remote_result_timeout",
                    "remote verified RESULT did not arrive before timeout",
                    phase="waiting_result",
                )
            outcome = self._wait_remote_outcome(
                record,
                timeout_s=min(
                    self._timing_budget_s("control", self.control_replay_interval_s),
                    remaining_total,
                ),
            )
            if isinstance(outcome, ResultMessage):
                return outcome
            if isinstance(outcome, MissingMessage):
                repair_rounds += 1
                if repair_rounds > self.max_repair_rounds:
                    raise FileTransferError(
                        "repair_round_limit",
                        "file repair exceeded bounded repair round limit",
                        phase="repairing",
                        details={"max_repair_rounds": self.max_repair_rounds},
                    )
                self._send_requested_chunks(
                    record,
                    prepared,
                    outcome,
                    chunk_size=chunk_size,
                    deadline=overall_deadline,
                )
                self._send_message(end, cancel_event=record.cancel_event, deadline=overall_deadline)
                continue

            if control_replays >= self.max_control_replays:
                raise FileTransferError(
                    "remote_result_timeout",
                    "remote verified RESULT did not arrive after bounded control replay",
                    phase="waiting_result",
                    details={"control_replays": control_replays},
                )
            control_replays += 1
            record.event(
                "control_replay",
                attempt=control_replays,
                maximum=self.max_control_replays,
            )
            # META and END are deliberately idempotent. Replaying both lets a
            # receiver that missed either local notification reconstruct state
            # and answer with MISSING or the final RESULT.
            self._send_message(meta, cancel_event=record.cancel_event, deadline=overall_deadline)
            self._send_message(end, cancel_event=record.cancel_event, deadline=overall_deadline)

    def feed_binary(self, payload: bytes) -> None:
        try:
            message = decode_message(payload)
        except FileProtocolError:
            return
        if message is None:
            return
        if isinstance(message, (ResultMessage, MissingMessage)):
            with self._lock:
                record = self._records.get(message.transfer_id)
            if record is not None and record.direction == "TX":
                if isinstance(message, ResultMessage):
                    record.set_remote_result(message)
                else:
                    record.set_remote_missing(message)
            return
        self._enqueue_rx(message)

    def _rx_loop(self) -> None:
        while not self._stopping.is_set():
            if self._rx_overflow.is_set():
                self._rx_overflow.clear()
                with self._lock:
                    incoming = self._incoming
                if incoming is not None:
                    try:
                        self._fail_incoming(incoming, FileTransferError("receiver_overflow", "bounded FT1 RX queue overflow", phase="receiving"))
                    except Exception as exc:
                        self._rx_worker_error(exc)
            try:
                item = self._rx_queue.get(timeout=FILE_RX_IDLE_SWEEP_S)
            except queue.Empty:
                try:
                    self._expire_stale_incoming()
                except Exception as exc:
                    self._rx_worker_error(exc)
                continue
            if item is None:
                return
            try:
                if isinstance(item, _OutboundFailure):
                    incoming = self._incoming_for(item.transfer_id)
                    if incoming is not None:
                        self._fail_incoming(incoming, FileTransferError("binary_send_failed", str(item.error), phase="receiving"))
                elif isinstance(item, _CancelIncoming):
                    self._cancel_incoming(item.transfer_id)
                elif isinstance(item, MetaMessage):
                    self._handle_meta(item)
                elif isinstance(item, DataMessage):
                    self._handle_data(item)
                elif isinstance(item, EndMessage):
                    self._handle_end(item)
            except Exception as exc:
                # Неожиданный отказ callback/storage видим и завершает попытку;
                # общий RX worker продолжает работу, retained bytes не удаляются.
                self._rx_worker_error(exc)

    def _rx_worker_error(self, exc: Exception) -> None:
        from ..application_log import report_exception
        report_exception(exc, "FT1 RX worker")
        with self._lock:
            incoming = self._incoming
            self._incoming = None
        if incoming is None:
            self.last_rx_worker_error = str(exc)
            return
        record = incoming.record
        record.event("rx_worker_error", error=str(exc), partial_retained=True)
        self._terminal_record(
            record,
            "failed",
            failure=FileTransferError("receiver_failed", str(exc), phase="receiving"),
        )

    def _touch_incoming(self, incoming: _IncomingState) -> None:
        incoming.last_activity_monotonic = time.monotonic()

    def _expire_stale_incoming(self) -> None:
        with self._lock:
            incoming = self._incoming
        if incoming is None:
            return
        idle_s = time.monotonic() - incoming.last_activity_monotonic
        idle_budget = self._incoming_idle_budget_s()
        if idle_s < idle_budget:
            return
        self._fail_incoming(
            incoming,
            FileTransferError(
                "remote_sender_timeout",
                (
                    "incoming FT1 transfer received no META/DATA/END activity "
                    f"for {idle_budget:.0f}s"
                ),
                phase="receiving",
                details={"idle_seconds": round(idle_s, 3)},
            ),
        )

    def _send_result(
        self,
        record: _TransferRecord | None,
        result: ResultMessage,
    ) -> bool:
        try:
            self._send_message(result, cancel_event=None)
        except Exception as exc:
            if record is not None:
                record.event(
                    "result_delivery_failed",
                    error=str(exc),
                )
            return False
        if record is not None:
            record.event("result_submitted", ok=result.ok)
        return True

    def _send_result_async(
        self,
        record: _TransferRecord | None,
        result: ResultMessage,
    ) -> None:
        try:
            action = lambda: self._send_result(record, result)
            if threading.current_thread() is self._rx_thread or getattr(self._control_admission, "depth", 0):
                self._outbox.submit(action)
            else:
                self._outbox.call(action)
        except OutboxError as exc:
            self.last_rx_worker_error = str(exc)
            if record is not None:
                record.event("result_delivery_failed", error=str(exc))

    def _reject_incoming(
        self,
        transfer_id: int,
        code: str,
        reason: str,
    ) -> None:
        self._send_result_async(
            None,
            ResultMessage(
                transfer_id=transfer_id,
                ok=False,
                code=code,
                reason=reason,
            ),
        )

    def _handle_meta(self, meta: MetaMessage) -> None:
        try:
            checked_chunk_count(meta.wire_size, meta.chunk_size)
        except FileProtocolError as exc:
            self._reject_incoming(meta.transfer_id, "invalid_metadata", str(exc))
            return
        with self._lock:
            existing = self._records.get(meta.transfer_id)
            active = self._active_id
            incoming = self._incoming

        if existing is not None:
            if existing.direction == "RX" and existing.rx_meta == meta:
                if existing.state == "completed":
                    self._send_result_async(
                        existing,
                        ResultMessage(
                            transfer_id=meta.transfer_id,
                            ok=True,
                            code="ok",
                            reason="",
                        ),
                    )
                elif (
                    incoming is not None
                    and incoming.record.transfer_id == meta.transfer_id
                ):
                    self._touch_incoming(incoming)
                    existing.event("meta_replayed")
                return
            self._reject_incoming(
                meta.transfer_id,
                "invalid_metadata",
                "conflicting META for existing transfer_id",
            )
            return

        if active is not None:
            self._reject_incoming(
                meta.transfer_id,
                "busy",
                "another file transfer is active",
            )
            return

        wire_path: Path | None = None
        try:
            filename = safe_received_filename(meta.filename)
            maximum = data_payload_capacity(self.transport.payload_capacity)
            if not 1 <= meta.chunk_size <= maximum:
                raise FileTransferError(
                    "invalid_metadata",
                    "remote chunk size exceeds local binary transport capacity",
                    phase="receiving",
                )
            self.receive_dir.mkdir(parents=True, exist_ok=True)
            temporary = tempfile.NamedTemporaryFile(
                prefix=f".serialterminal-{transfer_id_text(meta.transfer_id)}-",
                suffix=".part",
                dir=self.receive_dir,
                delete=False,
            )
            wire_path = Path(temporary.name)
            temporary.close()
            record = self._reserve_record(
                meta.transfer_id,
                direction="RX",
                filename=filename,
            )
        except FileTransferError as exc:
            if wire_path is not None:
                wire_path.unlink(missing_ok=True)
            self._reject_incoming(meta.transfer_id, exc.code, exc.message)
            return
        except Exception as exc:
            if wire_path is not None:
                wire_path.unlink(missing_ok=True)
            self._reject_incoming(
                meta.transfer_id,
                "storage_failed",
                str(exc),
            )
            return

        assert wire_path is not None

        record.rx_meta = meta
        record.set_sizes(
            original_bytes=meta.original_size,
            wire_bytes=meta.wire_size,
            chunks_total=checked_chunk_count(meta.wire_size, meta.chunk_size),
        )
        record.set_state("receiving")
        with self._lock:
            self._incoming = _IncomingState(
                meta=meta,
                record=record,
                wire_path=wire_path,
                received={},
                last_activity_monotonic=time.monotonic(),
            )

    def _incoming_for(self, transfer_id: int) -> _IncomingState | None:
        with self._lock:
            incoming = self._incoming
        if incoming is None or incoming.record.transfer_id != transfer_id:
            return None
        return incoming

    def _expected_chunk_length(
        self,
        incoming: _IncomingState,
        chunk_index: int,
    ) -> int:
        total = incoming.record.chunks_total
        if not 0 <= chunk_index < total:
            raise FileTransferError(
                "invalid_chunk",
                f"chunk index {chunk_index} is outside 0..{max(0, total - 1)}",
                phase="receiving",
            )
        if chunk_index < total - 1:
            return incoming.meta.chunk_size
        return incoming.meta.wire_size - incoming.meta.chunk_size * (total - 1)

    def _handle_data(self, message: DataMessage) -> None:
        incoming = self._incoming_for(message.transfer_id)
        if incoming is None:
            return
        if incoming.record.cancel_event.is_set():
            self._fail_incoming(
                incoming,
                FileTransferCancelled(),
                terminal_state="cancelled",
            )
            return
        try:
            try:
                expected_length = self._expected_chunk_length(
                    incoming,
                    message.chunk_index,
                )
            except FileTransferError as exc:
                incoming.record.event(
                    "chunk_rejected", chunk_index=message.chunk_index, reason=exc.code
                )
                return
            if len(message.payload) != expected_length:
                # Повреждённый DATA не должен уничтожать уже собранные чанки.
                # Не отмечаем его полученным: END/MISSING запросит исходный блок.
                # Если корректная копия уже сохранена, сохраняем и её bitmap bit.
                incoming.record.event(
                    "chunk_rejected",
                    chunk_index=message.chunk_index,
                    reason="length_mismatch",
                    actual_length=len(message.payload),
                    expected_length=expected_length,
                )
                return
            self._touch_incoming(incoming)
            offset = message.chunk_index * incoming.meta.chunk_size
            if message.chunk_index in incoming.received:
                with incoming.wire_path.open("rb") as file:
                    file.seek(offset)
                    existing = file.read(expected_length)
                if existing != message.payload:
                    incoming._quarantined = True
                    raise FileTransferError(
                        "invalid_chunk",
                        f"duplicate chunk {message.chunk_index} has different bytes",
                        phase="receiving",
                    )
                incoming.record.event(
                    "duplicate_chunk",
                    chunk_index=message.chunk_index,
                )
                return

            check_insert = getattr(incoming.received, "check_insert", None)
            if check_insert is not None:
                try:
                    check_insert(message.chunk_index)
                except ValueError as exc:
                    raise FileTransferError("storage_failed", str(exc), phase="receiving") from exc
            self._write_chunk(incoming, offset, message.payload)
            incoming.received[message.chunk_index] = len(message.payload)
            bytes_completed = incoming.record.bytes_completed + len(message.payload)
            incoming.record.set_progress(
                bytes_completed=bytes_completed,
                chunks_completed=len(incoming.received),
            )
        except FileTransferError as exc:
            self._fail_incoming(incoming, exc)

    def _write_chunk(self, incoming, offset, payload):
        with incoming.wire_path.open("r+b") as file:
            file.seek(offset)
            file.write(payload)
            file.flush()

    def _write_original_block(self, incoming, file, block):
        file.write(block)

    def _handle_end(self, message: EndMessage) -> None:
        incoming = self._incoming_for(message.transfer_id)
        if incoming is None:
            with self._lock:
                existing = self._records.get(message.transfer_id)
            if (
                existing is not None
                and existing.direction == "RX"
                and existing.state == "completed"
                and existing.rx_end == message
            ):
                existing.event("end_replayed")
                self._send_result_async(
                    existing,
                    ResultMessage(
                        transfer_id=message.transfer_id,
                        ok=True,
                        code="ok",
                        reason="",
                    ),
                )
            elif (
                existing is not None
                and existing.direction == "RX"
                and existing.state == "completed"
            ):
                self._reject_incoming(
                    message.transfer_id,
                    "protocol_error",
                    "conflicting END for completed transfer_id",
                )
            return
        if incoming.record.cancel_event.is_set():
            self._fail_incoming(
                incoming,
                FileTransferCancelled(),
                terminal_state="cancelled",
            )
            return
        record = incoming.record
        final_temp = None
        try:
            if message.chunk_count != record.chunks_total:
                record.event(
                    "end_rejected", reason="chunk_count_mismatch",
                    actual_chunk_count=message.chunk_count,
                    expected_chunk_count=record.chunks_total,
                )
                return
            self._touch_incoming(incoming)
            missing = [] if len(incoming.received) == record.chunks_total else [
                index
                for index in range(record.chunks_total)
                if index not in incoming.received
            ]
            if missing:
                ranges = canonical_missing_ranges(
                    missing,
                    chunk_count=record.chunks_total,
                )
                repair = MissingMessage(
                    transfer_id=record.transfer_id,
                    ranges=ranges,
                )
                try:
                    encode_message(
                        repair,
                        self.transport.payload_capacity,
                    )
                except FileProtocolError as exc:
                    raise FileTransferError(
                        "repair_too_large",
                        (
                            f"missing set needs {len(ranges)} ranges and does not "
                            "fit one FT1 MISSING message; resend file explicitly"
                        ),
                        phase="repairing",
                        details={
                            "missing_chunks": len(missing),
                            "missing_ranges": len(ranges),
                        },
                    ) from exc
                record.event(
                    "missing_detected",
                    chunks=len(missing),
                    ranges=len(ranges),
                    first_missing=missing[0],
                )
                record.set_state("repair_requested")
                self._send_message(
                    repair,
                    cancel_event=record.cancel_event,
                )
                record.event(
                    "repair_requested",
                    chunks=len(missing),
                    ranges=len(ranges),
                )
                record.set_state("repairing")
                return
            actual_size = incoming.wire_path.stat().st_size
            if actual_size != incoming.meta.wire_size:
                raise FileTransferError(
                    "missing_chunks",
                    (
                        f"wire file size {actual_size} does not match "
                        f"expected {incoming.meta.wire_size}"
                    ),
                    phase="verifying",
                )

            record.set_state("verifying")
            wire_hash = _sha256_file(
                incoming.wire_path,
                record.cancel_event,
            )
            if wire_hash != message.wire_sha256:
                raise FileTransferError(
                    "wire_hash_mismatch",
                    "received wire stream SHA-256 mismatch",
                    phase="verifying",
                )

            final_temp, original_hash, original_size = self._materialize_original(
                incoming
            )
            if original_size != incoming.meta.original_size:
                if final_temp != incoming.wire_path:
                    final_temp.unlink(missing_ok=True)
                raise FileTransferError(
                    "original_hash_mismatch",
                    (
                        f"original size {original_size} does not match "
                        f"expected {incoming.meta.original_size}"
                    ),
                    phase="verifying",
                )
            if original_hash != incoming.meta.original_sha256:
                if final_temp != incoming.wire_path:
                    final_temp.unlink(missing_ok=True)
                raise FileTransferError(
                    "original_hash_mismatch",
                    "original file SHA-256 mismatch",
                    phase="verifying",
                )

            destination = self._publish_verified(incoming, message, final_temp)
            record.rx_end = message

            # Держим session transfer lease до controller-local BINARY
            # presentation RESULT. RF delivery здесь не доказывается: если
            # RESULT потеряется, sender повторит idempotent META/END и receiver
            # снова отправит RESULT.
            self._send_result(
                record,
                ResultMessage(
                    transfer_id=record.transfer_id,
                    ok=True,
                    code="ok",
                    reason="",
                ),
            )
            with self._lock:
                if self._incoming is incoming:
                    self._incoming = None
            self._terminal_record(
                record,
                "completed",
                final_path=destination,
            )
            self._cleanup_published(incoming)
        except FileTransferCancelled as exc:
            self._fail_incoming(
                incoming,
                exc,
                terminal_state="cancelled",
            )
        except FileTransferError as exc:
            self._fail_incoming(incoming, exc)
        except Exception as exc:
            self._fail_incoming(
                incoming,
                FileTransferError(
                    "storage_failed",
                    str(exc),
                    phase=record.state,
                ),
            )
        finally:
            if final_temp is not None and final_temp != incoming.wire_path:
                try:
                    final_temp.unlink(missing_ok=True)
                except OSError as exc:
                    record.event("publication_cleanup_failed", error=str(exc))

    @staticmethod
    def _fsync_directory(directory: Path) -> None:
        try:
            descriptor = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        except OSError:
            # Без POSIX directory fsync сохраняется совместимость, но строгая
            # гарантия пережить power loss для rename не заявляется.
            if os.name == "posix":
                raise
            return
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def _publish_verified(self, incoming, end: EndMessage, final_temp: Path) -> Path:
        with final_temp.open("rb") as handle:
            os.fsync(handle.fileno())
        destination = _unique_destination(self.receive_dir, incoming.record.filename)
        os.replace(final_temp, destination)
        self._fsync_directory(destination.parent)
        return destination

    def _cleanup_published(self, incoming) -> None:
        try:
            incoming.wire_path.unlink(missing_ok=True)
        except OSError as exc:
            incoming.record.event("publication_cleanup_failed", error=str(exc))

    def _materialize_original(
        self,
        incoming: _IncomingState,
    ) -> tuple[Path, bytes, int]:
        record = incoming.record
        if incoming.meta.compression is Compression.NONE:
            digest = _sha256_file(incoming.wire_path, record.cancel_event)
            return incoming.wire_path, digest, incoming.meta.wire_size

        if incoming.meta.compression is not Compression.GZIP:
            raise FileTransferError(
                "decompression_failed",
                "unsupported compression method",
                phase="decompressing",
            )

        record.set_state("decompressing")
        temporary = tempfile.NamedTemporaryFile(
            prefix=f".serialterminal-{transfer_id_text(record.transfer_id)}-",
            suffix=".verified",
            dir=self.receive_dir,
            delete=False,
        )
        output_path = Path(temporary.name)
        digest = hashlib.sha256()
        size = 0
        try:
            with temporary:
                with gzip.open(incoming.wire_path, "rb") as source:
                    while True:
                        if record.cancel_event.is_set():
                            raise FileTransferCancelled()
                        block = source.read(_IO_CHUNK)
                        if not block:
                            break
                        size += len(block)
                        if size > incoming.meta.original_size:
                            raise FileTransferError(
                                "decompression_failed",
                                "decompressed data exceeds declared original size",
                                phase="decompressing",
                            )
                        digest.update(block)
                        self._write_original_block(incoming, temporary, block)
            return output_path, digest.digest(), size
        except FileTransferError:
            output_path.unlink(missing_ok=True)
            raise
        except Exception as exc:
            output_path.unlink(missing_ok=True)
            raise FileTransferError(
                "decompression_failed",
                str(exc),
                phase="decompressing",
            ) from exc

    def _fail_incoming(
        self,
        incoming: _IncomingState,
        failure: FileTransferError,
        *,
        terminal_state: str = "failed",
    ) -> None:
        if terminal_state == "cancelled":
            incoming.wire_path.unlink(missing_ok=True)
        else:
            incoming.record.event(
                "partial_retained", reason=failure.code,
                quarantined=getattr(incoming, "_quarantined", False),
            )
        with self._lock:
            if self._incoming is incoming:
                self._incoming = None
        # Claimed incoming transfer держит session ownership до локального
        # BINARY submission RESULT; remote loss чинится повторным FT1 control replay.
        self._send_result(
            incoming.record,
            ResultMessage(
                transfer_id=incoming.record.transfer_id,
                ok=False,
                code=(
                    failure.code
                    if failure.code in {
                        "busy",
                        "invalid_metadata",
                        "invalid_chunk",
                        "missing_chunks",
                        "wire_hash_mismatch",
                        "decompression_failed",
                        "original_hash_mismatch",
                        "storage_failed",
                        "repair_too_large",
                        "missing_percent_exceeded",
                        "recursion_depth_limit",
                        "repair_no_progress",
                        "remote_sender_timeout",
                        "cancelled",
                        "protocol_error",
                    }
                    else "protocol_error"
                ),
                reason=failure.message,
            ),
        )
        self._terminal_record(
            incoming.record,
            terminal_state,
            failure=failure,
        )

    def _cancel_incoming(self, transfer_id: int) -> None:
        incoming = self._incoming_for(transfer_id)
        if incoming is not None:
            self._fail_incoming(
                incoming,
                FileTransferCancelled(),
                terminal_state="cancelled",
            )

    def observe(
        self,
        transfer_id: str | int,
        *,
        cursor: int = 0,
        window: int = FILE_MAX_WINDOW,
        timeout_ms: int = 0,
    ) -> dict[str, Any]:
        try:
            parsed = parse_transfer_id(transfer_id)
        except FileProtocolError as exc:
            raise FileTransferError(
                "invalid_transfer_id",
                str(exc),
            ) from exc
        with self._lock:
            record = self._records.get(parsed)
        if record is None:
            raise FileTransferError(
                "unknown_file_transfer",
                f"unknown file transfer: {transfer_id}",
            )
        return record.observe(
            cursor=cursor,
            window=window,
            timeout_ms=timeout_ms,
        )

    def cancel(self, transfer_id: str | int) -> dict[str, Any]:
        try:
            parsed = parse_transfer_id(transfer_id)
        except FileProtocolError as exc:
            raise FileTransferError(
                "invalid_transfer_id",
                str(exc),
            ) from exc
        with self._lock:
            record = self._records.get(parsed)
        if record is None:
            raise FileTransferError(
                "unknown_file_transfer",
                f"unknown file transfer: {transfer_id}",
            )
        if record.state in _TERMINAL_STATES:
            return record.snapshot()
        record.cancel_event.set()
        record.event("cancel_requested")
        if record.direction == "RX":
            self._enqueue_rx(_CancelIncoming(parsed))
        return record.snapshot()

    def close_transfer(self, transfer_id: str | int) -> dict[str, Any]:
        parsed = parse_transfer_id(transfer_id)
        with self._lock:
            record = self._records.get(parsed)
            if record is None:
                raise FileTransferError(
                    "unknown_file_transfer",
                    f"unknown file transfer: {transfer_id}",
                )
            if record.state not in _TERMINAL_STATES:
                raise FileTransferError(
                    "file_transfer_active",
                    "active transfer cannot be closed",
                )
            self._records.pop(parsed, None)
            self._terminal_order = deque(
                value for value in self._terminal_order if value != parsed
            )
        return {
            "transfer_id": transfer_id_text(parsed),
            "state": "closed",
        }

    def display_snapshot(self) -> dict[str, Any] | None:
        with self._lock:
            transfer_id = self._active_id
            if transfer_id is None and self._terminal_order:
                transfer_id = self._terminal_order[-1]
            record = self._records.get(transfer_id) if transfer_id is not None else None
        return None if record is None else record.snapshot()

    def snapshots(self) -> list[dict[str, Any]]:
        with self._lock:
            records = list(self._records.values())
        return [record.snapshot() for record in records]

    def cancel_active(self) -> None:
        with self._lock:
            active = self._active_id
        if active is not None:
            try:
                self.cancel(active)
            except FileTransferError:
                pass

    def join_all(self, timeout: float) -> None:
        deadline = time.monotonic() + max(0.0, timeout)
        with self._lock:
            threads = [
                record._thread
                for record in self._records.values()
                if record._thread is not None
            ]
        for thread in threads:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            thread.join(timeout=remaining)

    def close(self) -> None:
        self.cancel_active()
        self.join_all(1.0)
        self._stopping.set()
        self.transport.set_receiver(None)
        try:
            self._rx_queue.put_nowait(None)
        except queue.Full:
            pass
        self._rx_thread.join(timeout=1.0)
        self._outbox.close(1.0)
        with self._lock:
            incoming = self._incoming
            self._incoming = None
        if incoming is not None:
            incoming.wire_path.unlink(missing_ok=True)
