from __future__ import annotations

from collections import deque
import os
import queue
import math
from pathlib import Path
import threading
import time
from typing import Any

from . import core
from .protocol import (
    DataMessage,
    EndMessage,
    FileProtocolError,
    MetaMessage,
    ResultMessage,
    ResumeMessage,
    data_payload_capacity,
    decode_message,
    encode_message,
    transfer_id_text,
)
from .resume_store import ResumeStateStore
from .transport import BinaryUserCancelled, BinaryUserError, BinaryUserTransport


FILE_LOCAL_RECOVERY_TIMEOUT_S = 60.0
FILE_LOCAL_RECOVERY_RETRY_S = 0.25
FILE_RESUME_HANDSHAKE_TIMEOUT_S = 3.0
FILE_RESUME_CHECKPOINT_CHUNKS = 32
FILE_RESUME_CHECKPOINT_S = 1.0
_RECOVERABLE_BINARY_ERRORS = frozenset(
    {"local_tx_unknown", "local_disconnect", "local_controller_reset"}
)


"""FT1 with bounded controller recovery and durable process-restart resume."""

def initialize(
    self,
    transport: BinaryUserTransport,
    *,
    local_recovery_timeout_s: float = FILE_LOCAL_RECOVERY_TIMEOUT_S,
    local_recovery_retry_s: float = FILE_LOCAL_RECOVERY_RETRY_S,
    resume_handshake_timeout_s: float = FILE_RESUME_HANDSHAKE_TIMEOUT_S,
    resume_checkpoint_chunks: int = FILE_RESUME_CHECKPOINT_CHUNKS,
    resume_checkpoint_s: float = FILE_RESUME_CHECKPOINT_S,
    **kwargs: Any,
) -> None:
    if local_recovery_timeout_s <= 0 or local_recovery_retry_s <= 0:
        raise ValueError("local recovery timing must be positive")
    if resume_handshake_timeout_s <= 0:
        raise ValueError("resume_handshake_timeout_s must be positive")
    if resume_checkpoint_chunks <= 0 or resume_checkpoint_s <= 0:
        raise ValueError("resume checkpoint policy must be positive")
    self.local_recovery_timeout_s = float(local_recovery_timeout_s)
    self.local_recovery_retry_s = float(local_recovery_retry_s)
    self.resume_handshake_timeout_s = float(resume_handshake_timeout_s)
    self.resume_checkpoint_chunks = int(resume_checkpoint_chunks)
    self.resume_checkpoint_s = float(resume_checkpoint_s)
    self._suspended_ids: deque[int] = deque(maxlen=32)
    core.FileTransferManager.__init__(self, transport, **kwargs)
    self._resume_store = ResumeStateStore(
        self.receive_dir / ".serialterminal-state"
    )

# TODO_035: same-process local controller recovery -----------------

