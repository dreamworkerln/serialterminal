from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import threading
from typing import Any


def default_log_path(
    *,
    log_dir: str | Path = "logs",
    prefix: str = "serialterminal",
) -> Path:
    directory = Path(log_dir)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S-%f")
    return directory / f"{prefix}-{stamp}-p{os.getpid()}.log"


class RunLog:
    """One thread-safe chronological logfile owned by one process invocation."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else default_log_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._file = self.path.open("a", encoding="utf-8", buffering=1)
        self.record("RUN", {"event": "start", "pid": os.getpid()})

    def write(self, text: str) -> None:
        with self._lock:
            self._file.write(text)
            self._file.flush()

    def record(self, tag: str, payload: Any) -> None:
        timestamp = datetime.now().astimezone().isoformat(timespec="milliseconds")
        if isinstance(payload, str):
            rendered = payload
        else:
            rendered = json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
        self.write(f"{timestamp} [{tag}] {rendered}\n")

    def close(self) -> None:
        with self._lock:
            if self._file.closed:
                return
            timestamp = datetime.now().astimezone().isoformat(timespec="milliseconds")
            self._file.write(
                f"{timestamp} [RUN] "
                + json.dumps(
                    {"event": "stop", "pid": os.getpid()},
                    separators=(",", ":"),
                    sort_keys=True,
                )
                + "\n"
            )
            self._file.flush()
            self._file.close()

    def __enter__(self) -> RunLog:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
