from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any

CACHE_VERSION = 1


def default_cache_path() -> Path:
    override = os.environ.get("SERIALTERMINAL_CACHE_FILE")
    if override:
        return Path(override).expanduser()
    root = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return root / "serialterminal" / "devices.json"


def _empty_cache() -> dict[str, Any]:
    return {"version": CACHE_VERSION, "devices": {}}


def load_cache(path: str | Path | None = None) -> dict[str, Any]:
    target = Path(path) if path is not None else default_cache_path()
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return _empty_cache()
    if not isinstance(data, dict) or not isinstance(data.get("devices"), dict):
        return _empty_cache()
    data.setdefault("version", CACHE_VERSION)
    return data


def save_cache(data: dict[str, Any], path: str | Path | None = None) -> Path:
    target = Path(path) if path is not None else default_cache_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, target)
    return target


def cache_key(kind: str, address: str) -> str:
    return f"{kind}:{address.strip().lower()}"


def get_cached_device(
    kind: str,
    address: str,
    path: str | Path | None = None,
) -> dict[str, Any] | None:
    return load_cache(path)["devices"].get(cache_key(kind, address))


def capability_confirmed(record: dict[str, Any] | None, capability: str) -> bool:
    return bool(record and record.get("capabilities", {}).get(capability) is True)


def update_cached_device(
    *,
    kind: str,
    address: str,
    name: str | None,
    capabilities: dict[str, Any],
    probe_status: str,
    error: str | None = None,
    metadata: dict[str, Any] | None = None,
    path: str | Path | None = None,
) -> Path:
    data = load_cache(path)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    key = cache_key(kind, address)
    previous = data["devices"].get(key, {})
    merged_metadata = dict(previous.get("metadata", {}))
    if metadata:
        merged_metadata.update(metadata)
    data["devices"][key] = {
        "kind": kind,
        "address": address,
        "name": name or previous.get("name") or "<unnamed>",
        "capabilities": dict(capabilities),
        "probe_status": probe_status,
        "error": error,
        "last_seen": now,
        "last_probe": now,
        "metadata": merged_metadata,
    }
    return save_cache(data, path)


def confirmed_devices(
    kind: str,
    capability: str,
    path: str | Path | None = None,
) -> list[dict[str, Any]]:
    data = load_cache(path)
    result = []
    for record in data["devices"].values():
        if record.get("kind") != kind:
            continue
        if capability_confirmed(record, capability):
            result.append(record)
    result.sort(
        key=lambda item: (
            (item.get("name") or "").lower(),
            (item.get("address") or "").lower(),
        )
    )
    return result