def _send_message_direct(self, message, *, cancel_event, deadline=None) -> None:
    payload = encode_message(message, self.transport.payload_capacity)
    fields = self._message_event_fields(message)
    with self._lock:
        record = self._records.get(message.transfer_id)
    if record is not None:
        record.event("binary_send_start", **fields)

    caller_deadline = deadline
    recovery_deadline = None
    attempts = 0
    previous_state = None
    while True:
        if self._stopping.is_set():
            raise core.FileTransferError("local_shutdown", "file manager is closing")
        self._check_remote_failure(record)
        self._check_send_deadline(caller_deadline)
        deadline = recovery_deadline
        if caller_deadline is not None:
            deadline = caller_deadline if deadline is None else min(deadline, caller_deadline)
        try:
            if deadline is not None and time.monotonic() >= deadline:
                raise core.FileTransferError(
                    "local_recovery_timeout",
                    "local controller did not recover before FT1 recovery deadline",
                    phase="recovering_local_node",
                )
            send_until = getattr(self.transport, "send_binary_until", None)
            if deadline is not None and callable(send_until):
                send_until(payload, deadline=deadline, cancel_event=cancel_event)
            else:
                self.transport.send_binary(payload, cancel_event=cancel_event)
        except BinaryUserCancelled as exc:
            raise core.FileTransferCancelled(str(exc)) from exc
        except BinaryUserError as exc:
            self._check_send_deadline(caller_deadline)
            if exc.code not in _RECOVERABLE_BINARY_ERRORS:
                self._raise_binary_failure(record, fields, exc, attempts)
            now = time.monotonic()
            if recovery_deadline is None:
                recovery_deadline = now + self.local_recovery_timeout_s
                if record is not None:
                    previous_state = record.snapshot()["state"]
                    record.set_state("recovering_local_node")
                    record.event(
                        "local_recovery_started",
                        **fields,
                        reason=exc.code,
                        timeout_s=self.local_recovery_timeout_s,
                    )
            deadline = recovery_deadline if caller_deadline is None else min(recovery_deadline, caller_deadline)
            if now >= deadline:
                if record is not None:
                    record.event(
                        "local_recovery_failed",
                        **fields,
                        reason=exc.code,
                        attempts=attempts,
                    )
                raise core.FileTransferError(
                    "local_recovery_timeout",
                    "local controller did not recover before FT1 recovery deadline",
                    phase="recovering_local_node",
                    details={"binary_error": exc.code, "attempts": attempts},
                ) from exc
            attempts += 1
            if record is not None:
                record.event(
                    "binary_send_replay",
                    **fields,
                    reason=exc.code,
                    attempt=attempts,
                )
            self._recovery_pause(cancel_event, deadline, record=record)
            continue

        if record is not None:
            if recovery_deadline is not None:
                record.event(
                    "local_recovery_resumed", **fields, attempts=attempts
                )
                if previous_state is not None:
                    record.set_state(previous_state)
            record.event(
                "binary_send_settled", **fields, local_replays=attempts
            )
        return

def _raise_binary_failure(self, record, fields, exc, attempts) -> None:
    if record is not None:
        record.event(
            "binary_send_failed",
            **fields,
            binary_error=exc.code,
            local_replays=attempts,
        )
    raise core.FileTransferError(
        "binary_send_failed",
        exc.message,
        phase="sending",
        details={"binary_error": exc.code, "local_replays": attempts},
    ) from exc

def _recovery_pause(self, cancel_event, deadline: float, *, record=None) -> None:
    wait_s = min(self.local_recovery_retry_s, max(0.0, deadline - time.monotonic()))
    if record is not None:
        self._check_remote_failure(record)
        with record._condition:
            if cancel_event is not None and cancel_event.is_set():
                raise core.FileTransferCancelled()
            if not record.remote_failure_event.is_set():
                record._condition.wait(timeout=wait_s)
        self._check_remote_failure(record)
    elif cancel_event is not None:
        if cancel_event.wait(timeout=wait_s):
            raise core.FileTransferCancelled()
    else:
        time.sleep(wait_s)

# TODO_036: durable receiver state ---------------------------------

def _checkpoint_incoming(
    self,
    incoming,
    *,
    status: str | None = None,
    force: bool = False,
    end: EndMessage | None = None,
    destination: Path | None = None,
) -> None:
    now = time.monotonic()
    previous_count = int(getattr(incoming, "_checkpoint_count", 0))
    previous_time = float(getattr(incoming, "_checkpoint_time", 0.0))
    if not force:
        chunk_due = len(incoming.received) - previous_count >= self.resume_checkpoint_chunks
        time_due = now - previous_time >= self.resume_checkpoint_s
        if not chunk_due and not time_due:
            return
    persistent_status = status or getattr(
        incoming, "_persistent_status", "receiving"
    )
    if persistent_status == "publishing":
        end = end or getattr(incoming, "_publishing_end", None)
        destination = destination or getattr(incoming, "_publishing_destination", None)
    self._resume_store.save_incoming(
        meta=incoming.meta,
        received=incoming.received,
        status=persistent_status,
        end=end,
        destination=destination,
    )
    incoming._checkpoint_count = len(incoming.received)
    incoming._checkpoint_time = now
    incoming._persistent_status = persistent_status

def _load_received(self, meta: MetaMessage, payload: dict[str, Any]):
    chunks_total = self._chunk_count(meta)
    return self._resume_store.received_from_ranges(
        meta,
        chunks_total,
        payload.get("received_ranges"),
    )

