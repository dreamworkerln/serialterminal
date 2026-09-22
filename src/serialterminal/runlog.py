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


def console_log_path(path: str | Path) -> Path:
    raw_path = Path(path)
    if raw_path.name.endswith(".log"):
        name = raw_path.name[:-4] + ".console.log"
    else:
        name = raw_path.name + ".console.log"
    return raw_path.with_name(name)


def format_console_record(
    session: str,
    direction: str,
    text: str,
    *,
    timestamp: float | None = None,
) -> str:
    """Render one shared human-console audit record for any frontend."""
    markers = {">": "I", "<": "O"}
    if direction not in markers:
        raise ValueError("console direction must be '>' or '<'")
    moment = (
        datetime.now().astimezone()
        if timestamp is None
        else datetime.fromtimestamp(timestamp).astimezone()
    )
    # Одна logical record должна оставаться одной физической строкой logfile,
    # даже если caller передал control characters внутри line text.
    visible_text = text.replace("\r", "\\r").replace("\n", "\\n")
    return (
        f"{moment.isoformat(timespec='milliseconds')} "
        f"[{session}] [{markers[direction]}] {visible_text}\n"
    )


class RunLog:
    """Thread-safe forensic log plus companion human-console view for one run."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else default_log_path()
        self.console_path = console_log_path(self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.console_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._event_sequences: dict[str, int] = {}
        self._file = self.path.open("a", encoding="utf-8", buffering=1)
        self._console_file = self.console_path.open(
            "a", encoding="utf-8", buffering=1
        )
        self.record("RUN", {"event": "start", "pid": os.getpid()})

    @staticmethod
    def _render_payload(payload: Any) -> str:
        if isinstance(payload, str):
            return payload
        return json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )

    @staticmethod
    def _timestamp(timestamp: float | None = None) -> str:
        moment = (
            datetime.now().astimezone()
            if timestamp is None
            else datetime.fromtimestamp(timestamp).astimezone()
        )
        return moment.isoformat(timespec="milliseconds")

    def _write_record_unlocked(self, tag: str, payload: Any) -> None:
        self._file.write(
            f"{self._timestamp()} [{tag}] {self._render_payload(payload)}\n"
        )

    @staticmethod
    def _event_position(tag: str, payload: Any) -> tuple[str, int] | None:
        if not isinstance(payload, dict):
            return None
        if tag not in {"STATE", "TX", "ERROR"} and not tag.startswith("RX "):
            return None
        session = payload.get("session")
        seq = payload.get("seq")
        if (
            not isinstance(session, str)
            or isinstance(seq, bool)
            or not isinstance(seq, int)
        ):
            return None
        return session, seq

    def _record_gap_if_needed_unlocked(self, tag: str, payload: Any) -> None:
        position = self._event_position(tag, payload)
        if position is None:
            return
        session, seq = position
        previous = self._event_sequences.get(session, 0)
        if seq > previous + 1:
            self._write_record_unlocked(
                "ERROR",
                {
                    "event": "forensic_gap",
                    "session": session,
                    "last_logged_seq": previous,
                    "next_logged_seq": seq,
                    "lost_seq_first": previous + 1,
                    "lost_seq_last": seq - 1,
                },
            )
        if seq > previous:
            self._event_sequences[session] = seq

    def write(self, text: str) -> None:
        with self._lock:
            self._file.write(text)
            self._file.flush()

    def record(self, tag: str, payload: Any) -> None:
        with self._lock:
            self._record_gap_if_needed_unlocked(tag, payload)
            self._write_record_unlocked(tag, payload)
            self._file.flush()

    def record_console(
        self,
        session: str,
        direction: str,
        text: str,
        *,
        timestamp: float | None = None,
    ) -> None:
        with self._lock:
            self._console_file.write(
                format_console_record(
                    session,
                    direction,
                    text,
                    timestamp=timestamp,
                )
            )
            self._console_file.flush()

    def close(self) -> None:
        with self._lock:
            if self._file.closed:
                return
            self._write_record_unlocked("RUN", {"event": "stop", "pid": os.getpid()})
            self._file.flush()
            self._console_file.flush()
            self._file.close()
            self._console_file.close()

    def __enter__(self) -> RunLog:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
