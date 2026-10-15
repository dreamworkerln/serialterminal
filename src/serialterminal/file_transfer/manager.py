from __future__ import annotations

import os
from pathlib import Path
import time
from typing import Any

from . import core
from .protocol import EndMessage, MetaMessage, ResultMessage, transfer_id_text
from .resume_source import prepare_source
from .resume_store import ResumeStateStore
from . import resumable


_PUBLIC_RESUME_HANDSHAKE_TIMEOUT_S = None


class _DurableResumeStateStore(ResumeStateStore):
    """Resume store with durable writes and no symlinked manifest reads."""

    @staticmethod
    def _fsync_directory(directory: Path) -> None:
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        try:
            descriptor = os.open(directory, flags)
        except OSError:
            # Some non-POSIX filesystems do not permit opening directories.
            # The manifest file itself is still fsynced by the base store.
            if os.name == "posix":
                raise
            return
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    @staticmethod
    def atomic_json(path: Path, payload: dict[str, Any]) -> None:
        ResumeStateStore.atomic_json(path, payload)
        # Новые каталоги state тоже должны пережить crash: fsync leaf manifest
        # недостаточен, если запись о самом каталоге ещё не сохранена.
        for directory in (path.parent, path.parent.parent, path.parent.parent.parent):
            _DurableResumeStateStore._fsync_directory(directory)

    def read_json(self, path: Path) -> dict[str, Any] | None:
        if path.is_symlink():
            return None
        return ResumeStateStore.read_json(self, path)


"""Public resumable FT1 manager with compatibility and identity guards."""

def initialize(self, *args: Any, **kwargs: Any) -> None:
    self._resume_candidates: dict[int, dict[str, Any]] = {}
    kwargs.setdefault(
        "resume_handshake_timeout_s", _PUBLIC_RESUME_HANDSHAKE_TIMEOUT_S
    )
    kwargs["_defer_start"] = True
    resumable.initialize(self, *args, **kwargs)
    self._resume_store = _DurableResumeStateStore(
        self.receive_dir / ".serialterminal-state",
        max_received_ranges=self.max_received_ranges, max_manifest_bytes=self.max_manifest_bytes,
    )
    core.FileTransferManager._start_workers(self)

def _prepare_source(self, path: Path, record) -> core._PreparedSource:
    return prepare_source(path, record)

def _sender_resume_candidate(self, path: Path) -> dict[str, Any] | None:
    try:
        actual_size = path.stat().st_size
        actual_hash = core._sha256_file(path)
    except OSError:
        return None

    candidates: list[dict[str, Any]] = []
    for value in self._resume_store.find_outgoing_for_source(path):
        candidate = self._validated_sender_candidate(
            path,
            value,
            actual_size=actual_size,
            actual_hash=actual_hash,
        )
        if candidate is not None:
            candidates.append(candidate)

    if not candidates:
        return None
    if len(candidates) > 1:
        transfer_ids = sorted(
            transfer_id_text(int(item["parsed_transfer_id"]))
            for item in candidates
        )
        raise core.FileTransferError(
            "ambiguous_resume_state",
            "multiple resumable sender journals match the same source",
            phase="preparing",
            details={"transfer_ids": transfer_ids},
        )

    candidate = candidates[0]
    transfer_id = int(candidate["parsed_transfer_id"])
    with self._lock:
        self._resume_candidates[transfer_id] = candidate
    return candidate

def _validated_sender_candidate(
    self,
    path: Path,
    value: dict[str, Any],
    *,
    actual_size: int,
    actual_hash: bytes,
) -> dict[str, Any] | None:
    try:
        transfer_text = str(value["transfer_id"])
        transfer_id = int(transfer_text, 16)
        original_size = int(value["original_size"])
        original_hash = bytes.fromhex(str(value["original_sha256"]))
        wire_size = int(value["wire_size"])
        wire_hash = bytes.fromhex(str(value["wire_sha256"]))
        compression = int(value["compression"])
        chunk_size = int(value["chunk_size"])
    except (KeyError, TypeError, ValueError):
        return None

    if (
        value.get("kind") != "outgoing"
        or value.get("status") != "active"
        or transfer_id == 0
        or transfer_text != transfer_id_text(transfer_id)
        or value.get("filename") != path.name
        or original_size < 0
        or wire_size < 0
        or len(original_hash) != 32
        or len(wire_hash) != 32
        or compression not in {0, 1}
        or chunk_size <= 0
        or actual_size != original_size
        or actual_hash != original_hash
    ):
        return None

    canonical = self._resume_store.read_json(
        self._resume_store.outgoing_manifest(transfer_id)
    )
    if canonical != value:
        return None

    candidate = dict(value)
    candidate["parsed_transfer_id"] = transfer_id
    return candidate