def _chunk_count(meta: MetaMessage) -> int:
    return 0 if meta.wire_size == 0 else math.ceil(meta.wire_size / meta.chunk_size)

def _earliest_missing(incoming) -> int:
    for index in range(incoming.record.chunks_total):
        if index not in incoming.received:
            return index
    return incoming.record.chunks_total

def _restore_incoming(self, meta: MetaMessage, *, existing=None):
    loaded = self._resume_store.load_incoming(meta.transfer_id)
    if loaded is None:
        return None
    payload, stored_meta = loaded
    if stored_meta != meta or payload.get("status") not in {"receiving", "suspended", "publishing"}:
        return None

    if payload.get("status") == "publishing":
        if self._reconcile_published(meta, payload):
            return "completed"

    part = self._resume_store.incoming_part(meta.transfer_id)
    received = self._load_received(meta, payload)
    if received is None or not part.is_file():
        return None

    with self._lock:
        if self._active_id is not None or self._stopping.is_set():
            return None
        if self._records.get(meta.transfer_id) is not existing:
            return None
        record = existing or core._TransferRecord(
            meta.transfer_id, direction="RX", filename=core.safe_received_filename(meta.filename),
            event_retention=self.event_retention, event_sink=self.event_sink,
        )
        self._active_id = meta.transfer_id
    claimed = False
    try:
        incoming = core._IncomingState(
            meta=meta, record=record, wire_path=part, received=received,
            last_activity_monotonic=time.monotonic(),
        )
        incoming._persistent_status = "receiving"
        destination_text = payload.get("destination")
        if payload.get("status") == "publishing" and isinstance(destination_text, str):
            destination = Path(destination_text)
            if self._valid_publishing_destination(destination):
                incoming._publishing_destination = destination
                incoming._publishing_end = self._resume_store.end_from_json(payload.get("end"), meta.transfer_id)
                incoming._persistent_status = "publishing"
        self._claim(record.transfer_id, record.direction)
        claimed = True
        if self._stopping.is_set():
            raise core.FileTransferError("local_shutdown", "manager closed during RX restore")
        self._checkpoint_incoming(incoming, force=True)
        if self._stopping.is_set():
            raise core.FileTransferError("local_shutdown", "manager closed during RX checkpoint")
        # Только успешные claim и checkpoint публикуют новое runtime state.
        with self._lock:
            if self._stopping.is_set():
                raise core.FileTransferError("local_shutdown", "manager closed during RX restore")
            self._restart_record(record, "receiving")
            with record._condition:
                record.rx_meta = meta
                record.original_bytes = meta.original_size
                record.wire_bytes = meta.wire_size
                record.chunks_total = self._chunk_count(meta)
                record.bytes_completed = sum(received.values())
                record.chunks_completed = len(received)
            self._records[meta.transfer_id] = record
            self._incoming = incoming
            while meta.transfer_id in self._terminal_order:
                self._terminal_order.remove(meta.transfer_id)
            try:
                self._suspended_ids.remove(meta.transfer_id)
            except ValueError:
                pass
    except Exception:
        try:
            if claimed:
                self._release(record.transfer_id, record.direction)
        except Exception as exc:
            # Не выдаём admission заново, если rollback lease не подтверждён.
            with self._lock:
                self._records[meta.transfer_id] = record
            failure = core.FileTransferError(
                "local_ownership_unsettled", str(exc), phase="resuming",
            )
            record.event("resume_rollback_failed", error=str(exc))
            if existing is None:
                record.terminal("failed", failure=failure)
            raise failure from exc
        with self._lock:
            if self._active_id == meta.transfer_id:
                self._active_id = None
        raise
    record.event(
        "resume_state_restored",
        chunks=len(received),
        next_chunk=self._earliest_missing(incoming),
    )
    return incoming

def _valid_publishing_destination(self, destination: Path) -> bool:
    return not destination.is_symlink() and destination.parent.resolve() == self.receive_dir.resolve()

