from __future__ import annotations

import os
from pathlib import Path
import time
from typing import Any

from . import core
from .protocol import EndMessage, MetaMessage, ResultMessage, transfer_id_text
from .resume_source import prepare_source
from .resume_store import ResumeStateStore
from .resumable import FileTransferManager as _ResumableFileTransferManager


class _DurableResumeStateStore(ResumeStateStore):
    """Resume store with a durable manifest rename on POSIX filesystems."""

    @staticmethod
    def _fsync_directory(directory: Path) -> None:
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        try:
            descriptor = os.open(directory, flags)
        except OSError:
            # Some non-POSIX filesystems do not permit opening directories.
            # The manifest file itself is still fsynced by the base store.
            return
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    @staticmethod
    def atomic_json(path: Path, payload: dict[str, Any]) -> None:
        ResumeStateStore.atomic_json(path, payload)
        _DurableResumeStateStore._fsync_directory(path.parent)


class FileTransferManager(_ResumableFileTransferManager):
    """Public resumable FT1 manager with compatibility and identity guards."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._resume_candidates: dict[int, dict[str, Any]] = {}
        super().__init__(*args, **kwargs)
        self._resume_store = _DurableResumeStateStore(
            self.receive_dir / ".serialterminal-state"
        )

    def _prepare_source(self, path: Path, record) -> core._PreparedSource:
        return prepare_source(path, record)

    def _sender_resume_candidate(self, path: Path) -> dict[str, Any] | None:
        try:
            actual_size = path.stat().st_size
            actual_hash = core._sha256_file(path)
        except OSError:
            return None

        for value in self._resume_store.find_outgoing_for_source(path):
            candidate = self._validated_sender_candidate(
                path,
                value,
                actual_size=actual_size,
                actual_hash=actual_hash,
            )
            if candidate is None:
                continue
            transfer_id = int(candidate["parsed_transfer_id"])
            with self._lock:
                self._resume_candidates[transfer_id] = candidate
            return candidate
        return None

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
        with self._lock:
            candidate = self._resume_candidates.get(record.transfer_id)
        if candidate is not None:
            self._verify_resume_wire(candidate, prepared, chunk_size)
        super()._save_sender_journal(record, prepared, chunk_size)

    def _await_resume(self, record, chunk_count: int):
        if not getattr(record, "_resuming_persistent", False):
            record.event(
                "resume_handshake_skipped",
                next_chunk=0,
                reason="new_transfer",
            )
            return 0, None
        return super()._await_resume(record, chunk_count)

    @staticmethod
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

        try:
            with incoming.wire_path.open("rb") as handle:
                os.fsync(handle.fileno())
        except OSError as exc:
            raise core.FileTransferError(
                "storage_failed",
                f"could not persist receiver partial before checkpoint: {exc}",
                phase="receiving",
            ) from exc

        super()._checkpoint_incoming(
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
        return super()._reconcile_published(meta, payload)

    def _completed_matches_meta(self, meta: MetaMessage) -> bool:
        value = self._resume_store.load_completed(meta.transfer_id)
        if value is None:
            return False
        final_path = value.get("final_path")
        if not isinstance(final_path, str):
            return False
        if not self._path_is_direct_receive_file(Path(final_path)):
            return False
        return super()._completed_matches_meta(meta)

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
        try:
            super()._terminal_record(record, state, **kwargs)
        finally:
            if state in {"completed", "cancelled"}:
                with self._lock:
                    self._resume_candidates.pop(record.transfer_id, None)

    def _handle_meta(self, meta: MetaMessage) -> None:
        """Re-open a durable RX transfer that timed out in this same process."""
        with self._lock:
            existing = self._records.get(meta.transfer_id)
        if self._can_revive_timed_out_receiver(existing, meta):
            self._revive_record(existing)
            restored = self._restore_incoming(meta, existing=existing)
            if restored == "completed":
                self._send_result_async(
                    existing,
                    ResultMessage(meta.transfer_id, True, "ok", ""),
                )
                return
            if restored is not None:
                existing.event("same_process_resume_reopened")
                self._send_resume(restored)
                return
        super()._handle_meta(meta)

    def _can_revive_timed_out_receiver(self, record, meta: MetaMessage) -> bool:
        if record is None or record.direction != "RX" or record.rx_meta != meta:
            return False
        if record.state != "failed":
            return False
        failure = record.failure
        if not isinstance(failure, dict) or failure.get("code") != "remote_sender_timeout":
            return False
        loaded = self._resume_store.load_incoming(meta.transfer_id)
        if loaded is None:
            return False
        payload, stored_meta = loaded
        if stored_meta != meta:
            return False
        if self._load_received(meta, payload) is None:
            return False
        return self._resume_store.incoming_part(meta.transfer_id).is_file()

    def _revive_record(self, record) -> None:
        with self._lock:
            while record.transfer_id in self._terminal_order:
                self._terminal_order.remove(record.transfer_id)
        with record._condition:
            record.failure = None
            record.final_path = None
            record.ended_monotonic = None
            record.cancel_event.clear()
            record.state = "receiving"
            record._condition.notify_all()

    def _expire_stale_incoming(self) -> None:
        """Keep historical runtime failure while retaining durable RX state."""
        with self._lock:
            incoming = self._incoming
        if incoming is None:
            return
        idle_s = time.monotonic() - incoming.last_activity_monotonic
        if idle_s < self.incoming_idle_timeout_s:
            return

        self._checkpoint_incoming(incoming, status="suspended", force=True)
        with self._lock:
            if self._incoming is incoming:
                self._incoming = None

        failure = core.FileTransferError(
            "remote_sender_timeout",
            "remote sender stopped before END completion",
            phase="receiving",
            details={"timeout_seconds": self.incoming_idle_timeout_s},
        )
        incoming.record.event(
            "transfer_suspended",
            reason="remote_sender_timeout",
            durable=True,
        )
        self._terminal_record(incoming.record, "failed", failure=failure)
