from __future__ import annotations

from dataclasses import dataclass, field
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


@dataclass
class _RxLineState:
    parts: list[str] = field(default_factory=list)
    seq_first: int | None = None
    seq_last: int | None = None


class RunLog:
    """One thread-safe chronological logfile owned by one process invocation."""

    _RX_LINE_BOUNDARY_STATES = frozenset(
        {"reconnecting", "connected", "disconnected", "closed"}
    )

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else default_log_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._file = self.path.open("a", encoding="utf-8", buffering=1)
        self._rx_line_states: dict[tuple[str, str], _RxLineState] = {}
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

    def _write_record_unlocked(self, tag: str, payload: Any) -> None:
        timestamp = datetime.now().astimezone().isoformat(timespec="milliseconds")
        self._file.write(f"{timestamp} [{tag}] {self._render_payload(payload)}\n")

    def _rx_line_records(self, payload: Any) -> list[tuple[str, dict[str, Any]]]:
        if not isinstance(payload, dict):
            return []

        session = payload.get("session")
        stream = payload.get("stream")
        seq = payload.get("seq")
        text = payload.get("text")
        if (
            not isinstance(session, str)
            or not session
            or not isinstance(stream, str)
            or not stream
            or isinstance(seq, bool)
            or not isinstance(seq, int)
            or not isinstance(text, str)
        ):
            return []

        key = (session, stream)
        state = self._rx_line_states.setdefault(key, _RxLineState())

        # Даже если incremental decoder пока не выдал символ (например, первая
        # половина UTF-8 code point), raw chunk уже относится к будущей строке.
        if payload.get("data_b64") is not None and state.seq_first is None:
            state.seq_first = seq
            state.seq_last = seq

        records: list[tuple[str, dict[str, Any]]] = []
        for character in text:
            if state.seq_first is None:
                state.seq_first = seq
            state.seq_last = seq

            if character != "\n":
                state.parts.append(character)
                continue

            line_text = "".join(state.parts)
            if line_text.endswith("\r"):
                line_text = line_text[:-1]
            records.append(
                (
                    f"RX LINE {stream}",
                    {
                        "session": session,
                        "stream": stream,
                        "text": line_text,
                        "seq_first": state.seq_first,
                        "seq_last": state.seq_last,
                    },
                )
            )
            state.parts.clear()
            state.seq_first = None
            state.seq_last = None

        if state.seq_first is not None and payload.get("data_b64") is not None:
            state.seq_last = seq
        return records

    def _flush_session_partials(
        self,
        session: str | None = None,
    ) -> list[tuple[str, dict[str, Any]]]:
        records: list[tuple[str, dict[str, Any]]] = []
        for key in list(self._rx_line_states):
            current_session, stream = key
            if session is not None and current_session != session:
                continue

            state = self._rx_line_states.pop(key)
            if not state.parts or state.seq_first is None or state.seq_last is None:
                continue
            records.append(
                (
                    f"RX PARTIAL {stream}",
                    {
                        "session": current_session,
                        "stream": stream,
                        "text": "".join(state.parts),
                        "seq_first": state.seq_first,
                        "seq_last": state.seq_last,
                    },
                )
            )
        return records

    def write(self, text: str) -> None:
        with self._lock:
            self._file.write(text)
            self._file.flush()

    def record(self, tag: str, payload: Any) -> None:
        with self._lock:
            # Граница connection lifecycle не должна склеивать незавершённую
            # logical line с байтами уже следующего transport connection.
            if tag == "STATE" and isinstance(payload, dict):
                state = payload.get("state")
                session = payload.get("session")
                if state in self._RX_LINE_BOUNDARY_STATES and isinstance(session, str):
                    for partial_tag, partial_payload in self._flush_session_partials(
                        session
                    ):
                        self._write_record_unlocked(partial_tag, partial_payload)

            self._write_record_unlocked(tag, payload)

            if tag.startswith("RX ") and not tag.startswith(("RX LINE ", "RX PARTIAL ")):
                for line_tag, line_payload in self._rx_line_records(payload):
                    self._write_record_unlocked(line_tag, line_payload)
            self._file.flush()

    def close(self) -> None:
        with self._lock:
            if self._file.closed:
                return
            for partial_tag, partial_payload in self._flush_session_partials():
                self._write_record_unlocked(partial_tag, partial_payload)
            self._write_record_unlocked("RUN", {"event": "stop", "pid": os.getpid()})
            self._file.flush()
            self._file.close()

    def __enter__(self) -> RunLog:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
