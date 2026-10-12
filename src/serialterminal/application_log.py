from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
import sys
import threading
import traceback

from .runlog import default_log_path

_active_log = None


class ApplicationLog:
    """Лог процесса: ошибки сохраняются сразу, независимо от session logs."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else default_log_path(prefix="serialterminal-application")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.path.open("a", encoding="utf-8")
        self._lock = threading.Lock()
        self.error_count = 0
        self.last_error = ""
        self._previous_hook = None
        self._previous_log = None

    def __enter__(self):
        global _active_log
        self._previous_log = _active_log
        _active_log = self
        self._previous_hook = threading.excepthook
        self._hook = self._thread_error
        threading.excepthook = self._hook
        self.note(f"START pid={os.getpid()} python={sys.version.split()[0]}")
        return self

    def __exit__(self, *args):
        global _active_log
        if threading.excepthook is self._hook:
            threading.excepthook = self._previous_hook
        if _active_log is self:
            _active_log = self._previous_log
        self.note("STOP")
        with self._lock:
            self._file.close()

    def _write(self, text, *, durable=False):
        try:
            with self._lock:
                stamp = datetime.now().astimezone().isoformat(timespec="milliseconds")
                self._file.write(f"{stamp} {text}\n")
                self._file.flush()
                if durable:
                    os.fsync(self._file.fileno())
        except (OSError, ValueError) as exc:
            # Ошибка самого logger не должна подменять исходное исключение.
            print(f"ST application log unavailable: {exc}", file=sys.stderr)

    def note(self, text):
        self._write(f"[INFO] {text}")

    def exception(self, exc: BaseException, context: str):
        summary = f"{type(exc).__name__}: {exc}".splitlines()[0]
        with self._lock:
            self.error_count += 1
            self.last_error = summary
        stack = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        self._write(f"[ERROR] {context}: {summary}\n{stack.rstrip()}", durable=True)

    def _thread_error(self, args):
        if args.exc_type is not SystemExit:
            self.exception(args.exc_value, f"thread:{args.thread.name if args.thread else 'unknown'}")


def report_exception(exc: BaseException, context: str) -> Path | None:
    log = _active_log
    if log is None:
        return None
    log.exception(exc, context)
    return log.path


def error_snapshot() -> tuple[int, str, Path | None]:
    log = _active_log
    if log is None:
        return 0, "", None
    with log._lock:
        return log.error_count, log.last_error, log.path


def report_event(context: str) -> None:
    log = _active_log
    if log is not None:
        log.note(context)