def _reconcile_published(self, meta: MetaMessage, payload: dict[str, Any]) -> bool:
    destination_text = payload.get("destination")
    end = self._resume_store.end_from_json(payload.get("end"), meta.transfer_id)
    if not isinstance(destination_text, str) or end is None:
        return False
    destination = Path(destination_text)
    try:
        if not destination.is_file():
            return False
        if destination.stat().st_size != meta.original_size:
            return False
        if core._sha256_file(destination) != meta.original_sha256:
            return False
    except OSError:
        return False
    with destination.open("rb") as handle:
        os.fsync(handle.fileno())
    self._fsync_directory(destination.parent)
    self._resume_store.save_completed(
        meta=meta,
        end=end,
        final_path=destination,
    )
    self._resume_store.delete_incoming(meta.transfer_id, delete_part=True)
    return True

def _completed_matches_meta(self, meta: MetaMessage) -> bool:
    value = self._resume_store.load_completed(meta.transfer_id)
    if value is None:
        return False
    if self._resume_store.meta_from_json(value.get("meta"), meta.transfer_id) != meta:
        return False
    path_text = value.get("final_path")
    if not isinstance(path_text, str):
        return False
    path = Path(path_text)
    try:
        valid = (
            path.is_file()
            and path.stat().st_size == meta.original_size
            and core._sha256_file(path) == meta.original_sha256
        )
        end = self._resume_store.end_from_json(value.get("end"), meta.transfer_id)
        if not valid or end is None:
            return False
    except OSError:
        return False
    try:
        # После ошибки fsync файл/journal может быть виден только в cache.
        # Replay OK повторно закрепляет commit, не публикуя новый destination.
        with path.open("rb") as handle:
            os.fsync(handle.fileno())
        self._fsync_directory(path.parent)
        self._resume_store.save_completed(meta=meta, end=end, final_path=path)
        return True
    except OSError as exc:
        raise core.FileTransferError(
            "storage_failed", f"could not persist completed replay: {exc}", phase="publishing",
        ) from exc

def _send_resume(self, incoming) -> None:
    # RESUME утверждает durable progress, а не только наличие bytes в RAM.
    # Отказ checkpoint не должен выпустить неподтверждённый cursor.
    self._checkpoint_incoming(incoming, force=True)
    next_chunk = self._earliest_missing(incoming)
    incoming.record.event("resume_requested", next_chunk=next_chunk)
    try:
        self._send_message(
            ResumeMessage(incoming.record.transfer_id, next_chunk),
            cancel_event=incoming.record.cancel_event,
        )
    except Exception as exc:
        incoming.record.event("resume_delivery_failed", error=str(exc))

def _handle_meta(self, meta: MetaMessage) -> None:
    retained = self._resume_store.load_incoming(meta.transfer_id)
    if retained is not None and retained[0].get("status") == "quarantined":
        self._reject_incoming(
            meta.transfer_id, "invalid_chunk", "retained transfer is quarantined"
        )
        return
    with self._lock:
        existing = self._records.get(meta.transfer_id)
        active = self._active_id
        incoming = self._incoming

    if existing is not None:
        if existing.direction == "RX" and existing.rx_meta == meta:
            if existing.state == "completed":
                self._send_result_async(
                    existing, ResultMessage(meta.transfer_id, True, "ok", "")
                )
                return
            if incoming is not None and incoming.record is existing:
                self._touch_incoming(incoming)
                existing.event("meta_replayed")
                self._send_resume(incoming)
                return
            if existing.state == "suspended":
                restored = self._restore_incoming(meta, existing=existing)
                if restored == "completed":
                    self._send_result_async(
                        existing,
                        ResultMessage(meta.transfer_id, True, "ok", ""),
                    )
                    return
                if restored is not None:
                    self._send_resume(restored)
                    return
        self._reject_incoming(
            meta.transfer_id,
            "protocol_error",
            "conflicting META for existing transfer_id",
        )
        return

    try:
        completed = self._completed_matches_meta(meta)
    except core.FileTransferError as exc:
        self._reject_incoming(meta.transfer_id, exc.code, exc.message)
        return
    if completed:
        self._send_result_async(
            None, ResultMessage(meta.transfer_id, True, "ok", "")
        )
        return
    if active is not None:
        self._reject_incoming(meta.transfer_id, "busy", "another file transfer is active")
        return

    restored = self._restore_incoming(meta)
    if restored == "completed":
        self._send_result_async(
            None, ResultMessage(meta.transfer_id, True, "ok", "")
        )
        return
    if restored is not None:
        self._send_resume(restored)
        return
    self._start_new_incoming(meta)

