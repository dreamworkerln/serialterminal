from __future__ import annotations

import base64
from dataclasses import asdict
import json
import sys
import threading
import time
from typing import Any, Callable, TextIO

from .runlog import RunLog
from .session import (
    ManagedSession,
    SessionClosedError,
    SessionCursorExpired,
    SessionEvent,
    SessionLine,
    encode_line,
)


CHATTER_ID_COMMAND = "/id"
_EOL = {"lf": "\n", "crlf": "\r\n", "cr": "\r"}
_HUMAN_CONSOLE_STREAMS = frozenset({"main", "chat"})


class AgentError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def _default_selector_factory(scope: str, baud: int, scan_seconds: float):
    # Импорт ленивый, чтобы CLI мог подключать agent frontend без циклического
    # top-level import и без отдельной копии discovery/transport factory logic.
    from .cli import DeviceSelector

    return DeviceSelector(scope, baud=baud, scan_seconds=scan_seconds)


def _event_dict(event: SessionEvent) -> dict[str, Any]:
    result = {
        key: value
        for key, value in asdict(event).items()
        if value is not None and key != "data"
    }
    if event.data is not None:
        result["data_b64"] = base64.b64encode(event.data).decode("ascii")
    return result


def _line_dict(line: SessionLine) -> dict[str, Any]:
    return {
        "stream": line.stream,
        "seq_first": line.seq_first,
        "seq_last": line.seq_last,
        "text": line.text,
    }