def _save_sender_journal(self, record, prepared, chunk_size: int) -> None:
    self._resume_store.claim("outgoing", record.transfer_id)
    with self._lock:
        candidate = self._resume_candidates.get(record.transfer_id)
    if candidate is not None:
        self._verify_resume_wire(candidate, prepared, chunk_size)
    resumable._save_sender_journal(self, record, prepared, chunk_size)

def _verify_resume_wire(candidate, prepared, chunk_size: int) -> None:
    try:
        expected_wire_size = int(candidate["wire_size"])
        expected_wire_hash = bytes.fromhex(str(candidate["wire_sha256"]))
        expected_compression = int(candidate["compression"])
        expected_chunk_size = int(candidate["chunk_size"])
    except (KeyError, TypeError, ValueError) as exc:
        raise core.FileTransferError(
            "resume_journal_invalid",
            "sender resume journal has invalid wire identity",
            phase="preparing",
        ) from exc

    actual = (
        prepared.wire_size,
        prepared.wire_sha256,
        int(prepared.compression),
        chunk_size,
    )
    expected = (
        expected_wire_size,
        expected_wire_hash,
        expected_compression,
        expected_chunk_size,
    )
    if actual != expected:
        raise core.FileTransferError(
            "resume_wire_changed",
            "rebuilt wire stream no longer matches the retained transfer identity",
            phase="preparing",
            details={
                "expected_wire_size": expected_wire_size,
                "actual_wire_size": prepared.wire_size,
                "expected_chunk_size": expected_chunk_size,
                "actual_chunk_size": chunk_size,
            },
        )

def _restore_incoming(self, meta: MetaMessage, *, existing=None):
    part = self._resume_store.incoming_part(meta.transfer_id)
    if part.is_symlink():
        return None
    if not self._resume_store.incoming_manifest(meta.transfer_id).exists():
        return None
    acquired = self._resume_store.claim("incoming", meta.transfer_id)
    try:
        return resumable._restore_incoming(self, meta, existing=existing)
    finally:
        if acquired and self._active_id != meta.transfer_id:
            self._resume_store.release("incoming", meta.transfer_id)

def _start_new_incoming(self, meta: MetaMessage) -> None:
    part = self._resume_store.incoming_part(meta.transfer_id)
    if part.is_symlink():
        self._reject_incoming(
            meta.transfer_id,
            "storage_failed",
            "receiver partial path is a symlink",
        )
        return
    resumable._start_new_incoming(self, meta)

def _checkpoint_incoming(
    self,
    incoming,
    *,
    status: str | None = None,
    force: bool = False,
    end: EndMessage | None = None,
    destination: Path | None = None,
) -> None:
    """Persist wire bytes before advancing the durable received map."""
    now = time.monotonic()
    previous_count = int(getattr(incoming, "_checkpoint_count", 0))
    previous_time = float(getattr(incoming, "_checkpoint_time", 0.0))
    if not force:
        chunk_due = (
            len(incoming.received) - previous_count
            >= self.resume_checkpoint_chunks
        )
        time_due = now - previous_time >= self.resume_checkpoint_s
        if not chunk_due and not time_due:
            return

    if incoming.wire_path.is_symlink():
        raise core.FileTransferError(
            "storage_failed",
            "receiver partial path became a symlink",
            phase="receiving",
        )
    try:
        with incoming.wire_path.open("rb") as handle:
            os.fsync(handle.fileno())
    except OSError as exc:
        raise core.FileTransferError(
            "storage_failed",
            f"could not persist receiver partial before checkpoint: {exc}",
            phase="receiving",
        ) from exc

    resumable._checkpoint_incoming(self,
        incoming,
        status=status,
        force=True,
        end=end,
        destination=destination,
    )

def _path_is_direct_receive_file(self, path: Path) -> bool:
    try:
        if path.is_symlink():
            return False
        receive_root = self.receive_dir.resolve()
        return path.parent.resolve() == receive_root
    except OSError:
        return False

def _reconcile_published(self, meta: MetaMessage, payload: dict[str, Any]) -> bool:
    destination = payload.get("destination")
    if not isinstance(destination, str):
        return False
    if not self._path_is_direct_receive_file(Path(destination)):
        return False
    return resumable._reconcile_published(self, meta, payload)

def _completed_matches_meta(self, meta: MetaMessage) -> bool:
    value = self._resume_store.load_completed(meta.transfer_id)
    if value is None:
        return False
    final_path = value.get("final_path")
    if not isinstance(final_path, str):
        return False
    if not self._path_is_direct_receive_file(Path(final_path)):
        return False
    return resumable._completed_matches_meta(self, meta)