def _start_new_incoming(self, meta: MetaMessage) -> None:
    part = self._resume_store.incoming_part(meta.transfer_id)
    created = False
    try:
        filename = core.safe_received_filename(meta.filename)
        if not 1 <= meta.chunk_size <= data_payload_capacity(self.transport.payload_capacity):
            raise core.FileTransferError(
                "invalid_metadata",
                "remote chunk size exceeds local binary transport capacity",
                phase="receiving",
            )
        if self._resume_store.incoming_manifest(meta.transfer_id).exists() or part.exists():
            raise core.FileTransferError(
                "storage_failed",
                "stale/corrupt durable resume state already exists for transfer_id",
                phase="receiving",
            )
        with part.open("xb"):
            pass
        created = True
        record = self._reserve_record(
            meta.transfer_id, direction="RX", filename=filename
        )
    except core.FileTransferError as exc:
        if created:
            part.unlink(missing_ok=True)
        self._reject_incoming(meta.transfer_id, exc.code, exc.message)
        return
    except OSError as exc:
        if created:
            part.unlink(missing_ok=True)
        self._reject_incoming(meta.transfer_id, "storage_failed", str(exc))
        return

    record.rx_meta = meta
    record.set_sizes(
        original_bytes=meta.original_size,
        wire_bytes=meta.wire_size,
        chunks_total=self._chunk_count(meta),
    )
    record.set_state("receiving")
    incoming = core._IncomingState(
        meta=meta,
        record=record,
        wire_path=part,
        received={},
        last_activity_monotonic=time.monotonic(),
    )
    incoming._checkpoint_count = 0
    incoming._checkpoint_time = 0.0
    incoming._persistent_status = "receiving"
    with self._lock:
        self._incoming = incoming
    self._checkpoint_incoming(incoming, force=True)
    self._send_resume(incoming)

def _handle_data(self, message: DataMessage) -> None:
    incoming = self._incoming_for(message.transfer_id)
    before = len(incoming.received) if incoming is not None else 0
    core.FileTransferManager._handle_data(self, message)
    current = self._incoming_for(message.transfer_id)
    if current is not None and len(current.received) > before:
        self._checkpoint_incoming(current)

def _suspend_incoming(self, incoming, *, reason: str) -> None:
    self._checkpoint_incoming(incoming, status="suspended", force=True)
    if reason == "manager_close" and not self._outbox.wait_idle(1.0):
        incoming.record.event("local_tx_drain_failed", code="local_ownership_unsettled")
        incoming.record.terminal("failed", failure=core.FileTransferError("local_ownership_unsettled", "outbound worker still owns operation", phase="settling"))
        return
    with self._lock:
        if self._incoming is incoming:
            self._incoming = None
        if self._active_id == incoming.record.transfer_id:
            self._active_id = None
        self._suspended_ids.append(incoming.record.transfer_id)
    incoming.record.set_state("suspended")
    incoming.record.event("transfer_suspended", reason=reason)
    self._release(incoming.record.transfer_id, incoming.record.direction)

def _expire_stale_incoming(self) -> None:
    with self._lock:
        incoming = self._incoming
    if incoming is None:
        return
    if time.monotonic() - incoming.last_activity_monotonic >= self.incoming_idle_timeout_s:
        self._suspend_incoming(incoming, reason="remote_sender_timeout")

