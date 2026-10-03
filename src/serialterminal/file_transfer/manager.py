from __future__ import annotations

from pathlib import Path
import time
from typing import Any

from . import core
from .protocol import MetaMessage, ResultMessage
from .resume_source import prepare_source
from .resumable import FileTransferManager as _ResumableFileTransferManager


class FileTransferManager(_ResumableFileTransferManager):
    """Public resumable FT1 manager with compatibility and identity guards."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._resume_candidates: dict[int, dict[str, Any]] = {}
        super().__init__(*args, **kwargs)

    def _prepare_source(self, path: Path, record) -> core._PreparedSource:
        return prepare_source(path, record)

    def _sender_resume_candidate(self, path: Path) -> dict[str, Any] | None:
        candidate = super()._sender_resume_candidate(path)
        if candidate is not None:
            transfer_id = int(candidate["parsed_transfer_id"])
            with self._lock:
                self._resume_candidates[transfer_id] = candidate
        return candidate

    def _save_sender_journal(self, record, prepared, chunk_size: int) -> None:
        with self._lock:
            candidate = self._resume_candidates.get(record.transfer_id)
        if candidate is not None:
            self._verify_resume_wire(candidate, prepared, chunk_size)
        super()._save_sender_journal(record, prepared, chunk_size)

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
        if getattr(record.failure, "code", None) != "remote_sender_timeout":
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