def _replay_completed_end(self, message: EndMessage) -> bool:
    value = self._resume_store.load_completed(message.transfer_id)
    if value is None:
        return False
    meta = self._resume_store.meta_from_json(
        value.get("meta"), message.transfer_id
    )
    stored_end = self._resume_store.end_from_json(
        value.get("end"), message.transfer_id
    )
    if (
        meta is None
        or stored_end != message
        or not self._completed_matches_meta(meta)
    ):
        return False
    self._send_result_async(
        None, ResultMessage(message.transfer_id, True, "ok", "")
    )
    return True

def _terminal_record(self, record, state: str, **kwargs: Any) -> None:
    failure = kwargs.get("failure")
    remote_code = failure.details.get("remote_code") if failure is not None else None
    if (state == "failed" and record.direction == "TX" and remote_code in {
            "wire_hash_mismatch", "original_hash_mismatch", "decompression_failed",
            "invalid_chunk", "invalid_metadata",
    }):
        journal = self._resume_store.read_json(self._resume_store.outgoing_manifest(record.transfer_id))
        if journal is not None:
            try:
                self._resume_store.save_outgoing(record.transfer_id, {
                    **journal, "status": "terminal", "terminal_remote_code": remote_code,
                })
                with self._lock:
                    self._resume_candidates.pop(record.transfer_id, None)
            except Exception as exc:
                # Без durable classification нельзя снова автоматически выбрать
                # этот ID. Ownership остаётся занятым до явного session close.
                record.event("sender_terminal_checkpoint_failed", error=str(exc), remote_code=remote_code)
                record.terminal("failed", failure=core.FileTransferError("local_ownership_unsettled", str(exc), phase="settling"))
                return
    try:
        core.FileTransferManager._terminal_record(self, record, state, **kwargs)
    finally:
        if state in {"completed", "cancelled"}:
            with self._lock:
                self._resume_candidates.pop(record.transfer_id, None)

def _handle_meta(self, meta: MetaMessage) -> None:
    """Re-open a failed RX attempt only from matching usable durable state."""
    with self._lock:
        existing = self._records.get(meta.transfer_id)
    if self._can_revive_timed_out_receiver(existing, meta):
        try:
            restored = self._restore_incoming(meta, existing=existing)
        except Exception as exc:
            existing.event("resume_restore_failed", error=str(exc))
            self._reject_incoming(meta.transfer_id, "storage_failed", str(exc))
            return
        if restored == "completed":
            value = self._resume_store.load_completed(meta.transfer_id)
            self._restart_record(existing, "receiving")
            existing.rx_end = self._resume_store.end_from_json(value.get("end"), meta.transfer_id)
            existing.terminal("completed", final_path=Path(value["final_path"]))
            self._send_result_async(
                existing,
                ResultMessage(meta.transfer_id, True, "ok", ""),
            )
            return
        if restored is not None:
            existing.event("same_process_resume_reopened")
            self._send_resume(restored)
            return
    resumable._handle_meta(self, meta)

def _can_revive_timed_out_receiver(self, record, meta: MetaMessage) -> bool:
    if record is None or record.direction != "RX" or record.rx_meta != meta:
        return False
    if record.state != "failed":
        return False
    with self._lock:
        if self._active_id is not None:
            return False
    loaded = self._resume_store.load_incoming(meta.transfer_id)
    if loaded is None:
        return False
    payload, stored_meta = loaded
    if stored_meta != meta or payload.get("status") not in {"receiving", "suspended", "publishing"}:
        return False
    if payload.get("status") == "publishing":
        return True
    if self._load_received(meta, payload) is None:
        return False
    part = self._resume_store.incoming_part(meta.transfer_id)
    return not part.is_symlink() and part.is_file()

def _expire_stale_incoming(self) -> None:
    """Keep historical runtime failure while retaining durable RX state."""
    with self._lock:
        incoming = self._incoming
    if incoming is None:
        return
    idle_s = time.monotonic() - incoming.last_activity_monotonic
    idle_budget = self._incoming_idle_budget_s()
    if idle_s < idle_budget:
        return

    self._checkpoint_incoming(incoming, status="suspended", force=True)
    with self._lock:
        if self._incoming is incoming:
            self._incoming = None

    failure = core.FileTransferError(
        "remote_sender_timeout",
        "remote sender stopped before END completion",
        phase="receiving",
        details={"timeout_seconds": idle_budget},
    )
    incoming.record.event(
        "transfer_suspended",
        reason="remote_sender_timeout",
        durable=True,
    )
    self._terminal_record(incoming.record, "failed", failure=failure)
