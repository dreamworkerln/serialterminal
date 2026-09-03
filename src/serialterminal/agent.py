from __future__ import annotations

import base64
from dataclasses import asdict
import json
import sys
import threading
from typing import Any, Callable, TextIO

from .runlog import RunLog
from .session import (
    ManagedSession,
    SessionClosedError,
    SessionCursorExpired,
    SessionEvent,
    encode_line,
)


CHATTER_ID_COMMAND = "/id"
_EOL = {"lf": "\n", "crlf": "\r\n", "cr": "\r"}


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
        session = ManagedSession(
            transport,
            line_ending=line_ending,
            reconnect_delay=self.reconnect_delay,
            connect_preamble=preamble,
        )
        session_id = self._next_session()

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
        return {"tx_id": tx_id, "state": "queued"}

    def send_bytes(self, session_id: str, data: bytes) -> dict[str, Any]:
        session = self._get_session(session_id)
        try:
            tx_id = session.queue_bytes(data)
        except SessionClosedError as exc:
            raise AgentError("session_closed", str(exc)) from exc
        return {"tx_id": tx_id, "state": "queued", "size": len(data)}

    def events(
        self,
        session_id: str,
        *,
        after_seq: int = 0,
        timeout_ms: int = 0,
        streams: list[str] | None = None,
        kinds: list[str] | None = None,
    ) -> dict[str, Any]:
        if timeout_ms < 0:
            raise AgentError("invalid_timeout", "timeout_ms must be non-negative")
        session = self._get_session(session_id)
        try:
            events = session.events_after(
                int(after_seq),
                timeout=timeout_ms / 1000.0,
                streams=streams,
                kinds=kinds,
            )
        except SessionCursorExpired as exc:
            raise AgentError(
                "cursor_expired",
                str(exc),
                {
                    "requested_seq": exc.requested_seq,
                    "oldest_seq": exc.oldest_seq,
                },
            ) from exc
        except ValueError as exc:
            raise AgentError("invalid_cursor", str(exc)) from exc

        return {
            "events": [_event_dict(event) for event in events],
            "timed_out": not events and timeout_ms > 0,
            "latest_seq": session.latest_event_seq(),
        }

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

    def _dispatch(self, request: dict[str, Any]) -> dict[str, Any]:
        op = request.get("op")
        if not isinstance(op, str):
            raise AgentError("invalid_request", "request must contain string field 'op'")

        if op == "discover":
            return self.manager.discover(
                scope=request.get("scope", "auto"),
                baud=request.get("baud"),
                scan_seconds=request.get("scan_seconds"),
            )
        if op == "open":
            device_key = request.get("device_key")
            if not isinstance(device_key, str) or not device_key:
                raise AgentError("invalid_request", "open requires device_key")
            return self.manager.open(
                device_key,
                eol=request.get("eol", "lf"),
                auto_id=bool(request.get("auto_id", True)),
                wait_connected_ms=int(request.get("wait_connected_ms", 10000)),
            )
        if op == "list_sessions":
            return self.manager.list_sessions()
        if op == "status":
            return self.manager.status(str(request.get("session", "")))
        if op == "send_line":
            session_id = str(request.get("session", ""))
            text = request.get("text")
            if not isinstance(text, str):
                raise AgentError("invalid_request", "send_line requires string text")
            return self.manager.send_line(
                session_id,
                text,
                eol=request.get("eol"),
            )
        if op == "send_bytes":
            session_id = str(request.get("session", ""))
            encoded = request.get("data_b64")
            if not isinstance(encoded, str):
                raise AgentError("invalid_request", "send_bytes requires data_b64")
            try:
                data = base64.b64decode(encoded, validate=True)
            except Exception as exc:
                raise AgentError("invalid_base64", "data_b64 is not valid base64") from exc
            return self.manager.send_bytes(session_id, data)
        if op == "events":
            streams = request.get("streams")
            kinds = request.get("kinds")
            if streams is not None and not isinstance(streams, list):
                raise AgentError("invalid_request", "streams must be a list")
            if kinds is not None and not isinstance(kinds, list):
                raise AgentError("invalid_request", "kinds must be a list")
            return self.manager.events(
                str(request.get("session", "")),
                after_seq=int(request.get("after_seq", 0)),
                timeout_ms=int(request.get("timeout_ms", 0)),
                streams=streams,
                kinds=kinds,
            )
        if op == "close":
            return self.manager.close(str(request.get("session", "")))

        raise AgentError("unknown_operation", f"unknown operation: {op}")

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

        rendered = json.dumps(
            response,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        self.run_log.record("AGENT RESPONSE", rendered)
        return rendered


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
        run_log.record("AGENT", {"event": "ready", "log_path": str(run_log.path)})
        try:
            for line in input_stream:
                if not line.strip():
                    continue
                rendered = protocol.process_line(line)
                output_stream.write(rendered + "\n")
                output_stream.flush()
        finally:
            manager.close_all()
    return 0
