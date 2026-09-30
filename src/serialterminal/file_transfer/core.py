from __future__ import annotations

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
    BinaryUserTransferLifecycle,
    BinaryUserTransport,
)


FILE_EVENT_RETENTION = 1024
FILE_MAX_WINDOW = 100
FILE_MAX_RETAINED_TERMINAL = 16
FILE_RESULT_TIMEOUT_S = 3600.0
FILE_CONTROL_REPLAY_INTERVAL_S = 30.0
FILE_MAX_CONTROL_REPLAYS = 3
FILE_MAX_REPAIR_ROUNDS = 8
FILE_MAX_LOCAL_MESSAGE_REPLAYS = 4
_IO_CHUNK = 256 * 1024

_TERMINAL_STATES = frozenset({"completed", "failed", "cancelled"})


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


@dataclass(frozen=True)
class _CancelIncoming:
    transfer_id: int


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


def _unique_destination(directory: Path, filename: str) -> Path:
    candidate = directory / filename
    if not candidate.exists():
        return candidate
    stem = candidate.stem
    suffix = candidate.suffix
    for index in range(1, 10000):
        alternate = directory / f"{stem} ({index}){suffix}"
        if not alternate.exists():
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
        self.remote_missing: deque[MissingMessage] = deque()
        self.rx_meta: MetaMessage | None = None
        self.rx_end: EndMessage | None = None
        self.started_monotonic = time.monotonic()
        self.ended_monotonic: float | None = None
        self._condition = threading.Condition()
        self._events: deque[dict[str, Any]] = deque(maxlen=event_retention)
        self._next_event_seq = 1
        self._thread: threading.Thread | None = None

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
            self.remote_result = result
            self._condition.notify_all()
        self.event(
            "remote_result",
            ok=result.ok,
            code=result.code,
            reason=result.reason,
        )

    def set_remote_missing(self, message: MissingMessage) -> None:
        with self._condition:
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
    """One-session FT1 sender/receiver over an opaque reliable binary transport."""

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
        result_timeout_s: float = FILE_RESULT_TIMEOUT_S,
        control_replay_interval_s: float = FILE_CONTROL_REPLAY_INTERVAL_S,
        max_control_replays: int = FILE_MAX_CONTROL_REPLAYS,
        max_repair_rounds: int = FILE_MAX_REPAIR_ROUNDS,
        max_local_message_replays: int = FILE_MAX_LOCAL_MESSAGE_REPLAYS,
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
        if result_timeout_s <= 0:
            raise ValueError("result_timeout_s must be positive")
        if control_replay_interval_s <= 0:
            raise ValueError("control_replay_interval_s must be positive")
        if max_control_replays < 0:
            raise ValueError("max_control_replays must be non-negative")
        if max_repair_rounds <= 0:
            raise ValueError("max_repair_rounds must be positive")
        if max_local_message_replays < 0:
            raise ValueError("max_local_message_replays must be non-negative")
        self.result_timeout_s = float(result_timeout_s)
        self.control_replay_interval_s = float(control_replay_interval_s)
        self.max_control_replays = int(max_control_replays)
        self.max_repair_rounds = int(max_repair_rounds)
        self.max_local_message_replays = int(max_local_message_replays)

        self._lock = threading.Lock()
        self._records: dict[int, _TransferRecord] = {}
        self._terminal_order: deque[int] = deque()
        self._active_id: int | None = None
        self._incoming: _IncomingState | None = None
        self._rx_queue: queue.Queue[FileMessage | _CancelIncoming | None] = queue.Queue()
        self._stopping = threading.Event()
        self._rx_thread = threading.Thread(
            target=self._rx_loop,
            name=f"serialterminal-file-rx-{id(self):x}",
            daemon=True,
        )
        self.transport.set_receiver(self.feed_binary)
        self._rx_thread.start()

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

    def _reserve_record(
        self,
        transfer_id: int,
        *,
        direction: str,
        filename: str,
    ) -> _TransferRecord:
        with self._lock:
            if self._active_id is not None:
                raise FileTransferError(
                    "file_transfer_busy",
                    "another file transfer is active on this session",
                    details={
                        "active_transfer_id": transfer_id_text(self._active_id),
                    },
                )
            if transfer_id in self._records:
                raise FileTransferError(
                    "duplicate_transfer_id",
                    "transfer id already exists",
                )
            record = _TransferRecord(
                transfer_id,
                direction=direction,
                filename=filename,
                event_retention=self.event_retention,
            )
            self._records[transfer_id] = record
            self._active_id = transfer_id
        claimed = False
        lifecycle_started = False
        try:
            self._claim(transfer_id, direction)
            claimed = True
            if isinstance(self.transport, BinaryUserTransferLifecycle):
                try:
                    self.transport.begin_transfer()
                    lifecycle_started = True
                except BinaryUserError as exc:
                    raise FileTransferError(
                        "binary_prepare_failed",
                        exc.message,
                        phase="preparing",
                        details={"binary_error": exc.code},
                    ) from exc
        except Exception:
            if lifecycle_started:
                try:
                    self.transport.end_transfer()
                except Exception:
                    pass
            try:
                if claimed:
                    self._release(transfer_id, direction)
            finally:
                with self._lock:
                    if self._active_id == transfer_id:
                        self._active_id = None
                    self._records.pop(transfer_id, None)
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
        record.terminal(state, failure=failure, final_path=final_path)
        try:
            if isinstance(self.transport, BinaryUserTransferLifecycle):
                try:
                    self.transport.end_transfer()
                except BinaryUserError as exc:
                    record.event(
                        "cleanup_failed",
                        code="binary_cleanup_failed",
                        binary_error=exc.code,
                        message=exc.message,
                    )
                except Exception as exc:
                    record.event(
                        "cleanup_failed",
                        code="binary_cleanup_failed",
                        message=str(exc),
                    )
        finally:
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
        original_size = path.stat().st_size
        record.original_bytes = original_size
        record.set_state("compressing")
        original_hash = hashlib.sha256()

        temporary = tempfile.NamedTemporaryFile(
            prefix="serialterminal-send-",
            suffix=".gz",
            delete=False,
        )
        temporary_path = Path(temporary.name)
        processed = 0
        try:
            with path.open("rb") as source, temporary:
                with gzip.GzipFile(
                    fileobj=temporary,
                    mode="wb",
                    mtime=0,
                ) as compressed:
                    while True:
                        if record.cancel_event.is_set():
                            raise FileTransferCancelled()
                        block = source.read(_IO_CHUNK)
                        if not block:
                            break
                        original_hash.update(block)
                        compressed.write(block)
                        processed += len(block)
                        record.set_progress(
                            bytes_completed=processed,
                            chunks_completed=0,
                        )
            compressed_size = temporary_path.stat().st_size
            original_sha256 = original_hash.digest()

            if compressed_size < original_size:
                wire_hash = _sha256_file(
                    temporary_path,
                    record.cancel_event,
                )
                return _PreparedSource(
                    source_path=path,
                    wire_path=temporary_path,
                    remove_wire_path=True,
                    filename=path.name,
                    original_size=original_size,
                    wire_size=compressed_size,
                    compression=Compression.GZIP,
                    original_sha256=original_sha256,
                    wire_sha256=wire_hash,
                )

            temporary_path.unlink(missing_ok=True)
            return _PreparedSource(
                source_path=path,
                wire_path=path,
                remove_wire_path=False,
                filename=path.name,
                original_size=original_size,
                wire_size=original_size,
                compression=Compression.NONE,
                original_sha256=original_sha256,
                wire_sha256=original_sha256,
            )
        except Exception:
            temporary.close()
            temporary_path.unlink(missing_ok=True)
            raise

    def _send_message(
        self,
        message: FileMessage,
        *,
        cancel_event: threading.Event | None,
    ) -> None:
        payload = encode_message(message, self.transport.payload_capacity)
        replay = 0
        while True:
            try:
                self.transport.send_binary(
                    payload,
                    cancel_event=cancel_event,
                )
                return
            except BinaryUserCancelled as exc:
                raise FileTransferCancelled(str(exc)) from exc
            except BinaryUserError as exc:
                if (
                    exc.code in {"local_tx_unknown", "local_disconnect"}
                    and replay < self.max_local_message_replays
                ):
                    replay += 1
                    continue
                raise FileTransferError(
                    "link_delivery_failed",
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
            chunks_total = (
                0
                if prepared.wire_size == 0
                else math.ceil(prepared.wire_size / chunk_size)
            )
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
                record._condition.wait(timeout=min(0.25, remaining))

    def _await_remote_completion(
        self,
        record: _TransferRecord,
        prepared: _PreparedSource,
        *,
        meta: MetaMessage,
        end: EndMessage,
        chunk_size: int,
    ) -> ResultMessage:
        overall_deadline = time.monotonic() + self.result_timeout_s
        control_replays = 0
        repair_rounds = 0

        while True:
            record.set_state("waiting_result")
            remaining_total = overall_deadline - time.monotonic()
            if remaining_total <= 0:
                raise FileTransferError(
                    "remote_result_timeout",
                    "remote verified RESULT did not arrive before timeout",
                    phase="waiting_result",
                )
            outcome = self._wait_remote_outcome(
                record,
                timeout_s=min(
                    self.control_replay_interval_s,
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
                )
                self._send_message(end, cancel_event=record.cancel_event)
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
            self._send_message(meta, cancel_event=record.cancel_event)
            self._send_message(end, cancel_event=record.cancel_event)

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
        self._rx_queue.put(message)

    def _rx_loop(self) -> None:
        while not self._stopping.is_set():
            item = self._rx_queue.get()
            if item is None:
                return
            try:
                if isinstance(item, _CancelIncoming):
                    self._cancel_incoming(item.transfer_id)
                elif isinstance(item, MetaMessage):
                    self._handle_meta(item)
                elif isinstance(item, DataMessage):
                    self._handle_data(item)
                elif isinstance(item, EndMessage):
                    self._handle_end(item)
            except Exception:
                # Receiver protocol failures are converted to terminal transfer
                # state inside the handlers. Never kill the shared RX worker.
                continue

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
            record.event("result_delivered", ok=result.ok)
        return True

    def _send_result_async(
        self,
        record: _TransferRecord | None,
        result: ResultMessage,
    ) -> None:
        threading.Thread(
            target=self._send_result,
            args=(record, result),
            name=f"serialterminal-file-result-{transfer_id_text(result.transfer_id)}",
            daemon=True,
        ).start()

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
                    existing.event("meta_replayed")
                return
            self._reject_incoming(
                meta.transfer_id,
                "protocol_error",
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
            chunks_total=(
                0
                if meta.wire_size == 0
                else math.ceil(meta.wire_size / meta.chunk_size)
            ),
        )
        record.set_state("receiving")
        with self._lock:
            self._incoming = _IncomingState(
                meta=meta,
                record=record,
                wire_path=wire_path,
                received={},
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
            expected_length = self._expected_chunk_length(
                incoming,
                message.chunk_index,
            )
            if len(message.payload) != expected_length:
                raise FileTransferError(
                    "invalid_chunk",
                    (
                        f"chunk {message.chunk_index} length {len(message.payload)} "
                        f"does not match expected {expected_length}"
                    ),
                    phase="receiving",
                )
            offset = message.chunk_index * incoming.meta.chunk_size
            if message.chunk_index in incoming.received:
                with incoming.wire_path.open("rb") as file:
                    file.seek(offset)
                    existing = file.read(expected_length)
                if existing != message.payload:
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

            with incoming.wire_path.open("r+b") as file:
                file.seek(offset)
                file.write(message.payload)
                file.flush()
            incoming.received[message.chunk_index] = len(message.payload)
            bytes_completed = sum(incoming.received.values())
            incoming.record.set_progress(
                bytes_completed=bytes_completed,
                chunks_completed=len(incoming.received),
            )
        except FileTransferError as exc:
            self._fail_incoming(incoming, exc)

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
        try:
            if message.chunk_count != record.chunks_total:
                raise FileTransferError(
                    "missing_chunks",
                    (
                        f"END chunk_count={message.chunk_count} does not match "
                        f"expected {record.chunks_total}"
                    ),
                    phase="verifying",
                )
            missing = [
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
                final_temp.unlink(missing_ok=True)
                raise FileTransferError(
                    "original_hash_mismatch",
                    "original file SHA-256 mismatch",
                    phase="verifying",
                )

            destination = _unique_destination(
                self.receive_dir,
                incoming.record.filename,
            )
            os.replace(final_temp, destination)
            record.rx_end = message
            if final_temp != incoming.wire_path:
                incoming.wire_path.unlink(missing_ok=True)

            # Hold the session transfer lease until RESULT itself reaches
            # link-level settlement, so manual USER traffic cannot interleave
            # with the receiver's final application acknowledgement.
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
                        temporary.write(block)
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
        incoming.wire_path.unlink(missing_ok=True)
        with self._lock:
            if self._incoming is incoming:
                self._incoming = None
        # A claimed incoming transfer keeps session ownership through
        # failure RESULT settlement for the same ordering reason as success.
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
            self._rx_queue.put(_CancelIncoming(parsed))
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
        self._rx_queue.put(None)
        self._rx_thread.join(timeout=1.0)
        with self._lock:
            incoming = self._incoming
            self._incoming = None
        if incoming is not None:
            incoming.wire_path.unlink(missing_ok=True)
