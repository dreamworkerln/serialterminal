from __future__ import annotations

from collections import deque
import json
import math
import os
from pathlib import Path
import threading
import time
from typing import Any

from . import core
from .protocol import (
    Compression,
    DataMessage,
    EndMessage,
    FileProtocolError,
    MetaMessage,
    MissingMessage,
    ResultMessage,
    ResumeMessage,
    canonical_missing_ranges,
    data_payload_capacity,
    decode_message,
    encode_message,
    transfer_id_text,
)
from .transport import BinaryUserCancelled, BinaryUserError, BinaryUserTransport


FILE_LOCAL_RECOVERY_TIMEOUT_S = 60.0
FILE_LOCAL_RECOVERY_RETRY_S = 0.25
FILE_RESUME_HANDSHAKE_TIMEOUT_S = 3.0
FILE_RESUME_CHECKPOINT_CHUNKS = 32
FILE_RESUME_CHECKPOINT_S = 1.0
FILE_RESUME_STATE_TTL_S = 7 * 24 * 3600.0
FILE_RESUME_MAX_INCOMING = 32
FILE_RESUME_MAX_OUTGOING = 32
FILE_RESUME_MAX_COMPLETED = 64
FILE_RESUME_MAX_PART_BYTES = 1024 * 1024 * 1024
_STATE_SCHEMA = 1
_RECOVERABLE_BINARY_ERRORS = frozenset(
    {"local_tx_unknown", "local_disconnect", "local_controller_reset"}
)