def _render_response(response: dict[str, Any]) -> str:
    return json.dumps(
        response,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _request_id_key(request_id: Any) -> str:
    return json.dumps(
        request_id,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


class SessionManager:
    """Own multiple independent ManagedSession objects for machine clients."""

    def __init__(
        self,
        *,
        run_log: RunLog | None = None,
        selector_factory: Callable[[str, int, float], Any] | None = None,
        default_baud: int = 115200,
        default_scan_seconds: float = 3.0,
        reconnect_delay: float = 0.5,
    ):
        self.run_log = run_log
        self.selector_factory = selector_factory or _default_selector_factory
        self.default_baud = default_baud
        self.default_scan_seconds = default_scan_seconds
        self.reconnect_delay = reconnect_delay

        self._lock = threading.Lock()
        self._observe_condition = threading.Condition()
        self._observe_cancelled = threading.Event()
        self._candidates: dict[str, tuple[Any, Any]] = {}
        self._sessions: dict[str, ManagedSession] = {}
        self._session_device_keys: dict[str, str] = {}
        self._device_sessions: dict[str, str] = {}
        self._event_loggers: dict[str, tuple[threading.Event, threading.Thread]] = {}
        self._next_session_id = 1

    def _get_session(self, session_id: str) -> ManagedSession:
        with self._lock:
            session = self._sessions.get(session_id)
        if session is None:
            raise AgentError("unknown_session", f"unknown session: {session_id}")
        return session

    def _notify_event_activity(self) -> None:
        # Это только manager-level doorbell. Сами raw events, logical lines и
        # cursor semantics остаются в соответствующем ManagedSession.
        with self._observe_condition:
            self._observe_condition.notify_all()

    def cancel_observes(self) -> None:
        """Wake pending observe requests during agent-process shutdown."""
        self._observe_cancelled.set()
        self._notify_event_activity()

    def discover(
        self,
        *,
        scope: str = "auto",
        baud: int | None = None,
        scan_seconds: float | None = None,
    ) -> dict[str, Any]:
        actual_baud = self.default_baud if baud is None else int(baud)
        actual_scan = (
            self.default_scan_seconds if scan_seconds is None else float(scan_seconds)
        )
        selector = self.selector_factory(scope, actual_baud, actual_scan)
        candidates = selector.discover()

        with self._lock:
            for candidate in candidates:
                self._candidates[candidate.key] = (candidate, selector)

        return {
            "devices": [
                {
                    "key": candidate.key,
                    "kind": candidate.kind,
                    "label": candidate.label,
                    "detail": candidate.detail,
                }
                for candidate in candidates
            ]
        }

    def _next_session(self) -> str:
        with self._lock:
            session_id = f"s{self._next_session_id}"
            self._next_session_id += 1
            return session_id

    def _log_event(self, session_id: str, event: SessionEvent) -> None:
        if self.run_log is None:
            return
        payload = {"session": session_id, **_event_dict(event)}
        if event.kind == "rx":
            tag = f"RX {event.stream or '-'}"
        elif event.kind == "tx":
            tag = "TX"
        elif event.kind == "state":
            tag = "STATE"
        else:
            tag = "ERROR"
        self.run_log.record(tag, payload)

    def _log_console_line(self, session_id: str, line: SessionLine) -> None:
        if self.run_log is None or line.stream not in _HUMAN_CONSOLE_STREAMS:
            return
        # BLE machine telemetry намеренно не попадает в human-console view. Если
        # firmware в /both сама дублирует telemetry в chat stream, такая строка
        # естественно попадёт сюда, потому что authority — фактический human stream.
        self.run_log.record_console(
            session_id,
            "<",
            line.text,
            timestamp=line.timestamp,
        )

    def _event_logger_loop(
        self,
        session_id: str,
        session: ManagedSession,
        stop_event: threading.Event,
    ) -> None:
        cursor = 0
        while not stop_event.is_set():
            try:
                events = session.events_after(cursor, timeout=0.2)
            except SessionCursorExpired as exc:
                cursor = exc.oldest_seq - 1
                continue
            for event in events:
                self._log_event(session_id, event)
                cursor = event.seq

        try:
            events = session.events_after(cursor)
        except SessionCursorExpired as exc:
            cursor = exc.oldest_seq - 1
            events = session.events_after(cursor)
        for event in events:
            self._log_event(session_id, event)

    def _start_event_logger(self, session_id: str, session: ManagedSession) -> None:
        if self.run_log is None:
            return
        stop_event = threading.Event()
        thread = threading.Thread(
            target=self._event_logger_loop,
            args=(session_id, session, stop_event),
            name=f"serialterminal-agent-log-{session_id}",
            daemon=True,
        )
        self._event_loggers[session_id] = (stop_event, thread)
        thread.start()

    def _stop_event_logger(self, session_id: str) -> None:
        pair = self._event_loggers.pop(session_id, None)
        if pair is None:
            return
        stop_event, thread = pair
        stop_event.set()
        thread.join(timeout=1.0)

    def open(
        self,
        device_key: str,
        *,
        eol: str = "lf",
        auto_id: bool = True,
        wait_connected_ms: int = 10000,
    ) -> dict[str, Any]:
        if eol not in _EOL:
            raise AgentError("invalid_eol", f"unsupported eol: {eol}")
        if wait_connected_ms < 0:
            raise AgentError("invalid_timeout", "wait_connected_ms must be non-negative")

        with self._lock:
            existing = self._device_sessions.get(device_key)
            cached = self._candidates.get(device_key)
        if existing is not None:
            raise AgentError(
                "device_busy",
                f"device is already owned by session {existing}",
                {"session": existing, "device_key": device_key},
            )
        if cached is None:
            raise AgentError(
                "unknown_device",
                "device_key is not in the current discovery cache; run discover first",
                {"device_key": device_key},
            )

        candidate, selector = cached
        try:
            transport = selector.make_transport(candidate)
        except Exception as exc:
            raise AgentError("open_failed", str(exc)) from exc

        line_ending = _EOL[eol]
        preamble = (
            (lambda _transport: encode_line(CHATTER_ID_COMMAND, line_ending))
            if auto_id
            else None
        )
        session_id = self._next_session()
        session = ManagedSession(
            transport,
            line_ending=line_ending,
            reconnect_delay=self.reconnect_delay,
            connect_preamble=preamble,
            event_notifier=self._notify_event_activity,
            line_notifier=lambda line: self._log_console_line(session_id, line),
        )

        with self._lock:
            # Повторная проверка закрывает race между двумя одновременными open.
            existing = self._device_sessions.get(device_key)
            if existing is not None:
                transport.close()
                raise AgentError(
                    "device_busy",
                    f"device is already owned by session {existing}",
                    {"session": existing, "device_key": device_key},
                )
            self._sessions[session_id] = session
            self._session_device_keys[session_id] = device_key
            self._device_sessions[device_key] = session_id

        self._start_event_logger(session_id, session)
        try:
            session.start()
        except Exception:
            self._stop_event_logger(session_id)
            with self._lock:
                self._sessions.pop(session_id, None)
                self._session_device_keys.pop(session_id, None)
                self._device_sessions.pop(device_key, None)
            transport.close()
            raise

        connected = session.wait_connected(wait_connected_ms / 1000.0)
        return {
            "session": session_id,
            "device_key": device_key,
            "description": transport.description,
            "state": "connected" if connected else "reconnecting",
            "streams": list(transport.stream_capabilities),
            "latest_seq": session.latest_event_seq(),
            "auto_id": auto_id,
        }

    def status(self, session_id: str) -> dict[str, Any]:
        session = self._get_session(session_id)
        transport = session._current_transport()
        return {
            "session": session_id,
            "device_key": transport.device_key,
            "description": transport.description,
            "connected": session.connected_event.is_set(),
            "state": (
                "closed"
                if session.stop_event.is_set()
                else "connected"
                if session.connected_event.is_set()
                else "reconnecting"
            ),
            "streams": list(transport.stream_capabilities),
            "latest_seq": session.latest_event_seq(),
            "queued_tx": session.outgoing.qsize(),
        }

    def list_sessions(self) -> dict[str, Any]:
        with self._lock:
            ids = list(self._sessions)
        return {"sessions": [self.status(session_id) for session_id in ids]}

    def send_line(
        self,
        session_id: str,
        text: str,
        *,
        eol: str | None = None,
    ) -> dict[str, Any]:
        session = self._get_session(session_id)
        ending = None
        if eol is not None:
            if eol not in _EOL:
                raise AgentError("invalid_eol", f"unsupported eol: {eol}")
            ending = _EOL[eol]
        try:
            tx_id = session.queue_line(text, line_ending=ending)
        except SessionClosedError as exc:
            raise AgentError("session_closed", str(exc)) from exc
        if self.run_log is not None:
            self.run_log.record_console(session_id, ">", text)
        return {"tx_id": tx_id, "state": "queued"}

    def send_bytes(self, session_id: str, data: bytes) -> dict[str, Any]:
        session = self._get_session(session_id)
        try:
            tx_id = session.queue_bytes(data)
        except SessionClosedError as exc:
            raise AgentError("session_closed", str(exc)) from exc
        return {"tx_id": tx_id, "state": "queued", "size": len(data)}

    def _resolve_observe_sessions(
        self,
        cursors: dict[str, int],
    ) -> list[tuple[str, ManagedSession, int]]:
        watched: list[tuple[str, ManagedSession, int]] = []
        for session_id, cursor in cursors.items():
            if not isinstance(session_id, str) or not session_id:
                raise AgentError(
                    "invalid_request",
                    "observe cursor keys must be non-empty session strings",
                )
            if isinstance(cursor, bool) or not isinstance(cursor, int) or cursor < 0:
                raise AgentError(
                    "invalid_cursor",
                    f"invalid event cursor for session {session_id}: {cursor!r}",
                    {"session": session_id, "requested_seq": cursor},
                )
            try:
                session = self._get_session(session_id)
            except AgentError as exc:
                if exc.code != "unknown_session":
                    raise
                raise AgentError(
                    "unknown_session",
                    f"unknown session: {session_id}",
                    {"session": session_id},
                ) from exc
            watched.append((session_id, session, cursor))
        return watched

    @staticmethod
    def _read_observation_snapshot(
        session_id: str,
        session: ManagedSession,
        cursor: int,
    ) -> tuple[list[SessionEvent], list[SessionLine]]:
        try:
            return session.observation_after(cursor)
        except SessionCursorExpired as exc:
            raise AgentError(
                "cursor_expired",
                f"{session_id}: {exc}",
                {
                    "session": session_id,
                    "requested_seq": exc.requested_seq,
                    "oldest_seq": exc.oldest_seq,
                },
            ) from exc
        except ValueError as exc:
            raise AgentError(
                "invalid_cursor",
                f"{session_id}: {exc}",
                {"session": session_id, "requested_seq": cursor},
            ) from exc

    def _collect_observation(
        self,
        watched: list[tuple[str, ManagedSession, int]],
    ) -> tuple[
        list[tuple[float, str, int, SessionEvent]],
        list[tuple[float, str, int, SessionLine]],
        dict[str, int],
    ]:
        events: list[tuple[float, str, int, SessionEvent]] = []
        lines: list[tuple[float, str, int, SessionLine]] = []
        current_cursors: dict[str, int] = {}

        for session_id, session, cursor in watched:
            available, completed = self._read_observation_snapshot(
                session_id, session, cursor
            )
            current_cursors[session_id] = available[-1].seq if available else cursor
            for event in available:
                events.append((event.timestamp, session_id, event.seq, event))
            for line in completed:
                lines.append((line.timestamp, session_id, line.seq_last, line))

        return events, lines, current_cursors

    @staticmethod
    def _observation_result(
        events: list[tuple[float, str, int, SessionEvent]],
        lines: list[tuple[float, str, int, SessionLine]],
        cursors: dict[str, int],
        *,
        timed_out: bool,
    ) -> dict[str, Any]:
        events.sort(key=lambda item: (item[0], item[1], item[2]))
        lines.sort(key=lambda item: (item[0], item[1], item[2]))
        return {
            "events": [
                {"session": session_id, **_event_dict(event)}
                for _, session_id, _, event in events
            ],
            "lines": [
                {"session": session_id, **_line_dict(line)}
                for _, session_id, _, line in lines
            ],
            "cursors": dict(cursors),
            "timed_out": timed_out,
        }

    def observe(
        self,
        cursors: dict[str, int],
        *,
        timeout_ms: int = 0,
    ) -> dict[str, Any]:
        if not cursors:
            raise AgentError("invalid_request", "observe requires non-empty cursors")
        if timeout_ms < 0:
            raise AgentError("invalid_timeout", "timeout_ms must be non-negative")

        watched = self._resolve_observe_sessions(cursors)
        deadline = time.monotonic() + timeout_ms / 1000.0

        # Держим manager condition во время snapshot scan. Session _record_event
        # уведомляет этот condition уже после освобождения своего event lock, поэтому
        # событие между scan и observe-wait не может потеряться и lock order не зацикливается.
        with self._observe_condition:
            while True:
                if self._observe_cancelled.is_set():
                    raise AgentError("agent_stopping", "agent process is stopping")

                events, lines, current_cursors = self._collect_observation(watched)
                if events:
                    return self._observation_result(
                        events,
                        lines,
                        current_cursors,
                        timed_out=False,
                    )
                if timeout_ms == 0:
                    return self._observation_result(
                        [],
                        [],
                        current_cursors,
                        timed_out=False,
                    )

                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return self._observation_result(
                        [],
                        [],
                        current_cursors,
                        timed_out=True,
                    )
                self._observe_condition.wait(timeout=remaining)

    def close(self, session_id: str) -> dict[str, Any]:
        session = self._get_session(session_id)
        with self._lock:
            device_key = self._session_device_keys.get(session_id)

        session.stop()
        self._stop_event_logger(session_id)

        with self._lock:
            self._sessions.pop(session_id, None)
            self._session_device_keys.pop(session_id, None)
            if device_key is not None:
                self._device_sessions.pop(device_key, None)
        return {"session": session_id, "state": "closed"}

    def close_all(self) -> None:
        with self._lock:
            ids = list(self._sessions)
        for session_id in ids:
            try:
                self.close(session_id)
            except Exception:
                pass


class AgentProtocol:
    """Request/response JSONL adapter over SessionManager."""

    def __init__(self, manager: SessionManager, *, run_log: RunLog):
        self.manager = manager
        self.run_log = run_log

    @staticmethod
    def _request_id(request: Any) -> Any:
        return request.get("id") if isinstance(request, dict) else None

    @staticmethod
    def _normalize_observe_cursors(request: dict[str, Any]) -> dict[str, int]:
        cursors = request.get("cursors")
        if not isinstance(cursors, dict) or not cursors:
            raise AgentError(
                "invalid_request",
                "observe requires non-empty object field 'cursors'",
            )

        normalized: dict[str, int] = {}
        for session_id, cursor in cursors.items():
            if not isinstance(session_id, str) or not session_id:
                raise AgentError(
                    "invalid_request",
                    "observe cursor keys must be non-empty session strings",
                )
            if isinstance(cursor, bool) or not isinstance(cursor, int):
                raise AgentError(
                    "invalid_cursor",
                    f"invalid event cursor for session {session_id}: {cursor!r}",
                    {"session": session_id, "requested_seq": cursor},
                )
            normalized[session_id] = cursor
        return normalized

    def _handle_discover(self, request: dict[str, Any]) -> dict[str, Any]:
        return self.manager.discover(
            scope=request.get("scope", "auto"),
            baud=request.get("baud"),
            scan_seconds=request.get("scan_seconds"),
        )

    def _handle_open(self, request: dict[str, Any]) -> dict[str, Any]:
        device_key = request.get("device_key")
        if not isinstance(device_key, str) or not device_key:
            raise AgentError("invalid_request", "open requires device_key")
        return self.manager.open(
            device_key,
            eol=request.get("eol", "lf"),
            auto_id=bool(request.get("auto_id", True)),
            wait_connected_ms=int(request.get("wait_connected_ms", 10000)),
        )

    def _handle_list_sessions(self, request: dict[str, Any]) -> dict[str, Any]:
        return self.manager.list_sessions()

    def _handle_status(self, request: dict[str, Any]) -> dict[str, Any]:
        return self.manager.status(str(request.get("session", "")))

    def _handle_send_line(self, request: dict[str, Any]) -> dict[str, Any]:
        text = request.get("text")
        if not isinstance(text, str):
            raise AgentError("invalid_request", "send_line requires string text")
        return self.manager.send_line(
            str(request.get("session", "")),
            text,
            eol=request.get("eol"),
        )

    def _handle_send_bytes(self, request: dict[str, Any]) -> dict[str, Any]:
        encoded = request.get("data_b64")
        if not isinstance(encoded, str):
            raise AgentError("invalid_request", "send_bytes requires data_b64")
        try:
            data = base64.b64decode(encoded, validate=True)
        except Exception as exc:
            raise AgentError("invalid_base64", "data_b64 is not valid base64") from exc
        return self.manager.send_bytes(str(request.get("session", "")), data)

    def _handle_observe(self, request: dict[str, Any]) -> dict[str, Any]:
        if request.get("id") is None:
            raise AgentError(
                "invalid_request",
                "observe requires a non-null request id",
            )
        cursors = self._normalize_observe_cursors(request)
        try:
            timeout_ms = int(request.get("timeout_ms", 0))
        except (TypeError, ValueError) as exc:
            raise AgentError(
                "invalid_timeout",
                "timeout_ms must be an integer",
            ) from exc
        return self.manager.observe(cursors, timeout_ms=timeout_ms)

    def _handle_close(self, request: dict[str, Any]) -> dict[str, Any]:
        return self.manager.close(str(request.get("session", "")))

    def _dispatch(self, request: dict[str, Any]) -> dict[str, Any]:
        op = request.get("op")
        if not isinstance(op, str):
            raise AgentError("invalid_request", "request must contain string field 'op'")

        handlers = {
            "discover": self._handle_discover,
            "open": self._handle_open,
            "list_sessions": self._handle_list_sessions,
            "status": self._handle_status,
            "send_line": self._handle_send_line,
            "send_bytes": self._handle_send_bytes,
            "observe": self._handle_observe,
            "close": self._handle_close,
        }
        handler = handlers.get(op)
        if handler is None:
            raise AgentError("unknown_operation", f"unknown operation: {op}")
        return handler(request)

    def handle(self, request: Any) -> dict[str, Any]:
        request_id = self._request_id(request)
        try:
            if not isinstance(request, dict):
                raise AgentError("invalid_request", "JSON request must be an object")
            result = self._dispatch(request)
            return {"id": request_id, "ok": True, "result": result}
        except AgentError as exc:
            error = {"code": exc.code, "message": exc.message}
            if exc.details:
                error["details"] = exc.details
            return {"id": request_id, "ok": False, "error": error}
        except Exception as exc:
            return {
                "id": request_id,
                "ok": False,
                "error": {"code": "internal_error", "message": str(exc)},
            }

    def process_line(self, line: str) -> str:
        self.run_log.record("AGENT REQUEST", line.rstrip("\r\n"))
        try:
            request = json.loads(line)
        except json.JSONDecodeError as exc:
            response = {
                "id": None,
                "ok": False,
                "error": {
                    "code": "invalid_json",
                    "message": str(exc),
                },
            }
        else:
            response = self.handle(request)

        rendered = _render_response(response)
        self.run_log.record("AGENT RESPONSE", rendered)
        return rendered


class _AgentJsonlRunner:
    """Own JSONL request concurrency while keeping protocol semantics separate."""

    def __init__(
        self,
        manager: SessionManager,
        protocol: AgentProtocol,
        run_log: RunLog,
        input_stream: TextIO,
        output_stream: TextIO,
    ):
        self.manager = manager
        self.protocol = protocol
        self.run_log = run_log
        self.input_stream = input_stream
        self.output_stream = output_stream
        self._output_lock = threading.Lock()
        self._pending_lock = threading.Lock()
        self._pending_ids: set[str] = set()
        self._observe_threads: list[threading.Thread] = []

    def _emit_response(self, response: dict[str, Any]) -> None:
        rendered = _render_response(response)
        # Один lock задаёт одинаковый порядок строк в stdout и AGENT RESPONSE
        # даже когда background observe завершается одновременно с command reply.
        with self._output_lock:
            self.run_log.record("AGENT RESPONSE", rendered)
            self.output_stream.write(rendered + "\n")
            self.output_stream.flush()

    @staticmethod
    def _invalid_json_response(exc: json.JSONDecodeError) -> dict[str, Any]:
        return {
            "id": None,
            "ok": False,
            "error": {
                "code": "invalid_json",
                "message": str(exc),
            },
        }

    @staticmethod
    def _request_id_busy_response(request_id: Any) -> dict[str, Any]:
        return {
            "id": request_id,
            "ok": False,
            "error": {
                "code": "request_id_busy",
                "message": f"request id is already pending: {request_id!r}",
                "details": {"id": request_id},
            },
        }

    def _finish_observe(self, request: dict[str, Any], request_key: str) -> None:
        try:
            self._emit_response(self.protocol.handle(request))
        finally:
            with self._pending_lock:
                self._pending_ids.discard(request_key)

    def _request_is_pending(self, request_key: str) -> bool:
        with self._pending_lock:
            return request_key in self._pending_ids

    @staticmethod
    def _is_async_observe(request: Any, request_id: Any) -> bool:
        return (
            isinstance(request, dict)
            and request.get("op") == "observe"
            and request_id is not None
        )

    def _start_observe(self, request: dict[str, Any], request_key: str) -> None:
        with self._pending_lock:
            self._pending_ids.add(request_key)
        thread = threading.Thread(
            target=self._finish_observe,
            args=(request, request_key),
            name=f"serialterminal-agent-observe-{len(self._observe_threads) + 1}",
            daemon=True,
        )
        self._observe_threads.append(thread)
        thread.start()

    def _handle_request(self, request: Any) -> None:
        request_id = AgentProtocol._request_id(request)
        request_key = (
            _request_id_key(request_id) if request_id is not None else None
        )
        if request_key is not None and self._request_is_pending(request_key):
            self._emit_response(self._request_id_busy_response(request_id))
            return
        if self._is_async_observe(request, request_id):
            assert isinstance(request, dict)
            assert request_key is not None
            self._start_observe(request, request_key)
            return
        self._emit_response(self.protocol.handle(request))

    def _handle_line(self, line: str) -> None:
        self.run_log.record("AGENT REQUEST", line.rstrip("\r\n"))
        try:
            request = json.loads(line)
        except json.JSONDecodeError as exc:
            self._emit_response(self._invalid_json_response(exc))
            return
        self._handle_request(request)

    def _shutdown(self) -> None:
        # EOF/agent shutdown не должен ждать произвольно долгий user timeout. Сначала
        # отменяем pending observe, даём им вернуть correlated reply, затем закрываем
        # device sessions, пока RunLog/stdout ещё доступны.
        self.manager.cancel_observes()
        for thread in self._observe_threads:
            thread.join(timeout=1.0)
        self.manager.close_all()

    def run(self) -> None:
        try:
            for line in self.input_stream:
                if line.strip():
                    self._handle_line(line)
        finally:
            self._shutdown()


def run_agent(
    *,
    log_path: str | None = None,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
) -> int:
    input_stream = sys.stdin if stdin is None else stdin
    output_stream = sys.stdout if stdout is None else stdout

    with RunLog(log_path) as run_log:
        manager = SessionManager(run_log=run_log)
        protocol = AgentProtocol(manager, run_log=run_log)
        run_log.record(
            "AGENT",
            {
                "event": "ready",
                "log_path": str(run_log.path),
                "console_log_path": str(run_log.console_path),
            },
        )
        _AgentJsonlRunner(
            manager,
            protocol,
            run_log,
            input_stream,
            output_stream,
        ).run()
    return 0