def _fail_incoming(self, incoming, failure, *, terminal_state="failed") -> None:
    if getattr(incoming, "_publication_committed", False):
        # Потеря локального RESULT после durable commit не отменяет файл.
        # META/END replay получит OK из tombstone без второй публикации.
        incoming.record.event("result_delivery_failed", code=failure.code, error=str(failure))
        incoming.record.rx_end = incoming._publishing_end
        with self._lock:
            if self._incoming is incoming:
                self._incoming = None
        self._terminal_record(incoming.record, "completed", final_path=incoming._publishing_destination)
        self._cleanup_published(incoming)
        return
    if terminal_state == "cancelled":
        self._resume_store.delete_incoming(
            incoming.record.transfer_id, delete_part=False
        )
    elif getattr(incoming, "_publishing_destination", None) is None:
        if failure.code in {
            "wire_hash_mismatch", "original_hash_mismatch", "decompression_failed"
        }:
            incoming._quarantined = True
        status = "quarantined" if getattr(incoming, "_quarantined", False) else "suspended"
        try:
            self._checkpoint_incoming(incoming, status=status, force=True)
        except Exception as exc:
            incoming.record.event("checkpoint_failed", error=str(exc), reason=failure.code)
    core.FileTransferManager._fail_incoming(self,
        incoming, failure, terminal_state=terminal_state
    )

def _handle_end(self, message: EndMessage) -> None:
    incoming = self._incoming_for(message.transfer_id)
    if incoming is None:
        if self._replay_completed_end(message):
            return
        core.FileTransferManager._handle_end(self, message)
        return

    if message.chunk_count != incoming.record.chunks_total:
        core.FileTransferManager._handle_end(self, message)
        return
    if self._missing_indexes(incoming):
        core.FileTransferManager._handle_end(self, message)
        if self._incoming_for(message.transfer_id) is not None:
            self._checkpoint_incoming(incoming, force=True)
        return

    core.FileTransferManager._handle_end(self, message)

def _publish_verified(self, incoming, end: EndMessage, final_temp: Path) -> Path:
    with final_temp.open("rb") as handle:
        os.fsync(handle.fileno())
    destination = getattr(incoming, "_publishing_destination", None)
    if destination is None:
        destination = core._unique_destination(self.receive_dir, incoming.record.filename)
    # Один destination связывает intent, rename и tombstone. После intent
    # не выбираем другое имя даже при прерывании попытки.
    incoming._publishing_destination = destination
    incoming._publishing_end = end
    self._checkpoint_incoming(
        incoming, status="publishing", force=True, end=end, destination=destination,
    )
    if destination.exists() or destination.is_symlink():
        raise core.FileTransferError(
            "storage_failed", "publishing destination is already occupied", phase="publishing",
        )
    os.replace(final_temp, destination)
    self._fsync_directory(destination.parent)
    self._resume_store.save_completed(meta=incoming.meta, end=end, final_path=destination)
    incoming._publication_committed = True
    return destination

def _cleanup_published(self, incoming) -> None:
    try:
        self._resume_store.delete_incoming(incoming.meta.transfer_id, delete_part=True)
    except OSError as exc:
        incoming.record.event("publication_cleanup_failed", error=str(exc))

def _missing_indexes(incoming) -> list[int]:
    return [
        index
        for index in range(incoming.record.chunks_total)
        if index not in incoming.received
    ]

def _replay_completed_end(self, message: EndMessage) -> bool:
    value = self._resume_store.load_completed(message.transfer_id)
    if value is None:
        return False
    stored = self._resume_store.end_from_json(value.get("end"), message.transfer_id)
    if stored != message:
        return False
    self._send_result_async(
        None, ResultMessage(message.transfer_id, True, "ok", "")
    )
    return True

# TODO_037: persistent sender identity + resume handshake -----------

def _sender_resume_candidate(self, path: Path) -> dict[str, Any] | None:
    for value in self._resume_store.find_outgoing_for_source(path):
        try:
            expected_size = int(value["original_size"])
            expected_hash = bytes.fromhex(str(value["original_sha256"]))
            transfer_id = int(str(value["transfer_id"]), 16)
        except (KeyError, TypeError, ValueError):
            continue
        try:
            if path.stat().st_size != expected_size:
                continue
            if core._sha256_file(path) != expected_hash:
                continue
        except OSError:
            continue
        candidate = dict(value)
        candidate["parsed_transfer_id"] = transfer_id
        return candidate
    return None