class FileTransferManager(core.FileTransferManager):
    """FT1 manager with bounded local recovery and durable process-restart resume.

    The wire remains an application protocol over opaque reliable BINARY USER.
    Firmware ACK semantics are untouched. Persistent resume uses a receiver-proven
    earliest-missing FT1 chunk, then preserves the existing END/MISSING/RESULT
    selective repair path for exact completion.
    """

    def __init__(
        self,
        transport: BinaryUserTransport,
        *,
        local_recovery_timeout_s: float = FILE_LOCAL_RECOVERY_TIMEOUT_S,
        local_recovery_retry_s: float = FILE_LOCAL_RECOVERY_RETRY_S,
        resume_handshake_timeout_s: float = FILE_RESUME_HANDSHAKE_TIMEOUT_S,
        resume_checkpoint_chunks: int = FILE_RESUME_CHECKPOINT_CHUNKS,
        resume_checkpoint_s: float = FILE_RESUME_CHECKPOINT_S,
        resume_state_ttl_s: float = FILE_RESUME_STATE_TTL_S,
        **kwargs: Any,
    ) -> None:
        if local_recovery_timeout_s <= 0:
            raise ValueError("local_recovery_timeout_s must be positive")
        if local_recovery_retry_s <= 0:
            raise ValueError("local_recovery_retry_s must be positive")
        if resume_handshake_timeout_s <= 0:
            raise ValueError("resume_handshake_timeout_s must be positive")
        if resume_checkpoint_chunks <= 0:
            raise ValueError("resume_checkpoint_chunks must be positive")
        if resume_checkpoint_s <= 0:
            raise ValueError("resume_checkpoint_s must be positive")
        if resume_state_ttl_s <= 0:
            raise ValueError("resume_state_ttl_s must be positive")

        self.local_recovery_timeout_s = float(local_recovery_timeout_s)
        self.local_recovery_retry_s = float(local_recovery_retry_s)
        self.resume_handshake_timeout_s = float(resume_handshake_timeout_s)
        self.resume_checkpoint_chunks = int(resume_checkpoint_chunks)
        self.resume_checkpoint_s = float(resume_checkpoint_s)
        self.resume_state_ttl_s = float(resume_state_ttl_s)

        super().__init__(transport, **kwargs)
        self._state_root = self.receive_dir / ".serialterminal-state"
        self._incoming_state_dir = self._state_root / "incoming"
        self._outgoing_state_dir = self._state_root / "outgoing"
        self._completed_state_dir = self._state_root / "completed"
        for directory in (
            self._incoming_state_dir,
            self._outgoing_state_dir,
            self._completed_state_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)
        self._cleanup_persistent_state()

    # ------------------------------------------------------------------
    # Generic durable-state helpers

    @staticmethod
    def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(
            f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
        )
        try:
            with temporary.open("w", encoding="utf-8") as handle:
                json.dump(
                    payload,
                    handle,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                )
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any] | None:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return None
        return value if isinstance(value, dict) else None

    def _incoming_manifest_path(self, transfer_id: int) -> Path:
        return self._incoming_state_dir / f"{transfer_id_text(transfer_id)}.json"

    def _incoming_part_path(self, transfer_id: int) -> Path:
        return self._incoming_state_dir / f"{transfer_id_text(transfer_id)}.part"

    def _outgoing_manifest_path(self, transfer_id: int) -> Path:
        return self._outgoing_state_dir / f"{transfer_id_text(transfer_id)}.json"

    def _completed_manifest_path(self, transfer_id: int) -> Path:
        return self._completed_state_dir / f"{transfer_id_text(transfer_id)}.json"

    @staticmethod
    def _meta_json(meta: MetaMessage) -> dict[str, Any]:
        return {
            "filename": meta.filename,
            "original_size": meta.original_size,
            "wire_size": meta.wire_size,
            "compression": int(meta.compression),
            "chunk_size": meta.chunk_size,
            "original_sha256": meta.original_sha256.hex(),
        }

    @staticmethod
    def _meta_from_json(value: Any, transfer_id: int) -> MetaMessage | None:
        if not isinstance(value, dict):
            return None
        try:
            original_hash = bytes.fromhex(str(value["original_sha256"]))
            compression = Compression(int(value["compression"]))
            meta = MetaMessage(
                transfer_id=transfer_id,
                filename=str(value["filename"]),
                original_size=int(value["original_size"]),
                wire_size=int(value["wire_size"]),
                compression=compression,
                chunk_size=int(value["chunk_size"]),
                original_sha256=original_hash,
            )
        except (KeyError, TypeError, ValueError):
            return None
        if len(meta.original_sha256) != 32 or meta.chunk_size <= 0:
            return None
        return meta

    @staticmethod
    def _end_json(end: EndMessage) -> dict[str, Any]:
        return {
            "chunk_count": end.chunk_count,
            "wire_sha256": end.wire_sha256.hex(),
        }

    @staticmethod
    def _end_from_json(value: Any, transfer_id: int) -> EndMessage | None:
        if not isinstance(value, dict):
            return None
        try:
            wire_hash = bytes.fromhex(str(value["wire_sha256"]))
            end = EndMessage(
                transfer_id=transfer_id,
                chunk_count=int(value["chunk_count"]),
                wire_sha256=wire_hash,
            )
        except (KeyError, TypeError, ValueError):
            return None
        if len(end.wire_sha256) != 32:
            return None
        return end

    @staticmethod
    def _received_ranges(received: dict[int, int]) -> list[list[int]]:
        if not received:
            return []
        ordered = sorted(received)
        ranges: list[list[int]] = []
        start = previous = ordered[0]
        for index in ordered[1:]:
            if index == previous + 1:
                previous = index
                continue
            ranges.append([start, previous - start + 1])
            start = previous = index
        ranges.append([start, previous - start + 1])
        return ranges

    @staticmethod
    def _expected_length(meta: MetaMessage, chunks_total: int, index: int) -> int:
        if not 0 <= index < chunks_total:
            raise ValueError("chunk index outside transfer")
        if index < chunks_total - 1:
            return meta.chunk_size
        return meta.wire_size - meta.chunk_size * (chunks_total - 1)

    def _ranges_to_received(
        self,
        meta: MetaMessage,
        ranges: Any,
    ) -> dict[int, int] | None:
        chunks_total = (
            0 if meta.wire_size == 0 else math.ceil(meta.wire_size / meta.chunk_size)
        )
        if ranges is None:
            return {}
        if not isinstance(ranges, list):
            return None
        received: dict[int, int] = {}
        previous_end = 0
        for pair in ranges:
            if (
                not isinstance(pair, list)
                or len(pair) != 2
                or isinstance(pair[0], bool)
                or isinstance(pair[1], bool)
            ):
                return None
            try:
                start, count = int(pair[0]), int(pair[1])
            except (TypeError, ValueError):
                return None
            if start < previous_end or count <= 0 or start + count > chunks_total:
                return None
            for index in range(start, start + count):
                received[index] = self._expected_length(meta, chunks_total, index)
            previous_end = start + count
        return received

    def _cleanup_bucket(self, directory: Path, maximum: int) -> None:
        now = time.time()
        entries: list[tuple[float, Path, dict[str, Any] | None]] = []
        for path in directory.glob("*.json"):
            payload = self._read_json(path)
            try:
                updated = float(payload.get("updated", 0)) if payload else 0.0
            except (TypeError, ValueError):
                updated = 0.0
            if updated <= 0:
                try:
                    updated = path.stat().st_mtime
                except OSError:
                    updated = 0.0
            entries.append((updated, path, payload))
        entries.sort(key=lambda item: item[0], reverse=True)
        for index, (updated, path, _payload) in enumerate(entries):
            if index < maximum and now - updated <= self.resume_state_ttl_s:
                continue
            transfer_text = path.stem
            path.unlink(missing_ok=True)
            if directory == self._incoming_state_dir:
                (directory / f"{transfer_text}.part").unlink(missing_ok=True)

    def _cleanup_persistent_state(self) -> None:
        self._cleanup_bucket(self._incoming_state_dir, FILE_RESUME_MAX_INCOMING)
        self._cleanup_bucket(self._outgoing_state_dir, FILE_RESUME_MAX_OUTGOING)
        self._cleanup_bucket(self._completed_state_dir, FILE_RESUME_MAX_COMPLETED)

        parts: list[tuple[float, Path, int]] = []
        total = 0
        for path in self._incoming_state_dir.glob("*.part"):
            manifest = path.with_suffix(".json")
            if not manifest.exists():
                path.unlink(missing_ok=True)
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            total += stat.st_size
            parts.append((stat.st_mtime, path, stat.st_size))
        if total <= FILE_RESUME_MAX_PART_BYTES:
            return
        parts.sort()
        for _mtime, part, size in parts:
            if total <= FILE_RESUME_MAX_PART_BYTES:
                break
            part.unlink(missing_ok=True)
            part.with_suffix(".json").unlink(missing_ok=True)
            total -= size

    # ------------------------------------------------------------------
    # TODO_035: same-process bounded local controller recovery

    def _send_message(
        self,
        message,
        *,
        cancel_event: threading.Event | None,
    ) -> None:
        payload = encode_message(message, self.transport.payload_capacity)
        fields = self._message_event_fields(message)
        with self._lock:
            record = self._records.get(message.transfer_id)
        if record is not None:
            record.event("binary_send_start", **fields)

        recovery_deadline: float | None = None
        recovery_attempt = 0
        previous_state: str | None = None
        while True:
            try:
                self.transport.send_binary(payload, cancel_event=cancel_event)
                if record is not None:
                    if recovery_deadline is not None:
                        record.event(
                            "local_recovery_resumed",
                            **fields,
                            attempts=recovery_attempt,
                        )
                        if previous_state is not None:
                            record.set_state(previous_state)
                    record.event(
                        "binary_send_settled",
                        **fields,
                        local_replays=recovery_attempt,
                    )
                return
            except BinaryUserCancelled as exc:
                raise core.FileTransferCancelled(str(exc)) from exc
            except BinaryUserError as exc:
                if exc.code not in _RECOVERABLE_BINARY_ERRORS:
                    if record is not None:
                        record.event(
                            "binary_send_failed",
                            **fields,
                            binary_error=exc.code,
                            local_replays=recovery_attempt,
                        )
                    raise core.FileTransferError(
                        "binary_send_failed",
                        exc.message,
                        phase="sending",
                        details={
                            "binary_error": exc.code,
                            "local_replays": recovery_attempt,
                        },
                    ) from exc

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
                if now >= recovery_deadline:
                    if record is not None:
                        record.event(
                            "local_recovery_failed",
                            **fields,
                            reason=exc.code,
                            attempts=recovery_attempt,
                        )
                    raise core.FileTransferError(
                        "local_recovery_timeout",
                        "local controller did not recover before FT1 recovery deadline",
                        phase="recovering_local_node",
                        details={
                            "binary_error": exc.code,
                            "attempts": recovery_attempt,
                            "timeout_seconds": self.local_recovery_timeout_s,
                        },
                    ) from exc

                recovery_attempt += 1
                if record is not None:
                    record.event(
                        "binary_send_replay",
                        **fields,
                        reason=exc.code,
                        attempt=recovery_attempt,
                        recovery_deadline_s=round(
                            max(0.0, recovery_deadline - now), 3
                        ),
                    )
                if cancel_event is not None and cancel_event.wait(
                    timeout=min(
                        self.local_recovery_retry_s,
                        max(0.0, recovery_deadline - now),
                    )
                ):
                    raise core.FileTransferCancelled()
                if cancel_event is None:
                    time.sleep(
                        min(
                            self.local_recovery_retry_s,
                            max(0.0, recovery_deadline - now),
                        )
                    )

    # ------------------------------------------------------------------
    # TODO_036: durable receiver partial state and tombstones

    def _checkpoint_incoming(
        self,
        incoming: core._IncomingState,
        *,
        status: str | None = None,
        force: bool = False,
        end: EndMessage | None = None,
        destination: Path | None = None,
    ) -> None:
        now_mono = time.monotonic()
        last_chunks = int(getattr(incoming, "_checkpoint_chunks", 0))
        last_time = float(getattr(incoming, "_checkpoint_time", 0.0))
        if not force:
            if (
                len(incoming.received) - last_chunks < self.resume_checkpoint_chunks
                and now_mono - last_time < self.resume_checkpoint_s
            ):
                return
        payload: dict[str, Any] = {
            "schema": _STATE_SCHEMA,
            "kind": "incoming",
            "transfer_id": transfer_id_text(incoming.record.transfer_id),
            "status": status or str(getattr(incoming, "_persistent_status", "receiving")),
            "meta": self._meta_json(incoming.meta),
            "received_ranges": self._received_ranges(incoming.received),
            "updated": time.time(),
        }
        if end is not None:
            payload["end"] = self._end_json(end)
        if destination is not None:
            payload["destination"] = str(destination)
        self._atomic_json(
            self._incoming_manifest_path(incoming.record.transfer_id), payload
        )
        incoming._checkpoint_chunks = len(incoming.received)
        incoming._checkpoint_time = now_mono
        incoming._persistent_status = payload["status"]

    def _load_incoming_manifest(
        self,
        transfer_id: int,
    ) -> tuple[dict[str, Any], MetaMessage, dict[int, int]] | None:
        path = self._incoming_manifest_path(transfer_id)
        payload = self._read_json(path)
        if payload is None or payload.get("schema") != _STATE_SCHEMA:
            return None
        if payload.get("transfer_id") != transfer_id_text(transfer_id):
            return None
        meta = self._meta_from_json(payload.get("meta"), transfer_id)
        if meta is None:
            return None
        received = self._ranges_to_received(meta, payload.get("received_ranges"))
        if received is None:
            return None
        return payload, meta, received

    def _completed_tombstone(self, transfer_id: int) -> dict[str, Any] | None:
        payload = self._read_json(self._completed_manifest_path(transfer_id))
        if payload is None or payload.get("schema") != _STATE_SCHEMA:
            return None
        if payload.get("transfer_id") != transfer_id_text(transfer_id):
            return None
        return payload

    def _write_completed_tombstone(
        self,
        record: core._TransferRecord,
        meta: MetaMessage,
        end: EndMessage,
        destination: Path,
    ) -> None:
        self._atomic_json(
            self._completed_manifest_path(record.transfer_id),
            {
                "schema": _STATE_SCHEMA,
                "kind": "completed",
                "transfer_id": transfer_id_text(record.transfer_id),
                "meta": self._meta_json(meta),
                "end": self._end_json(end),
                "final_path": str(destination),
                "updated": time.time(),
            },
        )

    def _completed_matches_meta(
        self,
        transfer_id: int,
        meta: MetaMessage,
    ) -> bool:
        tombstone = self._completed_tombstone(transfer_id)
        if tombstone is None:
            return False
        stored = self._meta_from_json(tombstone.get("meta"), transfer_id)
        if stored != meta:
            return False
        final_raw = tombstone.get("final_path")
        if not isinstance(final_raw, str):
            return False
        final = Path(final_raw)
        try:
            if not final.is_file() or final.stat().st_size != meta.original_size:
                return False
            if core._sha256_file(final) != meta.original_sha256:
                return False
        except (OSError, core.FileTransferError):
            return False
        return True

    def _earliest_missing(self, incoming: core._IncomingState) -> int:
        for index in range(incoming.record.chunks_total):
            if index not in incoming.received:
                return index
        return incoming.record.chunks_total

    def _send_resume(self, incoming: core._IncomingState) -> None:
        next_chunk = self._earliest_missing(incoming)
        incoming.record.event("resume_requested", next_chunk=next_chunk)
        try:
            self._send_message(
                ResumeMessage(
                    transfer_id=incoming.record.transfer_id,
                    next_chunk=next_chunk,
                ),
                cancel_event=incoming.record.cancel_event,
            )
        except Exception as exc:
            # Old senders ignore RESUME and start at chunk zero; a temporary
            # local failure is also recoverable through META replay. Do not
            # destroy durable receiver state merely because this hint failed.
            incoming.record.event("resume_delivery_failed", error=str(exc))

    def _restore_incoming(
        self,
        meta: MetaMessage,
        *,
        existing: core._TransferRecord | None = None,
    ) -> core._IncomingState | None:
        loaded = self._load_incoming_manifest(meta.transfer_id)
        if loaded is None:
            return None
        payload, stored_meta, received = loaded
        if stored_meta != meta:
            return None
        part = self._incoming_part_path(meta.transfer_id)
        if not part.is_file():
            return None

        if existing is None:
            record = self._reserve_record(
                meta.transfer_id,
                direction="RX",
                filename=core.safe_received_filename(meta.filename),
            )
        else:
            record = existing
            with self._lock:
                if self._active_id not in (None, record.transfer_id):
                    return None
                self._active_id = record.transfer_id
            self._claim(record.transfer_id, record.direction)

        chunks_total = (
            0 if meta.wire_size == 0 else math.ceil(meta.wire_size / meta.chunk_size)
        )
        record.rx_meta = meta
        record.original_bytes = meta.original_size
        record.wire_bytes = meta.wire_size
        record.chunks_total = chunks_total
        record.set_progress(
            bytes_completed=sum(received.values()),
            chunks_completed=len(received),
        )
        record.set_state("receiving")
        incoming = core._IncomingState(
            meta=meta,
            record=record,
            wire_path=part,
            received=received,
            last_activity_monotonic=time.monotonic(),
        )
        incoming._checkpoint_chunks = len(received)
        incoming._checkpoint_time = time.monotonic()
        incoming._persistent_status = str(payload.get("status", "receiving"))
        with self._lock:
            self._incoming = incoming
        self._checkpoint_incoming(incoming, status="receiving", force=True)
        record.event(
            "resume_state_restored",
            chunks=len(received),
            next_chunk=self._earliest_missing(incoming),
        )
        return incoming

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
                        ResultMessage(meta.transfer_id, True, "ok", ""),
                    )
                    return
                if incoming is not None and incoming.record is existing:
                    self._touch_incoming(incoming)
                    existing.event("meta_replayed")
                    self._send_resume(incoming)
                    return
                if existing.state == "suspended":
                    restored = self._restore_incoming(meta, existing=existing)
                    if restored is not None:
                        self._send_resume(restored)
                        return
            self._reject_incoming(
                meta.transfer_id,
                "protocol_error",
                "conflicting META for existing transfer_id",
            )
            return

        if self._completed_matches_meta(meta.transfer_id, meta):
            self._send_result_async(
                None,
                ResultMessage(meta.transfer_id, True, "ok", ""),
            )
            return

        if active is not None:
            self._reject_incoming(
                meta.transfer_id,
                "busy",
                "another file transfer is active",
            )
            return

        restored = self._restore_incoming(meta)
        if restored is not None:
            self._send_resume(restored)
            return

        part = self._incoming_part_path(meta.transfer_id)
        try:
            filename = core.safe_received_filename(meta.filename)
            maximum = data_payload_capacity(self.transport.payload_capacity)
            if not 1 <= meta.chunk_size <= maximum:
                raise core.FileTransferError(
                    "invalid_metadata",
                    "remote chunk size exceeds local binary transport capacity",
                    phase="receiving",
                )
            if self._incoming_manifest_path(meta.transfer_id).exists() or part.exists():
                raise core.FileTransferError(
                    "storage_failed",
                    "stale/corrupt durable resume state already exists for transfer_id",
                    phase="receiving",
                )
            part.parent.mkdir(parents=True, exist_ok=True)
            with part.open("xb"):
                pass
            record = self._reserve_record(
                meta.transfer_id,
                direction="RX",
                filename=filename,
            )
        except core.FileTransferError as exc:
            part.unlink(missing_ok=True)
            self._reject_incoming(meta.transfer_id, exc.code, exc.message)
            return
        except Exception as exc:
            part.unlink(missing_ok=True)
            self._reject_incoming(meta.transfer_id, "storage_failed", str(exc))
            return

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
        incoming = core._IncomingState(
            meta=meta,
            record=record,
            wire_path=part,
            received={},
            last_activity_monotonic=time.monotonic(),
        )
        incoming._checkpoint_chunks = 0
        incoming._checkpoint_time = 0.0
        incoming._persistent_status = "receiving"
        with self._lock:
            self._incoming = incoming
        self._checkpoint_incoming(incoming, status="receiving", force=True)
        self._send_resume(incoming)

    def _handle_data(self, message: DataMessage) -> None:
        incoming = self._incoming_for(message.transfer_id)
        before = len(incoming.received) if incoming is not None else 0
        super()._handle_data(message)
        current = self._incoming_for(message.transfer_id)
        if current is not None and len(current.received) > before:
            self._checkpoint_incoming(current)

    def _suspend_incoming(
        self,
        incoming: core._IncomingState,
        *,
        reason: str,
    ) -> None:
        self._checkpoint_incoming(incoming, status="suspended", force=True)
        with self._lock:
            if self._incoming is incoming:
                self._incoming = None
            if self._active_id == incoming.record.transfer_id:
                self._active_id = None
        incoming.record.set_state("suspended")
        incoming.record.event("transfer_suspended", reason=reason)
        self._release(incoming.record.transfer_id, incoming.record.direction)

    def _expire_stale_incoming(self) -> None:
        with self._lock:
            incoming = self._incoming
        if incoming is None:
            return
        idle_s = time.monotonic() - incoming.last_activity_monotonic
        if idle_s < self.incoming_idle_timeout_s:
            return
        self._suspend_incoming(incoming, reason="remote_sender_timeout")

    def _fail_incoming(
        self,
        incoming: core._IncomingState,
        failure: core.FileTransferError,
        *,
        terminal_state: str = "failed",
    ) -> None:
        self._incoming_manifest_path(incoming.record.transfer_id).unlink(missing_ok=True)
        super()._fail_incoming(
            incoming,
            failure,
            terminal_state=terminal_state,
        )

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
                    ResultMessage(message.transfer_id, True, "ok", ""),
                )
                return
            tombstone = self._completed_tombstone(message.transfer_id)
            if tombstone is not None:
                stored_end = self._end_from_json(
                    tombstone.get("end"), message.transfer_id
                )
                if stored_end == message:
                    self._send_result_async(
                        None,
                        ResultMessage(message.transfer_id, True, "ok", ""),
                    )
                    return
            return

        self._touch_incoming(incoming)
        if incoming.record.cancel_event.is_set():
            self._fail_incoming(
                incoming,
                core.FileTransferCancelled(),
                terminal_state="cancelled",
            )
            return
        record = incoming.record
        try:
            if message.chunk_count != record.chunks_total:
                raise core.FileTransferError(
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
                repair = MissingMessage(record.transfer_id, ranges)
                try:
                    encode_message(repair, self.transport.payload_capacity)
                except FileProtocolError as exc:
                    raise core.FileTransferError(
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
                self._send_message(repair, cancel_event=record.cancel_event)
                record.event(
                    "repair_requested",
                    chunks=len(missing),
                    ranges=len(ranges),
                )
                record.set_state("repairing")
                self._checkpoint_incoming(incoming, force=True)
                return

            if incoming.wire_path.stat().st_size != incoming.meta.wire_size:
                raise core.FileTransferError(
                    "missing_chunks",
                    "wire file size does not match expected wire_size",
                    phase="verifying",
                )
            record.set_state("verifying")
            if core._sha256_file(incoming.wire_path, record.cancel_event) != message.wire_sha256:
                raise core.FileTransferError(
                    "wire_hash_mismatch",
                    "received wire stream SHA-256 mismatch",
                    phase="verifying",
                )

            final_temp, original_hash, original_size = self._materialize_original(incoming)
            if original_size != incoming.meta.original_size:
                final_temp.unlink(missing_ok=True)
                raise core.FileTransferError(
                    "original_hash_mismatch",
                    "original size does not match declared size",
                    phase="verifying",
                )
            if original_hash != incoming.meta.original_sha256:
                final_temp.unlink(missing_ok=True)
                raise core.FileTransferError(
                    "original_hash_mismatch",
                    "original file SHA-256 mismatch",
                    phase="verifying",
                )

            destination = core._unique_destination(
                self.receive_dir, incoming.record.filename
            )
            self._checkpoint_incoming(
                incoming,
                status="publishing",
                force=True,
                end=message,
                destination=destination,
            )
            os.replace(final_temp, destination)
            record.rx_end = message
            if final_temp != incoming.wire_path:
                incoming.wire_path.unlink(missing_ok=True)
            self._write_completed_tombstone(
                record, incoming.meta, message, destination
            )
            self._incoming_manifest_path(record.transfer_id).unlink(missing_ok=True)

            self._send_result(
                record,
                ResultMessage(record.transfer_id, True, "ok", ""),
            )
            with self._lock:
                if self._incoming is incoming:
                    self._incoming = None
            self._terminal_record(record, "completed", final_path=destination)
        except core.FileTransferCancelled as exc:
            self._fail_incoming(incoming, exc, terminal_state="cancelled")
        except core.FileTransferError as exc:
            self._fail_incoming(incoming, exc)
        except Exception as exc:
            self._fail_incoming(
                incoming,
                core.FileTransferError(
                    "storage_failed", str(exc), phase=record.state
                ),
            )

    # ------------------------------------------------------------------
    # TODO_037: sender journal + META -> earliest-missing handshake

    def _write_outgoing_journal(
        self,
        record: core._TransferRecord,
        prepared: core._PreparedSource,
        *,
        chunk_size: int,
        status: str,
    ) -> None:
        self._atomic_json(
            self._outgoing_manifest_path(record.transfer_id),
            {
                "schema": _STATE_SCHEMA,
                "kind": "outgoing",
                "transfer_id": transfer_id_text(record.transfer_id),
                "status": status,
                "source_path": str(prepared.source_path.resolve()),
                "filename": prepared.filename,
                "original_size": prepared.original_size,
                "original_sha256": prepared.original_sha256.hex(),
                "wire_size": prepared.wire_size,
                "wire_sha256": prepared.wire_sha256.hex(),
                "compression": int(prepared.compression),
                "chunk_size": chunk_size,
                "updated": time.time(),
            },
        )

    def _find_outgoing_resume(self, path: Path) -> dict[str, Any] | None:
        resolved = str(path.resolve())
        candidates: list[dict[str, Any]] = []
        for manifest in self._outgoing_state_dir.glob("*.json"):
            value = self._read_json(manifest)
            if (
                value
                and value.get("schema") == _STATE_SCHEMA
                and value.get("source_path") == resolved
                and isinstance(value.get("original_sha256"), str)
            ):
                candidates.append(value)
        if not candidates:
            return None
        candidates.sort(key=lambda item: float(item.get("updated", 0)), reverse=True)
        for value in candidates:
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
            except (OSError, core.FileTransferError):
                continue
            value = dict(value)
            value["parsed_transfer_id"] = transfer_id
            return value
        return None

    def start_send(self, local_path: str | Path) -> dict[str, Any]:
        path = Path(local_path).expanduser()
        if not path.exists():
            raise core.FileTransferError(
                "file_not_found",
                f"local file does not exist: {path}",
                phase="preparing",
            )
        if not path.is_file():
            raise core.FileTransferError(
                "not_a_file",
                f"local path is not a regular file: {path}",
                phase="preparing",
            )

        resume = self._find_outgoing_resume(path)
        with self._lock:
            if resume is not None:
                transfer_id = int(resume["parsed_transfer_id"])
                if transfer_id in self._records:
                    resume = None
            if resume is None:
                transfer_id = self._new_transfer_id_locked()
        record = self._reserve_record(
            transfer_id,
            direction="TX",
            filename=path.name,
        )
        record._resuming_persistent = resume is not None
        if resume is not None:
            record.event("sender_resume_journal_restored")
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
            "max_window": core.FILE_MAX_WINDOW,
            "retention": self.event_retention,
        }
        if resume is not None:
            result["resumed"] = True
        return result

    def feed_binary(self, payload: bytes) -> None:
        try:
            message = decode_message(payload)
        except FileProtocolError:
            return
        if message is None:
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
        super().feed_binary(payload)

    def _await_resume(
        self,
        record: core._TransferRecord,
        *,
        chunk_count: int,
    ) -> tuple[int, ResultMessage | None]:
        deadline = time.monotonic() + self.resume_handshake_timeout_s
        with record._condition:
            while True:
                if record.cancel_event.is_set():
                    raise core.FileTransferCancelled()
                if record.remote_result is not None:
                    return 0, record.remote_result
                message = getattr(record, "remote_resume", None)
                if message is not None:
                    record.remote_resume = None
                    if not 0 <= message.next_chunk <= chunk_count:
                        raise core.FileTransferError(
                            "invalid_resume_request",
                            "receiver RESUME cursor exceeds declared chunk_count",
                            phase="resuming",
                            details={
                                "next_chunk": message.next_chunk,
                                "chunk_count": chunk_count,
                            },
                        )
                    return message.next_chunk, None
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    # Backward compatibility: an older receiver does not know
                    # RESUME and simply accepts DATA from zero.
                    record.event("resume_handshake_fallback", next_chunk=0)
                    return 0, None
                record._condition.wait(timeout=remaining)

    def _send_chunks_from(
        self,
        record: core._TransferRecord,
        prepared: core._PreparedSource,
        *,
        chunk_size: int,
        start_chunk: int,
    ) -> None:
        if start_chunk < 0 or start_chunk > record.chunks_total:
            raise core.FileTransferError(
                "invalid_resume_request",
                "resume cursor outside prepared stream",
                phase="resuming",
            )
        sent_bytes = min(prepared.wire_size, start_chunk * chunk_size)
        record.set_progress(
            bytes_completed=sent_bytes,
            chunks_completed=start_chunk,
        )
        with prepared.wire_path.open("rb") as source:
            source.seek(start_chunk * chunk_size)
            chunk_index = start_chunk
            while chunk_index < record.chunks_total:
                if record.cancel_event.is_set():
                    raise core.FileTransferCancelled()
                block = source.read(chunk_size)
                if not block:
                    raise core.FileTransferError(
                        "local_failure",
                        "prepared wire stream ended before declared chunk_count",
                        phase="sending",
                    )
                self._send_message(
                    DataMessage(record.transfer_id, chunk_index, block),
                    cancel_event=record.cancel_event,
                )
                sent_bytes += len(block)
                chunk_index += 1
                record.set_progress(
                    bytes_completed=sent_bytes,
                    chunks_completed=chunk_index,
                )

    def _send_worker(self, record: core._TransferRecord, path: Path) -> None:
        prepared: core._PreparedSource | None = None
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
            self._write_outgoing_journal(
                record,
                prepared,
                chunk_size=chunk_size,
                status="active",
            )
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
                record.transfer_id,
                chunks_total,
                prepared.wire_sha256,
            )

            record.set_state("sending")
            self._send_message(meta, cancel_event=record.cancel_event)
            start_chunk, early_result = self._await_resume(
                record, chunk_count=chunks_total
            )
            if early_result is not None:
                if not early_result.ok:
                    raise core.FileTransferError(
                        "remote_failed",
                        early_result.reason or early_result.code,
                        phase="resuming",
                    )
                self._outgoing_manifest_path(record.transfer_id).unlink(missing_ok=True)
                self._terminal_record(record, "completed")
                return

            if start_chunk:
                record.set_state("resuming")
                record.event("resume_started", next_chunk=start_chunk)
            else:
                record.set_state("sending")
            self._send_chunks_from(
                record,
                prepared,
                chunk_size=chunk_size,
                start_chunk=start_chunk,
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
                raise core.FileTransferError(
                    "remote_failed",
                    result.reason or result.code,
                    phase="waiting_result",
                    details={"remote_code": result.code},
                )
            self._outgoing_manifest_path(record.transfer_id).unlink(missing_ok=True)
            self._terminal_record(record, "completed")
        except core.FileTransferCancelled as exc:
            if getattr(record, "_shutdown_suspend", False):
                failure = core.FileTransferError(
                    "local_shutdown",
                    "SerialTerminal stopped with resumable outgoing transfer retained",
                    phase=record.state,
                )
                self._terminal_record(record, "failed", failure=failure)
            else:
                self._outgoing_manifest_path(record.transfer_id).unlink(missing_ok=True)
                self._terminal_record(record, "cancelled", failure=exc)
        except core.FileTransferError as exc:
            # Keep sender journal for a later file_send_start(path) resume unless
            # source identity changes or the operator explicitly cancels.
            self._terminal_record(record, "failed", failure=exc)
        except Exception as exc:
            failure = core.FileTransferError(
                "local_failure", str(exc), phase=record.state
            )
            self._terminal_record(record, "failed", failure=failure)
        finally:
            if prepared is not None and prepared.remove_wire_path:
                prepared.wire_path.unlink(missing_ok=True)

    def close(self) -> None:
        # Process/session shutdown is a suspension boundary, not an instruction
        # to destroy recoverable partial state. Explicit cancel still deletes it.
        self._stopping.set()
        self.transport.set_receiver(None)
        with self._lock:
            incoming = self._incoming
            active = self._records.get(self._active_id) if self._active_id is not None else None
        if incoming is not None:
            self._suspend_incoming(incoming, reason="manager_close")
        if active is not None and active.direction == "TX":
            active._shutdown_suspend = True
            active.cancel_event.set()
        self._rx_queue.put(None)
        self._rx_thread.join(timeout=1.0)
        self.join_all(1.0)
