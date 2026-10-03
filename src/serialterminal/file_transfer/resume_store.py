from __future__ import annotations

import json
import os
from pathlib import Path
import threading
import time
from typing import Any

from .protocol import Compression, EndMessage, MetaMessage, transfer_id_text


STATE_SCHEMA = 1
DEFAULT_STATE_TTL_S = 7 * 24 * 3600.0
DEFAULT_MAX_INCOMING = 32
DEFAULT_MAX_OUTGOING = 32
DEFAULT_MAX_COMPLETED = 64
DEFAULT_MAX_PART_BYTES = 1024 * 1024 * 1024


class ResumeStateStore:
    """Crash-safe small manifests plus receiver partial wire files."""

    def __init__(
        self,
        root: Path,
        *,
        ttl_s: float = DEFAULT_STATE_TTL_S,
        max_part_bytes: int = DEFAULT_MAX_PART_BYTES,
    ) -> None:
        self.root = root
        self.incoming_dir = root / "incoming"
        self.outgoing_dir = root / "outgoing"
        self.completed_dir = root / "completed"
        self.ttl_s = float(ttl_s)
        self.max_part_bytes = int(max_part_bytes)
        self.cleanup()

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

    @staticmethod
    def read_json(path: Path) -> dict[str, Any] | None:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return None
        return value if isinstance(value, dict) else None

    def incoming_manifest(self, transfer_id: int) -> Path:
        return self.incoming_dir / f"{transfer_id_text(transfer_id)}.json"

    def incoming_part(self, transfer_id: int) -> Path:
        return self.incoming_dir / f"{transfer_id_text(transfer_id)}.part"

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
            )
        except (KeyError, TypeError, ValueError):
            return None
        return result if len(result.wire_sha256) == 32 else None

    @staticmethod
    def ranges_from_received(received: dict[int, int]) -> list[list[int]]:
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

    @staticmethod
    def received_from_ranges(
        meta: MetaMessage,
        chunk_count: int,
        ranges: Any,
    ) -> dict[int, int] | None:
        if not isinstance(ranges, list):
            return None
        received: dict[int, int] = {}
        previous_end = 0
        for pair in ranges:
            if not isinstance(pair, list) or len(pair) != 2:
                return None
            if any(isinstance(value, bool) for value in pair):
                return None
            try:
                start, count = int(pair[0]), int(pair[1])
            except (TypeError, ValueError):
                return None
            end = start + count
            if start < previous_end or count <= 0 or end > chunk_count:
                return None
            for index in range(start, end):
                if index < chunk_count - 1:
                    length = meta.chunk_size
                else:
                    length = meta.wire_size - meta.chunk_size * (chunk_count - 1)
                received[index] = length
            previous_end = end
        return received

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
            "updated": time.time(),
        }
        if end is not None:
            payload["end"] = self.end_json(end)
        if destination is not None:
            payload["destination"] = str(destination)
        self.atomic_json(self.incoming_manifest(meta.transfer_id), payload)

    def load_incoming(
        self,
        transfer_id: int,
    ) -> tuple[dict[str, Any], MetaMessage] | None:
        payload = self.read_json(self.incoming_manifest(transfer_id))
        if payload is None or payload.get("schema") != STATE_SCHEMA:
            return None
        if payload.get("transfer_id") != transfer_id_text(transfer_id):
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
        self.atomic_json(
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
        self.atomic_json(self.outgoing_manifest(transfer_id), document)

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
                result.append(value)
        result.sort(key=lambda item: float(item.get("updated", 0)), reverse=True)
        return result

    def cleanup(self) -> None:
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
                updated = float(value.get("updated", 0)) if value else 0.0
            except (TypeError, ValueError):
                updated = 0.0
            entries.append((updated, path))
        entries.sort(reverse=True)
        for index, (updated, path) in enumerate(entries):
            if index < maximum and now - updated <= self.ttl_s:
                continue
            path.unlink(missing_ok=True)
            if with_parts:
                path.with_suffix(".part").unlink(missing_ok=True)

    def _cleanup_part_budget(self) -> None:
        parts: list[tuple[float, Path, int]] = []
        total = 0
        for part in self.incoming_dir.glob("*.part"):
            manifest = part.with_suffix(".json")
            if not manifest.exists():
                part.unlink(missing_ok=True)
                continue
            try:
                stat = part.stat()
            except OSError:
                continue
            parts.append((stat.st_mtime, part, stat.st_size))
            total += stat.st_size
        if total <= self.max_part_bytes:
            return
        parts.sort()
        for _mtime, part, size in parts:
            if total <= self.max_part_bytes:
                break
            part.unlink(missing_ok=True)
            part.with_suffix(".json").unlink(missing_ok=True)
            total -= size
