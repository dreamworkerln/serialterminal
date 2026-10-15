from __future__ import annotations

from contextlib import contextmanager

import errno
import json
import math
import os
from pathlib import Path
import threading
import time
from typing import Any

from .received import ReceivedRanges, DEFAULT_MAX_RECEIVED_RANGES, DEFAULT_MAX_MANIFEST_BYTES
from .protocol import Compression, EndMessage, MetaMessage, transfer_id_text


STATE_SCHEMA = 1
DEFAULT_STATE_TTL_S = 7 * 24 * 3600.0
DEFAULT_MAX_INCOMING = 32
DEFAULT_MAX_OUTGOING = 32
DEFAULT_MAX_COMPLETED = 64
DEFAULT_MAX_PART_BYTES = 1024 * 1024 * 1024
_PART_PREFIX = ".serialterminal-"
_PART_SUFFIX = ".part"


class ResumeStateStore:
    """Crash-safe small manifests plus receiver partial wire files."""

    def __init__(
        self,
        root: Path,
        *,
        ttl_s: float = DEFAULT_STATE_TTL_S,
        max_part_bytes: int = DEFAULT_MAX_PART_BYTES,
        max_received_ranges: int = DEFAULT_MAX_RECEIVED_RANGES,
        max_manifest_bytes: int = DEFAULT_MAX_MANIFEST_BYTES,
    ) -> None:
        self.max_received_ranges = max_received_ranges
        self.max_manifest_bytes = max_manifest_bytes
        self.root = root
        self.incoming_dir = root / "incoming"
        self.outgoing_dir = root / "outgoing"
        self.completed_dir = root / "completed"
        self.ttl_s = float(ttl_s)
        self.max_part_bytes = int(max_part_bytes)
        self._namespace_mutex = threading.RLock()
        self._namespace_depth = threading.local()
        self._owned_leases = {}
        # Keep the public receive directory available while creating the hidden
        # durable-state tree only when a manifest is actually persisted. This
        # preserves the old "invalid META leaves receive_dir empty" contract.
        self.root.parent.mkdir(parents=True, exist_ok=True)
        self.cleanup()

    @contextmanager
    def namespace_lock(self):
        # Один неизменный lock inode координирует cleanup/admission/publication.
        # RLock и thread-local depth позволяют nested saves того же store.
        import fcntl

        with self._namespace_mutex:
            depth = getattr(self._namespace_depth, "value", 0)
            if depth:
                self._namespace_depth.value = depth + 1
                try:
                    yield
                finally:
                    self._namespace_depth.value = depth
                return
            self.root.mkdir(parents=True, exist_ok=True)
            descriptor = os.open(self.root / ".store.lock", os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
            with os.fdopen(descriptor, "a+b") as handle:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                self._namespace_depth.value = 1
                try:
                    yield
                finally:
                    self._namespace_depth.value = 0
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    publication_lock = namespace_lock

    def _lease_path(self, kind: str, transfer_id: int) -> Path:
        if kind not in {"incoming", "outgoing"}:
            raise ValueError("unknown durable ownership kind")
        return self.root / "leases" / f"{kind}-{transfer_id_text(transfer_id)}.lock"

    def claim(self, kind: str, transfer_id: int) -> bool:
        import fcntl

        key = (kind, transfer_id)
        with self.namespace_lock():
            if key in self._owned_leases:
                return False
            path = self._lease_path(kind, transfer_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            descriptor = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
            handle = os.fdopen(descriptor, "a+b")
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                handle.close()
                raise OSError(errno.EBUSY, "durable transfer identity has another live owner") from exc
            self._owned_leases[key] = handle
            return True

    def release(self, kind: str, transfer_id: int) -> None:
        with self._namespace_mutex:
            if (kind, transfer_id) not in self._owned_leases:
                return
        with self.namespace_lock():
            handle = self._owned_leases.pop((kind, transfer_id), None)
            if handle is not None:
                handle.close()
                self._lease_path(kind, transfer_id).unlink(missing_ok=True)

    def release_all(self) -> None:
        for kind, transfer_id in list(self._owned_leases):
            self.release(kind, transfer_id)

    def _protected(self, kind: str, transfer_id: int) -> bool:
        import fcntl

        path = self._lease_path(kind, transfer_id)
        if not path.exists():
            return False
        descriptor = os.open(path, os.O_RDWR | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(descriptor, "a+b") as handle:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return True
        # Вызывается только под namespace lock: новый owner не откроет старый
        # inode между проверкой и unlink после crash/release прежнего owner.
        path.unlink(missing_ok=True)
        return False

    def reserved_destinations(self, filename: str | None = None) -> set[Path]:
        result = set()
        directory = self.root.parent.resolve()
        if filename is not None and filename.startswith(_PART_PREFIX) and filename.endswith(_PART_SUFFIX):
            try:
                int(filename[len(_PART_PREFIX):-len(_PART_SUFFIX)], 16)
            except ValueError:
                pass
            else:
                # Итоговый пользовательский файл не занимает namespace .part;
                # unique suffix отделяет его от будущего orphan/retention cleanup.
                result.add(directory / filename)
        for path in self.incoming_dir.glob("*.json"):
            value = self.read_json(path)
            if value is None or value.get("status") != "publishing":
                continue
            text = value.get("destination")
            if not isinstance(text, str):
                continue
            destination = Path(text)
            if destination.parent.resolve() == directory:
                result.add(directory / destination.name)
        return result

    @staticmethod
    def atomic_json(path: Path, payload: dict[str, Any]) -> None:
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

    def read_json(self, path: Path) -> dict[str, Any] | None:
        try:
            with path.open("rb") as handle:
                payload = handle.read(self.max_manifest_bytes + 1)
            if len(payload) > self.max_manifest_bytes:
                return None
            value = json.loads(payload)
        except (OSError, ValueError, TypeError):
            return None
        return value if isinstance(value, dict) else None

    def incoming_manifest(self, transfer_id: int) -> Path:
        return self.incoming_dir / f"{transfer_id_text(transfer_id)}.json"

    def incoming_part(self, transfer_id: int) -> Path:
        # Keep .part in the established receive_dir surface. The manifest is
        # hidden under .serialterminal-state and points at this stable identity.
        return self.root.parent / (
            f"{_PART_PREFIX}{transfer_id_text(transfer_id)}{_PART_SUFFIX}"
        )

    def outgoing_manifest(self, transfer_id: int) -> Path:
        return self.outgoing_dir / f"{transfer_id_text(transfer_id)}.json"

    def completed_manifest(self, transfer_id: int) -> Path:
        return self.completed_dir / f"{transfer_id_text(transfer_id)}.json"

    @staticmethod
    def meta_json(meta: MetaMessage) -> dict[str, Any]:
        return {
            "filename": meta.filename,
            "original_size": meta.original_size,
            "wire_size": meta.wire_size,
            "compression": int(meta.compression),
            "chunk_size": meta.chunk_size,
            "original_sha256": meta.original_sha256.hex(),
            "parent_transfer_id": meta.parent_transfer_id,
            "depth": meta.depth,
            "previous_repair_id": meta.previous_repair_id,
        }

    @staticmethod
    def meta_from_json(value: Any, transfer_id: int) -> MetaMessage | None:
        if not isinstance(value, dict):
            return None
        try:
            digest = bytes.fromhex(str(value["original_sha256"]))
            result = MetaMessage(
                transfer_id=transfer_id,
                filename=str(value["filename"]),
                original_size=int(value["original_size"]),
                wire_size=int(value["wire_size"]),
                compression=Compression(int(value["compression"])),
                chunk_size=int(value["chunk_size"]),
                original_sha256=digest,
                parent_transfer_id=int(value.get("parent_transfer_id", 0)),
                depth=int(value.get("depth", 0)),
                previous_repair_id=int(value.get("previous_repair_id", 0)),
            )
        except (KeyError, TypeError, ValueError):
            return None
        if len(result.original_sha256) != 32 or result.chunk_size <= 0:
            return None
        return result

    @staticmethod
    def end_json(end: EndMessage) -> dict[str, Any]:
        return {
            "chunk_count": end.chunk_count,
            "wire_sha256": end.wire_sha256.hex(),
            "repair_id": end.repair_id,
        }

    @staticmethod
    def end_from_json(value: Any, transfer_id: int) -> EndMessage | None:
        if not isinstance(value, dict):
            return None
        try:
            digest = bytes.fromhex(str(value["wire_sha256"]))
            result = EndMessage(
                transfer_id=transfer_id,
                chunk_count=int(value["chunk_count"]),
                wire_sha256=digest,
                repair_id=int(value.get("repair_id", 0)),
            )
        except (KeyError, TypeError, ValueError):
            return None
        return result if len(result.wire_sha256) == 32 else None

    @staticmethod
    def ranges_from_received(received: dict[int, int]) -> list[list[int]]:
        if isinstance(received, ReceivedRanges):
            return received.ranges()
        if not received:
            return []
        ordered = sorted(received)
        result: list[list[int]] = []
        start = previous = ordered[0]
        for index in ordered[1:]:
            if index == previous + 1:
                previous = index
                continue
            result.append([start, previous - start + 1])
            start = previous = index
        result.append([start, previous - start + 1])
        return result

    def received_from_ranges(self, meta, chunk_count, ranges):
        return ReceivedRanges.restore(meta, chunk_count, ranges, maximum=self.max_received_ranges)

    def _save_document(self, path, payload):
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
        if len(encoded) > self.max_manifest_bytes:
            raise OSError(errno.ENOSPC, "manifest resource limit exceeded")
        self.atomic_json(path, payload)

    def save_incoming(
        self,
        *,
        meta: MetaMessage,
        received: dict[int, int],
        status: str,
        end: EndMessage | None = None,
        destination: Path | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "schema": STATE_SCHEMA,
            "kind": "incoming",
            "transfer_id": transfer_id_text(meta.transfer_id),
            "status": status,
            "meta": self.meta_json(meta),
            "received_ranges": self.ranges_from_received(received),
            "part_path": str(self.incoming_part(meta.transfer_id)),
            "updated": time.time(),
        }
        if end is not None:
            payload["end"] = self.end_json(end)
        if destination is not None:
            payload["destination"] = str(destination)
        self._save_document(self.incoming_manifest(meta.transfer_id), payload)

    def load_incoming(
        self,
        transfer_id: int,
    ) -> tuple[dict[str, Any], MetaMessage] | None:
        payload = self.read_json(self.incoming_manifest(transfer_id))
        if payload is None or payload.get("schema") != STATE_SCHEMA:
            return None
        if payload.get("transfer_id") != transfer_id_text(transfer_id):
            return None
        expected_part = str(self.incoming_part(transfer_id))
        if payload.get("part_path") not in (None, expected_part):
            return None
        meta = self.meta_from_json(payload.get("meta"), transfer_id)
        return None if meta is None else (payload, meta)

    def delete_incoming(self, transfer_id: int, *, delete_part: bool) -> None:
        self.incoming_manifest(transfer_id).unlink(missing_ok=True)
        if delete_part:
            self.incoming_part(transfer_id).unlink(missing_ok=True)

    def save_completed(
        self,
        *,
        meta: MetaMessage,
        end: EndMessage,
        final_path: Path,
    ) -> None:
        self._save_document(
            self.completed_manifest(meta.transfer_id),
            {
                "schema": STATE_SCHEMA,
                "kind": "completed",
                "transfer_id": transfer_id_text(meta.transfer_id),
                "meta": self.meta_json(meta),
                "end": self.end_json(end),
                "final_path": str(final_path),
                "updated": time.time(),
            },
        )

    def load_completed(self, transfer_id: int) -> dict[str, Any] | None:
        payload = self.read_json(self.completed_manifest(transfer_id))
        if payload is None or payload.get("schema") != STATE_SCHEMA:
            return None
        if payload.get("transfer_id") != transfer_id_text(transfer_id):
            return None
        return payload

    def save_outgoing(self, transfer_id: int, payload: dict[str, Any]) -> None:
        document = {
            "schema": STATE_SCHEMA,
            "kind": "outgoing",
            "transfer_id": transfer_id_text(transfer_id),
            "updated": time.time(),
            **payload,
        }
        self._save_document(self.outgoing_manifest(transfer_id), document)

    def delete_outgoing(self, transfer_id: int) -> None:
        self.outgoing_manifest(transfer_id).unlink(missing_ok=True)

    def find_outgoing_for_source(self, source_path: Path) -> list[dict[str, Any]]:
        resolved = str(source_path.resolve())
        result: list[dict[str, Any]] = []
        for path in self.outgoing_dir.glob("*.json"):
            value = self.read_json(path)
            if (
                value is not None
                and value.get("schema") == STATE_SCHEMA
                and value.get("source_path") == resolved
            ):
                updated = value.get("updated")
                if isinstance(updated, bool) or not isinstance(updated, (int, float)):
                    continue
                try:
                    stamp = float(updated)
                except (OverflowError, ValueError):
                    continue
                if not math.isfinite(stamp) or stamp < 0:
                    continue
                result.append(value)
        result.sort(key=lambda item: item["updated"], reverse=True)
        return result

    def cleanup(self) -> None:
        if not self.root.exists() and not any(self.root.parent.glob(f"{_PART_PREFIX}*{_PART_SUFFIX}")):
            return
        with self.namespace_lock():
            self._cleanup_dir(self.incoming_dir, DEFAULT_MAX_INCOMING, with_parts=True)
            self._cleanup_dir(self.outgoing_dir, DEFAULT_MAX_OUTGOING, with_parts=False)
            self._cleanup_dir(self.completed_dir, DEFAULT_MAX_COMPLETED, with_parts=False)
            self._cleanup_part_budget()

    def _cleanup_dir(self, directory: Path, maximum: int, *, with_parts: bool) -> None:
        now = time.time()
        entries: list[tuple[float, Path]] = []
        for path in directory.glob("*.json"):
            value = self.read_json(path)
            try:
                raw = value.get("updated", 0) if value else 0
                if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                    raise ValueError("invalid retained timestamp")
                updated = float(raw)
                if not math.isfinite(updated) or updated < 0:
                    raise ValueError("invalid retained timestamp")
            except (TypeError, ValueError, OverflowError):
                # Повреждённый timestamp не доказывает истечение TTL и не
                # прерывает startup: используем сохранённое filesystem mtime.
                try:
                    updated = path.stat().st_mtime
                except OSError:
                    updated = 0.0
            entries.append((updated, path))
        entries.sort(reverse=True)
        for index, (updated, path) in enumerate(entries):
            if directory != self.completed_dir:
                try:
                    transfer_id = int(path.stem, 16)
                except ValueError:
                    transfer_id = None
                if transfer_id is not None and self._protected(directory.name, transfer_id):
                    continue
            if index < maximum and now - updated <= self.ttl_s:
                continue
            path.unlink(missing_ok=True)
            if with_parts:
                try:
                    transfer_id = int(path.stem, 16)
                except ValueError:
                    continue
                self.incoming_part(transfer_id).unlink(missing_ok=True)

    def _cleanup_part_budget(self) -> None:
        parts: list[tuple[float, Path, int, Path]] = []
        total = 0
        pattern = f"{_PART_PREFIX}*{_PART_SUFFIX}"
        for part in self.root.parent.glob(pattern):
            transfer_text = part.name[len(_PART_PREFIX) : -len(_PART_SUFFIX)]
            try:
                transfer_id = int(transfer_text, 16)
            except ValueError:
                continue
            manifest = self.incoming_manifest(transfer_id)
            if not manifest.exists() and not self._protected("incoming", transfer_id):
                part.unlink(missing_ok=True)
                continue
            try:
                stat = part.stat()
            except OSError:
                continue
            parts.append((stat.st_mtime, part, stat.st_size, manifest))
            total += stat.st_size
        if total <= self.max_part_bytes:
            return
        parts.sort()
        for _mtime, part, size, manifest in parts:
            if total <= self.max_part_bytes:
                break
            transfer_text = part.name[len(_PART_PREFIX) : -len(_PART_SUFFIX)]
            if self._protected("incoming", int(transfer_text, 16)):
                continue
            part.unlink(missing_ok=True)
            manifest.unlink(missing_ok=True)
            total -= size