def start_send(self, local_path: str | Path) -> dict[str, Any]:
    path = Path(local_path).expanduser()
    if not path.exists():
        raise core.FileTransferError(
            "file_not_found", f"local file does not exist: {path}", phase="preparing"
        )
    if not path.is_file():
        raise core.FileTransferError(
            "not_a_file", f"local path is not a regular file: {path}", phase="preparing"
        )
    candidate = self._sender_resume_candidate(path)
    with self._lock:
        transfer_id = (
            int(candidate["parsed_transfer_id"])
            if candidate is not None
            else self._new_transfer_id_locked()
        )
        existing = self._records.get(transfer_id)
        if existing is not None and (candidate is None or existing.direction != "TX" or existing.state != "failed"):
            candidate = None
            existing = None
            transfer_id = self._new_transfer_id_locked()
    record = self._reserve_record(
        transfer_id, direction="TX", filename=path.name, resume_existing=existing,
    )
    record._resuming_persistent = candidate is not None
    if candidate is not None:
        record.event("sender_resume_journal_restored")
    thread = threading.Thread(
        target=self._send_worker,
        args=(record, path),
        name=f"serialterminal-file-tx-{transfer_id_text(transfer_id)}",
        daemon=True,
    )
    record._thread = thread
    try:
        thread.start()
    except Exception as exc:
        if not thread.is_alive():
            record._thread = None
        failure = core.FileTransferError("local_failure", str(exc), phase="preparing")
        self._terminal_record(record, "failed", failure=failure)
        raise failure from exc
    result = record.snapshot()
    result["events"] = {
        "cursor": 0,
        "max_window": core.FILE_MAX_WINDOW,
        "retention": self.event_retention,
    }
    if candidate is not None:
        result["resumed"] = True
    return result

def _save_sender_journal(self, record, prepared, chunk_size: int) -> None:
    self._resume_store.save_outgoing(
        record.transfer_id,
        {
            "status": "active",
            "source_path": str(prepared.source_path.resolve()),
            "filename": prepared.filename,
            "original_size": prepared.original_size,
            "original_sha256": prepared.original_sha256.hex(),
            "wire_size": prepared.wire_size,
            "wire_sha256": prepared.wire_sha256.hex(),
            "compression": int(prepared.compression),
            "chunk_size": chunk_size,
        },
    )

def feed_binary(self, payload: bytes) -> None:
    try:
        message = decode_message(payload)
    except FileProtocolError:
        return
    if isinstance(message, ResumeMessage):
        with self._lock:
            record = self._records.get(message.transfer_id)
        if record is not None and record.direction == "TX":
            with record._condition:
                record.remote_resume = message
                record._condition.notify_all()
            record.event("remote_resume", next_chunk=message.next_chunk)
        return
    core.FileTransferManager.feed_binary(self, payload)

def _await_resume(self, record, chunk_count: int):
    deadline = time.monotonic() + self.resume_handshake_timeout_s
    with record._condition:
        while True:
            if record.cancel_event.is_set():
                raise core.FileTransferCancelled()
            if record.remote_result is not None:
                return 0, record.remote_result
            resume = getattr(record, "remote_resume", None)
            if resume is not None:
                record.remote_resume = None
                if not 0 <= resume.next_chunk <= chunk_count:
                    raise core.FileTransferError(
                        "invalid_resume_request",
                        "receiver RESUME cursor exceeds declared chunk_count",
                        phase="resuming",
                    )
                return resume.next_chunk, None
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                record.event("resume_handshake_fallback", next_chunk=0)
                return 0, None
            record._condition.wait(timeout=remaining)

def _send_chunks_from(self, record, prepared, chunk_size: int, start: int) -> None:
    if not 0 <= start <= record.chunks_total:
        raise core.FileTransferError(
            "invalid_resume_request", "resume cursor outside prepared stream"
        )
    sent_bytes = min(prepared.wire_size, start * chunk_size)
    record.set_progress(bytes_completed=sent_bytes, chunks_completed=start)
    with prepared.wire_path.open("rb") as source:
        source.seek(start * chunk_size)
        for index in range(start, record.chunks_total):
            if record.cancel_event.is_set():
                raise core.FileTransferCancelled()
            block = source.read(chunk_size)
            if not block:
                raise core.FileTransferError(
                    "local_failure", "prepared wire stream ended early"
                )
            self._send_message(
                DataMessage(record.transfer_id, index, block),
                cancel_event=record.cancel_event,
            )
            sent_bytes += len(block)
            record.set_progress(
                bytes_completed=sent_bytes, chunks_completed=index + 1
            )

