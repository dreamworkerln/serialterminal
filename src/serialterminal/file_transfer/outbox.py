from __future__ import annotations

from dataclasses import dataclass, field
import queue
import threading
import time
from typing import Any, Callable


class OutboxError(RuntimeError):
    pass


@dataclass
class _Job:
    action: Callable[[], Any]
    on_error: Callable[[Exception], None] | None = None
    done: threading.Event = field(default_factory=threading.Event)
    result: Any = None
    error: Exception | None = None


class Outbox:
    """Один bounded владелец отправки; RX ставит работу без transport waits."""

    def __init__(self, capacity: int = 16) -> None:
        self.queue: queue.Queue[_Job] = queue.Queue(maxsize=capacity)
        self.lock = threading.Lock()
        self.closed = False
        self.stopping = threading.Event()
        self.last_error: str | None = None
        self.callback_error: str | None = None
        self.worker = threading.Thread(target=self._run, name="serialterminal-ft1-outbox", daemon=True)
        self.worker.start()

    def submit(self, action, *, on_error=None) -> _Job:
        job = _Job(action, on_error)
        with self.lock:
            if self.closed:
                raise OutboxError("FT1 outbox is closed")
            try:
                self.queue.put_nowait(job)
            except queue.Full as exc:
                raise OutboxError("FT1 outbox is full") from exc
        return job

    def call(self, action, *, deadline=None):
        if threading.current_thread() is self.worker:
            return action()
        job = self.submit(action)
        remaining = None if deadline is None else max(0.0, deadline-time.monotonic())
        if not job.done.wait(remaining):
            # Работа уже могла начаться: caller не получает ложное non-delivery.
            raise OutboxError("FT1 outbound operation outcome is unknown at deadline")
        if job.error is not None:
            raise job.error
        return job.result

    def _run(self) -> None:
        while not self.stopping.is_set() or not self.queue.empty():
            try:
                job = self.queue.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                job.result = job.action()
            except Exception as exc:
                job.error = exc
                self.last_error = str(exc)
                if job.on_error is not None:
                    try:
                        job.on_error(exc)
                    except Exception as callback_exc:
                        # Ошибка callback видима, worker сохраняет остальные jobs.
                        self.callback_error = str(callback_exc)
            finally:
                job.done.set()
                self.queue.task_done()

    def discard_pending(self) -> None:
        discarded = []
        with self.lock:
            self.closed = True
            while True:
                try:
                    job = self.queue.get_nowait()
                except queue.Empty:
                    break
                discarded.append(job)
        for job in discarded:
            job.error = OutboxError("FT1 outbox closed before operation started")
            if job.on_error is not None:
                try:
                    job.on_error(job.error)
                except Exception as exc:
                    self.callback_error = str(exc)
            job.done.set()
            self.queue.task_done()

    def wait_idle(self, timeout: float) -> bool:
        deadline = time.monotonic() + max(0.0,timeout)
        with self.queue.all_tasks_done:
            while self.queue.unfinished_tasks:
                remaining = deadline-time.monotonic()
                if remaining <= 0:
                    return False
                self.queue.all_tasks_done.wait(remaining)
        return True

    def close(self, timeout: float = 1.0) -> None:
        with self.lock:
            self.closed = True
            self.stopping.set()
        if threading.current_thread() is not self.worker:
            self.worker.join(timeout=max(0.0, timeout))
