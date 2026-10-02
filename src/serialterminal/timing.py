from __future__ import annotations

import json
from pathlib import Path
import threading
import time
from typing import Any, Protocol


class TimingSink(Protocol):
    def __call__(self, event: str, **fields: Any) -> None:
        ...


def timing_log_path(path: str | Path) -> Path:
    raw_path = Path(path)
    if raw_path.name.endswith(".log"):
        name = raw_path.name[:-4] + ".fttiming.jsonl"
    else:
        name = raw_path.name + ".fttiming.jsonl"
    return raw_path.with_name(name)


class TimingTrace:
    """Collect monotonic timing events in RAM and write them only on close."""

    def __init__(self, log_path: str | Path):
        self.path = timing_log_path(log_path)
        self._lock = threading.Lock()
        self._events: list[dict[str, Any]] = []
        self._next_seq = 1
        self._closed = False

    def record(self, event: str, **fields: Any) -> None:
        perf_ns = time.perf_counter_ns()
        timestamp = time.time()
        with self._lock:
            if self._closed:
                return
            record = {
                "seq": self._next_seq,
                "event": event,
                "perf_ns": perf_ns,
                "timestamp": timestamp,
                **fields,
            }
            self._next_seq += 1
            self._events.append(record)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            events = self._events
            self._events = []

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as file:
            for event in events:
                file.write(
                    json.dumps(
                        event,
                        ensure_ascii=False,
                        separators=(",", ":"),
                        sort_keys=True,
                    )
                    + "\n"
                )