def _send_worker(self, record, path: Path) -> None:
    prepared = None
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
        self._save_sender_journal(record, prepared, chunk_size)
        meta = MetaMessage(
            record.transfer_id,
            prepared.filename,
            prepared.original_size,
            prepared.wire_size,
            prepared.compression,
            chunk_size,
            prepared.original_sha256,
        )
        end = EndMessage(
            record.transfer_id, chunks_total, prepared.wire_sha256
        )
        record.set_state("sending")
        self._send_message(meta, cancel_event=record.cancel_event)
        start, early_result = self._await_resume(record, chunks_total)
        if early_result is not None:
            self._finish_early_result(record, early_result)
            return
        if start:
            record.set_state("resuming")
            record.event("resume_started", next_chunk=start)
        self._send_chunks_from(record, prepared, chunk_size, start)
        self._send_message(end, cancel_event=record.cancel_event)
        result = self._await_remote_completion(
            record,
            prepared,
            meta=meta,
            end=end,
            chunk_size=chunk_size,
        )
        if not result.ok:
            raise core.FileTransferError(
                "remote_failed",
                result.reason or result.code,
                phase="waiting_result",
                details={"remote_code": result.code},
            )
        self._resume_store.delete_outgoing(record.transfer_id)
        self._terminal_record(record, "completed")
    except core.FileTransferCancelled as exc:
        self._handle_sender_cancel(record, exc)
    except core.FileTransferError as exc:
        self._terminal_record(record, "failed", failure=exc)
    except Exception as exc:
        self._terminal_record(
            record,
            "failed",
            failure=core.FileTransferError(
                "local_failure", str(exc), phase=record.state
            ),
        )
    finally:
        if prepared is not None and prepared.remove_wire_path:
            prepared.wire_path.unlink(missing_ok=True)

def _finish_early_result(self, record, result: ResultMessage) -> None:
    if not result.ok:
        raise core.FileTransferError(
            "remote_failed",
            result.reason or result.code,
            phase="resuming",
        )
    self._resume_store.delete_outgoing(record.transfer_id)
    self._terminal_record(record, "completed")

def _handle_sender_cancel(self, record, exc) -> None:
    if getattr(record, "_shutdown_suspend", False):
        self._terminal_record(
            record,
            "failed",
            failure=core.FileTransferError(
                "local_shutdown",
                "SerialTerminal stopped with resumable outgoing transfer retained",
                phase=record.state,
            ),
        )
    else:
        self._resume_store.delete_outgoing(record.transfer_id)
        self._terminal_record(record, "cancelled", failure=exc)

# lifecycle / display ------------------------------------------------

def display_snapshot(self):
    snapshot = core.FileTransferManager.display_snapshot(self)
    if snapshot is not None:
        return snapshot
    with self._lock:
        while self._suspended_ids:
            record = self._records.get(self._suspended_ids[-1])
            if record is not None:
                return record.snapshot()
            self._suspended_ids.pop()
    return None

def close(self) -> None:
    self._stopping.set()
    self._outbox.discard_pending()
    self.transport.set_receiver(None)
    with self._lock:
        incoming = self._incoming
        active = (
            self._records.get(self._active_id)
            if self._active_id is not None
            else None
        )
    if incoming is not None:
        self._suspend_incoming(incoming, reason="manager_close")
    if active is not None and active.direction == "TX":
        active._shutdown_suspend = True
        active.cancel_event.set()
    try:
        self._rx_queue.put_nowait(None)
    except queue.Full:
        pass
    self._rx_thread.join(timeout=1.0)
    self._outbox.close(1.0)
    self.join_all(1.0)
    shutdown = getattr(self.transport, "close", None)
    if callable(shutdown):
        shutdown()
