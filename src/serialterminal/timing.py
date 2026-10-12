from __future__ import annotations

import json
import queue
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
    """Ограниченный буфер таймингов с записью пачек отдельным worker."""

    def __init__(self, log_path: str | Path, *, batch_size: int = 256):
        if type(batch_size) is not int or batch_size < 1:
            raise ValueError("timing batch_size must be a positive integer")
        self.path = timing_log_path(log_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Новый TUI session с тем же log path не стирает предыдущую часть run.
        self._file = self.path.open("a", encoding="utf-8")
        self._lock = threading.Lock()
        self._events: list[dict[str, Any]] = []
        self._next_seq = 1
        self._closed = False
        self._batch_size = batch_size
        self._queue = queue.Queue(maxsize=8)
        self._write_error: Exception | None = None
        self._worker = threading.Thread(target=self._write_batches, name="serialterminal-timing-log", daemon=True)
        self._worker.start()

    def record(self, event: str, **fields: Any) -> None:
        with self._lock:
            if self._closed or self._write_error is not None:
                return
            record = {
                "seq": self._next_seq,
                "event": event,
                "perf_ns": time.perf_counter_ns(),
                "timestamp": time.time(),
                **fields,
            }
            self._next_seq += 1
            self._events.append(record)
            if len(self._events) >= self._batch_size:
                batch, self._events = self._events, []
                # Bounded queue сохраняет порядок и не теряет строки молча.
                # Если диск отстаёт на восемь пачек, producer ждёт worker.
                self._queue.put(batch)

    def _write_batches(self) -> None:
        from .application_log import report_exception

        try:
            while True:
                batch = self._queue.get()
                try:
                    if batch is None:
                        return
                    if self._write_error is None:
                        try:
                            for event in batch:
                                self._file.write(json.dumps(event, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n")
                            # flush отдаёт пачку ядру; fsync каждого batch не нужен.
                            self._file.flush()
                        except Exception as exc:
                            self._write_error = exc
                            report_exception(exc, "timing log writer")
                finally:
                    self._queue.task_done()
        finally:
            try:
                self._file.close()
            except Exception as exc:
                if self._write_error is None:
                    self._write_error = exc
                    report_exception(exc, "timing log close")

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            if self._events:
                self._queue.put(self._events)
                self._events = []
            self._queue.put(None)
        self._worker.join()
        if self._write_error is not None:
            raise OSError(f"timing log incomplete: {self.path}: {self._write_error}") from self._write_error
