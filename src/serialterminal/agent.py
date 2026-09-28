from __future__ import annotations

import base64
from dataclasses import asdict
import json
from pathlib import Path
import sys
import threading
import time
from typing import Any, Callable, TextIO

from .file_transfer import FileTransferError, FileTransferManager, transfer_id_text
from .file_transfer.core import FILE_MAX_WINDOW
from .profiles import SendBytes, SendLine, resolve_profile
from .runlog import RunLog
from .session import (
    ManagedSession,
    SessionClosedError,
    SessionCursorExpired,
    SessionTxFenceTimeout,
    SessionTxOutcomeUnknown,
    SessionEvent,
    SessionLine,
    encode_line,
)
from .sweep import (
    SWEEP_MAX_WINDOW,
    SweepError,
    SweepJobManager,
    normalize_sweep_plan,
)


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


def _profile_preamble_bytes(actions, line_ending: str) -> bytes:
    payload = bytearray()
    for action in actions:
        if isinstance(action, SendLine):
            payload.extend(encode_line(action.text, line_ending))
        elif isinstance(action, SendBytes):
            payload.extend(action.data)
        else:
            raise TypeError(f"unsupported profile action: {type(action)!r}")
    return bytes(payload)


class _SessionSweepContext:
    """Capability-limited adapter view over sessions owned by one sweep."""

    def __init__(
        self,
        manager: "SessionManager",
        sessions: tuple[str, ...],
    ):
        self.manager = manager
        self.sessions = frozenset(sessions)

    def _require_session(self, session_id: str) -> None:
        if session_id not in self.sessions:
            raise SweepError(
                "invalid_sweep_session",
                f"adapter tried to access undeclared session: {session_id}",
                {"session": session_id},
            )

    def status(self, session_id: str) -> dict[str, Any]:
        self._require_session(session_id)
        return self.manager.status(session_id)

    def profile_name(self, session_id: str) -> str:
        self._require_session(session_id)
        return self.manager.session_profile(session_id)

    def send_line(self, session_id: str, text: str) -> dict[str, Any]:
        self._require_session(session_id)
        return self.manager._sweep_send_line(session_id, text)

    def send_bytes(self, session_id: str, data: bytes) -> dict[str, Any]:
        self._require_session(session_id)
        return self.manager._sweep_send_bytes(session_id, data)

    def observe(
        self,
        cursors: dict[str, int],
        *,
        timeout_ms: int,
        include_events: bool = False,
    ) -> dict[str, Any]:
        for session_id in cursors:
            self._require_session(session_id)
        return self.manager.observe(
            cursors,
            timeout_ms=timeout_ms,
            include_events=include_events,
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
        receive_dir: str | Path | None = None,
    ):
        self.run_log = run_log
        self.selector_factory = selector_factory or _default_selector_factory
        self.default_baud = default_baud
        self.default_scan_seconds = default_scan_seconds
        self.reconnect_delay = reconnect_delay
        self.receive_dir = receive_dir

        self._lock = threading.Lock()
        self._selector_profile_lock = threading.Lock()
        self._observe_condition = threading.Condition()
        self._observe_cancelled = threading.Event()
        self._candidates: dict[str, tuple[Any, Any]] = {}
        self._sessions: dict[str, ManagedSession] = {}
        self._session_device_keys: dict[str, str] = {}
        self._session_profiles: dict[str, str] = {}
        self._device_sessions: dict[str, str] = {}
        self._event_loggers: dict[str, tuple[threading.Event, threading.Thread]] = {}
        self._session_mutations: dict[str, int] = {}
        self._session_sweep_owners: dict[str, str] = {}
        self._session_file_owners: dict[str, str] = {}
        self._file_managers: dict[str, FileTransferManager] = {}
        self._next_session_id = 1
        self._sweep_manager = SweepJobManager(
            acquire_sessions=self._acquire_sweep_sessions,
            release_sessions=self._release_sweep_sessions,
            run_log=run_log,
        )

    def _get_session(self, session_id: str) -> ManagedSession:
        with self._lock:
            session = self._sessions.get(session_id)
        if session is None:
            raise AgentError("unknown_session", f"unknown session: {session_id}")
        return session

    def session_profile(self, session_id: str) -> str:
        with self._lock:
            if session_id not in self._sessions:
                raise AgentError("unknown_session", f"unknown session: {session_id}")
            return self._session_profiles.get(session_id, "generic")

    def _begin_external_mutation(self, session_id: str) -> ManagedSession:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise AgentError("unknown_session", f"unknown session: {session_id}")
            owner = self._session_sweep_owners.get(session_id)
            if owner is not None:
                raise AgentError(
                    "session_busy",
                    f"session is owned by sweep {owner}: {session_id}",
                    {
                        "session": session_id,
                        "owner": {"kind": "sweep", "sweep_id": owner},
                    },
                )
            file_owner = self._session_file_owners.get(session_id)
            if file_owner is not None:
                raise AgentError(
                    "session_busy",
                    f"session is owned by file transfer {file_owner}: {session_id}",
                    {
                        "session": session_id,
                        "owner": {
                            "kind": "file_transfer",
                            "transfer_id": file_owner,
                        },
                    },
                )
            self._session_mutations[session_id] = (
                self._session_mutations.get(session_id, 0) + 1
            )
            return session

    def _finish_external_mutation(self, session_id: str) -> None:
        with self._lock:
            count = self._session_mutations.get(session_id, 0)
            if count <= 1:
                self._session_mutations.pop(session_id, None)
            else:
                self._session_mutations[session_id] = count - 1

    def _claim_file_transfer(
        self,
        session_id: str,
        transfer_id: int,
        direction: str,
    ) -> None:
        transfer_text = transfer_id_text(transfer_id)
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise FileTransferError(
                    "unknown_session",
                    f"unknown session: {session_id}",
                )
            sweep_owner = self._session_sweep_owners.get(session_id)
            if sweep_owner is not None:
                raise FileTransferError(
                    "session_busy",
                    f"session is owned by sweep {sweep_owner}",
                )
            file_owner = self._session_file_owners.get(session_id)
            if file_owner is not None:
                raise FileTransferError(
                    "session_busy",
                    f"session is owned by file transfer {file_owner}",
                )
            if self._session_mutations.get(session_id, 0) != 0:
                raise FileTransferError(
                    "session_busy",
                    "session has a concurrent external mutation",
                )
            fence_tx_id = session.capture_tx_fence()
            self._session_file_owners[session_id] = transfer_text

        try:
            session.wait_tx_fence(fence_tx_id, 10.0)
        except SessionTxFenceTimeout as exc:
            self._release_file_transfer(session_id, transfer_id, direction)
            raise FileTransferError(
                "session_fence_timeout",
                "pre-transfer TX fence timed out",
                phase="preparing",
            ) from exc
        except SessionTxOutcomeUnknown as exc:
            self._release_file_transfer(session_id, transfer_id, direction)
            raise FileTransferError(
                "session_tx_unknown",
                "pre-transfer TX outcome is ambiguous; reopen session first",
                phase="preparing",
                details={"tx_id": exc.tx_id},
            ) from exc

    def _release_file_transfer(
        self,
        session_id: str,
        transfer_id: int,
        direction: str,
    ) -> None:
        del direction
        transfer_text = transfer_id_text(transfer_id)
        with self._lock:
            if self._session_file_owners.get(session_id) == transfer_text:
                self._session_file_owners.pop(session_id, None)

    def _acquire_sweep_sessions(
        self,
        sweep_id: str,
        sessions: tuple[str, ...],
    ):
        with self._lock:
            owned: list[tuple[str, ManagedSession, int]] = []
            for session_id in sessions:
                session = self._sessions.get(session_id)
                if session is None:
                    raise SweepError(
                        "unknown_session",
                        f"unknown session: {session_id}",
                        {"session": session_id},
                    )
                owner = self._session_sweep_owners.get(session_id)
                if owner is not None:
                    raise SweepError(
                        "session_busy",
                        f"session is owned by sweep {owner}: {session_id}",
                        {
                            "session": session_id,
                            "owner": {"kind": "sweep", "sweep_id": owner},
                        },
                    )
                file_owner = self._session_file_owners.get(session_id)
                if file_owner is not None:
                    raise SweepError(
                        "session_busy",
                        f"session is owned by file transfer {file_owner}: {session_id}",
                        {
                            "session": session_id,
                            "owner": {
                                "kind": "file_transfer",
                                "transfer_id": file_owner,
                            },
                        },
                    )
                if self._session_mutations.get(session_id, 0) != 0:
                    raise SweepError(
                        "session_busy",
                        f"session has a concurrent mutation: {session_id}",
                        {
                            "session": session_id,
                            "owner": {"kind": "external_mutation"},
                        },
                    )
                owned.append(
                    (session_id, session, session.capture_tx_fence())
                )
            for session_id in sessions:
                self._session_sweep_owners[session_id] = sweep_id

        def preflight(phase) -> None:
            for session_id, session, fence_tx_id in owned:
                phase.raise_if_cancelled()
                try:
                    session.wait_tx_fence(
                        fence_tx_id,
                        phase.remaining_s(),
                    )
                except SessionTxFenceTimeout as exc:
                    raise SweepError(
                        "session_fence_timeout",
                        f"pre-sweep TX fence timed out: {session_id}",
                        {
                            "session": session_id,
                            "fence_tx_id": fence_tx_id,
                        },
                    ) from exc
                except SessionTxOutcomeUnknown as exc:
                    raise SweepError(
                        "session_tx_unknown",
                        (
                            "pre-sweep TX outcome is ambiguous; "
                            f"reopen session before sweep: {session_id}"
                        ),
                        {
                            "session": session_id,
                            "tx_id": exc.tx_id,
                        },
                    ) from exc

        return preflight

    def _release_sweep_sessions(
        self,
        sweep_id: str,
        sessions: tuple[str, ...],
    ) -> None:
        with self._lock:
            for session_id in sessions:
                if self._session_sweep_owners.get(session_id) == sweep_id:
                    self._session_sweep_owners.pop(session_id, None)

    def _sweep_owned_session(self, session_id: str) -> ManagedSession:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise SweepError(
                    "unknown_session",
                    f"unknown session: {session_id}",
                    {"session": session_id},
                )
            owner = self._session_sweep_owners.get(session_id)
            if owner is None:
                raise SweepError(
                    "sweep_session_not_owned",
                    f"session is no longer owned by an active sweep: {session_id}",
                    {"session": session_id},
                )
            return session

    def _sweep_send_line(
        self,
        session_id: str,
        text: str,
    ) -> dict[str, Any]:
        session = self._sweep_owned_session(session_id)
        try:
            tx_id = session.queue_line(text)
        except SessionClosedError as exc:
            raise SweepError("session_closed", str(exc)) from exc
        if self.run_log is not None:
            self.run_log.record_console(session_id, ">", text)
        return {"tx_id": tx_id, "state": "queued"}

    def _sweep_send_bytes(
        self,
        session_id: str,
        data: bytes,
    ) -> dict[str, Any]:
        session = self._sweep_owned_session(session_id)
        try:
            tx_id = session.queue_bytes(data)
        except SessionClosedError as exc:
            raise SweepError("session_closed", str(exc)) from exc
        return {"tx_id": tx_id, "state": "queued", "size": len(data)}

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

    def _log_console_line(
        self,
        session_id: str,
        line: SessionLine,
        console_streams: frozenset[str],
    ) -> None:
        if self.run_log is None or line.stream not in console_streams:
            return
        # В companion log попадают только console streams выбранного profile.
        # Отдельные background streams остаются в forensic log.
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
        profile: str = "generic",
        wait_connected_ms: int = 10000,
    ) -> dict[str, Any]:
        if eol not in _EOL:
            raise AgentError("invalid_eol", f"unsupported eol: {eol}")
        if wait_connected_ms < 0:
            raise AgentError("invalid_timeout", "wait_connected_ms must be non-negative")
        try:
            terminal_profile = resolve_profile(profile)
        except ValueError as exc:
            raise AgentError("unknown_profile", str(exc)) from exc

        profile_actions = terminal_profile.connect_preamble()
        console_streams = frozenset(terminal_profile.human_console_streams())

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
            # Discovery selector хранит transport parameters. Profile задаётся
            # именно на open, чтобы один agent process мог держать разные
            # controller profiles без process-global режима.
            with self._selector_profile_lock:
                selector.profile = terminal_profile
                transport = selector.make_transport(candidate)
        except Exception as exc:
            raise AgentError("open_failed", str(exc)) from exc

        line_ending = _EOL[eol]
        preamble_payload = _profile_preamble_bytes(profile_actions, line_ending)
        preamble = (
            (lambda _transport, payload=preamble_payload: payload)
            if preamble_payload
            else None
        )
        session_id = self._next_session()
        application_holder: dict[str, Any] = {}

        def line_notifier(line: SessionLine) -> None:
            self._log_console_line(
                session_id,
                line,
                console_streams,
            )
            binary_adapter = application_holder.get("binary")
            if binary_adapter is not None:
                binary_adapter.feed_line(line.stream, line.text)

        session = ManagedSession(
            transport,
            line_ending=line_ending,
            reconnect_delay=self.reconnect_delay,
            connect_preamble=preamble,
            event_notifier=self._notify_event_activity,
            line_notifier=line_notifier,
        )
        binary_adapter = terminal_profile.make_binary_user_transport(
            lambda text: {
                "tx_id": session.queue_line(text),
                "state": "queued",
            },
            wait_tx_outcome=session.wait_tx_outcome,
            connection_generation=session.connection_generation,
        )
        file_manager = (
            FileTransferManager(
                binary_adapter,
                receive_dir=self.receive_dir,
                claim_transfer=lambda transfer_id, direction: self._claim_file_transfer(
                    session_id,
                    transfer_id,
                    direction,
                ),
                release_transfer=lambda transfer_id, direction:
                    self._release_file_transfer(
                        session_id,
                        transfer_id,
                        direction,
                    ),
            )
            if binary_adapter is not None
            else None
        )
        if binary_adapter is not None:
            application_holder["binary"] = binary_adapter

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
            self._session_profiles[session_id] = terminal_profile.name
            self._device_sessions[device_key] = session_id
            if file_manager is not None:
                self._file_managers[session_id] = file_manager

        self._start_event_logger(session_id, session)
        try:
            session.start()
        except Exception:
            self._stop_event_logger(session_id)
            if file_manager is not None:
                file_manager.close()
            with self._lock:
                self._sessions.pop(session_id, None)
                self._session_device_keys.pop(session_id, None)
                self._session_profiles.pop(session_id, None)
                self._file_managers.pop(session_id, None)
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
            "profile": terminal_profile.name,
        }

    def status(self, session_id: str) -> dict[str, Any]:
        session = self._get_session(session_id)
        transport = session._current_transport()
        with self._lock:
            profile = self._session_profiles.get(session_id, "generic")
            file_manager = self._file_managers.get(session_id)
        return {
            "session": session_id,
            "device_key": transport.device_key,
            "description": transport.description,
            "profile": profile,
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
            "file_transfer_supported": file_manager is not None,
            "file_transfer": (
                file_manager.display_snapshot()
                if file_manager is not None
                else None
            ),
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
        session = self._begin_external_mutation(session_id)
        try:
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
        finally:
            self._finish_external_mutation(session_id)

    def send_bytes(self, session_id: str, data: bytes) -> dict[str, Any]:
        session = self._begin_external_mutation(session_id)
        try:
            try:
                tx_id = session.queue_bytes(data)
            except SessionClosedError as exc:
                raise AgentError("session_closed", str(exc)) from exc
            return {"tx_id": tx_id, "state": "queued", "size": len(data)}
        finally:
            self._finish_external_mutation(session_id)

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
        include_events: bool,
    ) -> dict[str, Any]:
        lines.sort(key=lambda item: (item[0], item[1], item[2]))
        result: dict[str, Any] = {
            "lines": [
                {"session": session_id, **_line_dict(line)}
                for _, session_id, _, line in lines
            ],
            "cursors": dict(cursors),
            "timed_out": timed_out,
        }
        if include_events:
            # Raw event payload дорог для model context и нужен только для
            # transport forensics; forensic RunLog при этом пишется независимо.
            events.sort(key=lambda item: (item[0], item[1], item[2]))
            result["events"] = [
                {"session": session_id, **_event_dict(event)}
                for _, session_id, _, event in events
            ]
        return result

    def observe(
        self,
        cursors: dict[str, int],
        *,
        timeout_ms: int = 0,
        include_events: bool = False,
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
                        include_events=include_events,
                    )
                if timeout_ms == 0:
                    return self._observation_result(
                        [],
                        [],
                        current_cursors,
                        timed_out=False,
                        include_events=include_events,
                    )

                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return self._observation_result(
                        [],
                        [],
                        current_cursors,
                        timed_out=True,
                        include_events=include_events,
                    )
                self._observe_condition.wait(timeout=remaining)

    def _force_close_session(
        self,
        session_id: str,
        session: ManagedSession,
    ) -> dict[str, Any]:
        with self._lock:
            device_key = self._session_device_keys.get(session_id)

        with self._lock:
            file_manager = self._file_managers.get(session_id)
        if file_manager is not None:
            file_manager.close()

        session.stop()
        self._stop_event_logger(session_id)

        with self._lock:
            self._sessions.pop(session_id, None)
            self._session_device_keys.pop(session_id, None)
            self._session_profiles.pop(session_id, None)
            self._session_mutations.pop(session_id, None)
            self._session_sweep_owners.pop(session_id, None)
            self._session_file_owners.pop(session_id, None)
            self._file_managers.pop(session_id, None)
            if device_key is not None:
                self._device_sessions.pop(device_key, None)
        return {"session": session_id, "state": "closed"}

    def close(self, session_id: str) -> dict[str, Any]:
        session = self._begin_external_mutation(session_id)
        try:
            return self._force_close_session(session_id, session)
        finally:
            self._finish_external_mutation(session_id)

    @staticmethod
    def _file_error(exc: FileTransferError) -> AgentError:
        return AgentError(exc.code, exc.message, exc.details)

    def _file_manager(self, session_id: str) -> FileTransferManager:
        self._get_session(session_id)
        with self._lock:
            manager = self._file_managers.get(session_id)
        if manager is None:
            raise AgentError(
                "file_transfer_unsupported",
                f"session profile does not support file transfer: {session_id}",
                {"session": session_id},
            )
        return manager

    def file_send_start(
        self,
        session_id: str,
        local_path: str,
    ) -> dict[str, Any]:
        manager = self._file_manager(session_id)
        try:
            return manager.start_send(local_path)
        except FileTransferError as exc:
            raise self._file_error(exc) from exc

    def file_transfer_observe(
        self,
        session_id: str,
        transfer_id: str,
        *,
        cursor: int,
        window: int,
        timeout_ms: int,
    ) -> dict[str, Any]:
        manager = self._file_manager(session_id)
        try:
            return manager.observe(
                transfer_id,
                cursor=cursor,
                window=window,
                timeout_ms=timeout_ms,
            )
        except FileTransferError as exc:
            raise self._file_error(exc) from exc

    def file_transfer_cancel(
        self,
        session_id: str,
        transfer_id: str,
    ) -> dict[str, Any]:
        manager = self._file_manager(session_id)
        try:
            return manager.cancel(transfer_id)
        except FileTransferError as exc:
            raise self._file_error(exc) from exc

    def file_transfer_close(
        self,
        session_id: str,
        transfer_id: str,
    ) -> dict[str, Any]:
        manager = self._file_manager(session_id)
        try:
            return manager.close_transfer(transfer_id)
        except (FileTransferError, ValueError) as exc:
            if isinstance(exc, FileTransferError):
                raise self._file_error(exc) from exc
            raise AgentError("invalid_transfer_id", str(exc)) from exc

    def cancel_file_transfers(self) -> None:
        with self._lock:
            managers = list(self._file_managers.values())
        for manager in managers:
            manager.cancel_active()

    def join_file_transfers(self, timeout: float) -> None:
        deadline = time.monotonic() + max(0.0, timeout)
        with self._lock:
            managers = list(self._file_managers.values())
        for manager in managers:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            manager.join_all(remaining)

    @staticmethod
    def _sweep_error(exc: SweepError) -> AgentError:
        return AgentError(exc.code, exc.message, exc.details)

    def _sweep_adapter_factory(
        self,
        adapter_name: str,
        sessions: tuple[str, ...],
    ):
        factories = []
        seen: set[int] = set()
        for session_id in sessions:
            profile_name = self.session_profile(session_id)
            try:
                profile = resolve_profile(profile_name)
            except ValueError as exc:
                raise AgentError("unknown_profile", str(exc)) from exc
            factory = profile.sweep_adapters().get(adapter_name)
            if factory is not None and id(factory) not in seen:
                seen.add(id(factory))
                factories.append(factory)
        if not factories:
            raise AgentError(
                "unknown_sweep_adapter",
                f"no participating profile provides sweep adapter: {adapter_name}",
                {"adapter": adapter_name},
            )
        if len(factories) != 1:
            raise AgentError(
                "ambiguous_sweep_adapter",
                f"multiple adapter factories provide: {adapter_name}",
                {"adapter": adapter_name},
            )
        return factories[0]

    def sweep_start(
        self,
        adapter_name: Any,
        raw_sessions: Any,
        raw_plan: Any,
    ) -> dict[str, Any]:
        if not isinstance(adapter_name, str) or not adapter_name:
            raise AgentError(
                "invalid_request",
                "sweep_start requires non-empty string field 'adapter'",
            )
        if not isinstance(raw_sessions, list) or not raw_sessions:
            raise AgentError(
                "invalid_request",
                "sweep_start requires non-empty array field 'sessions'",
            )
        if len(raw_sessions) > 32:
            raise AgentError(
                "invalid_request",
                "sweep_start sessions exceeds maximum of 32",
            )
        if any(
            not isinstance(session_id, str) or not session_id
            for session_id in raw_sessions
        ):
            raise AgentError(
                "invalid_request",
                "sweep_start sessions must be non-empty strings",
            )
        if len(set(raw_sessions)) != len(raw_sessions):
            raise AgentError(
                "invalid_request",
                "sweep_start sessions must be distinct",
            )
        sessions = tuple(raw_sessions)
        try:
            plan = normalize_sweep_plan(raw_plan)
            factory = self._sweep_adapter_factory(adapter_name, sessions)
            context = _SessionSweepContext(self, sessions)
            adapter = factory(context, sessions, plan)
            return self._sweep_manager.start(
                sessions=sessions,
                plan=plan,
                adapter=adapter,
            )
        except SweepError as exc:
            raise self._sweep_error(exc) from exc

    def sweep_observe(
        self,
        sweep_id: str,
        *,
        cursor: int,
        window: int,
        timeout_ms: int,
    ) -> dict[str, Any]:
        try:
            return self._sweep_manager.observe(
                sweep_id,
                cursor=cursor,
                window=window,
                timeout_ms=timeout_ms,
            )
        except SweepError as exc:
            raise self._sweep_error(exc) from exc

    def sweep_cancel(self, sweep_id: str) -> dict[str, Any]:
        try:
            return self._sweep_manager.cancel(sweep_id)
        except SweepError as exc:
            raise self._sweep_error(exc) from exc

    def sweep_close(self, sweep_id: str) -> dict[str, Any]:
        try:
            return self._sweep_manager.close(sweep_id)
        except SweepError as exc:
            raise self._sweep_error(exc) from exc

    def cancel_sweeps(self) -> None:
        self._sweep_manager.cancel_active()

    def join_sweeps(self, timeout: float) -> None:
        self._sweep_manager.join_all(timeout)

    def close_all(self) -> None:
        with self._lock:
            pairs = list(self._sessions.items())
        for session_id, session in pairs:
            try:
                self._force_close_session(session_id, session)
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
        if "auto_id" in request:
            raise AgentError(
                "invalid_request",
                "open does not accept auto_id; select profile explicitly",
            )
        profile = request.get("profile", "generic")
        if not isinstance(profile, str) or not profile:
            raise AgentError("invalid_request", "open profile must be a non-empty string")
        return self.manager.open(
            device_key,
            eol=request.get("eol", "lf"),
            profile=profile,
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
        include_events = request.get("include_events", False)
        if not isinstance(include_events, bool):
            raise AgentError(
                "invalid_request",
                "observe field 'include_events' must be boolean",
            )
        return self.manager.observe(
            cursors,
            timeout_ms=timeout_ms,
            include_events=include_events,
        )

    def _handle_close(self, request: dict[str, Any]) -> dict[str, Any]:
        return self.manager.close(str(request.get("session", "")))

    @staticmethod
    def _file_transfer_id(request: dict[str, Any]) -> str:
        transfer_id = request.get("transfer_id")
        if not isinstance(transfer_id, str) or not transfer_id:
            raise AgentError(
                "invalid_request",
                "file transfer operation requires non-empty string field 'transfer_id'",
            )
        return transfer_id

    def _handle_file_send_start(
        self,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        session_id = request.get("session")
        local_path = request.get("path")
        if not isinstance(session_id, str) or not session_id:
            raise AgentError(
                "invalid_request",
                "file_send_start requires non-empty string field 'session'",
            )
        if not isinstance(local_path, str) or not local_path:
            raise AgentError(
                "invalid_request",
                "file_send_start requires non-empty string field 'path'",
            )
        return self.manager.file_send_start(session_id, local_path)

    def _handle_file_transfer_observe(
        self,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        if request.get("id") is None:
            raise AgentError(
                "invalid_request",
                "file_transfer_observe requires a non-null request id",
            )
        session_id = request.get("session")
        if not isinstance(session_id, str) or not session_id:
            raise AgentError(
                "invalid_request",
                "file_transfer_observe requires non-empty string field 'session'",
            )
        cursor = request.get("cursor", 0)
        window = request.get("window", FILE_MAX_WINDOW)
        timeout_ms = request.get("timeout_ms", 0)
        return self.manager.file_transfer_observe(
            session_id,
            self._file_transfer_id(request),
            cursor=cursor,
            window=window,
            timeout_ms=timeout_ms,
        )

    def _handle_file_transfer_cancel(
        self,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        session_id = request.get("session")
        if not isinstance(session_id, str) or not session_id:
            raise AgentError(
                "invalid_request",
                "file_transfer_cancel requires non-empty string field 'session'",
            )
        return self.manager.file_transfer_cancel(
            session_id,
            self._file_transfer_id(request),
        )

    def _handle_file_transfer_close(
        self,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        session_id = request.get("session")
        if not isinstance(session_id, str) or not session_id:
            raise AgentError(
                "invalid_request",
                "file_transfer_close requires non-empty string field 'session'",
            )
        return self.manager.file_transfer_close(
            session_id,
            self._file_transfer_id(request),
        )

    @staticmethod
    def _sweep_id(request: dict[str, Any]) -> str:
        sweep_id = request.get("sweep_id")
        if not isinstance(sweep_id, str) or not sweep_id:
            raise AgentError(
                "invalid_request",
                "sweep operation requires non-empty string field 'sweep_id'",
            )
        return sweep_id

    def _handle_sweep_start(self, request: dict[str, Any]) -> dict[str, Any]:
        return self.manager.sweep_start(
            request.get("adapter"),
            request.get("sessions"),
            request.get("plan"),
        )

    def _handle_sweep_observe(self, request: dict[str, Any]) -> dict[str, Any]:
        if request.get("id") is None:
            raise AgentError(
                "invalid_request",
                "sweep_observe requires a non-null request id",
            )
        cursor = request.get("cursor")
        window = request.get("window", SWEEP_MAX_WINDOW)
        timeout_ms = request.get("timeout_ms", 0)
        return self.manager.sweep_observe(
            self._sweep_id(request),
            cursor=cursor,
            window=window,
            timeout_ms=timeout_ms,
        )

    def _handle_sweep_cancel(self, request: dict[str, Any]) -> dict[str, Any]:
        return self.manager.sweep_cancel(self._sweep_id(request))

    def _handle_sweep_close(self, request: dict[str, Any]) -> dict[str, Any]:
        return self.manager.sweep_close(self._sweep_id(request))

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
            "file_send_start": self._handle_file_send_start,
            "file_transfer_observe": self._handle_file_transfer_observe,
            "file_transfer_cancel": self._handle_file_transfer_cancel,
            "file_transfer_close": self._handle_file_transfer_close,
            "sweep_start": self._handle_sweep_start,
            "sweep_observe": self._handle_sweep_observe,
            "sweep_cancel": self._handle_sweep_cancel,
            "sweep_close": self._handle_sweep_close,
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
                    "code":"invalid_json",
                    "message":str(exc),
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
        self._observe_threads: set[threading.Thread] = set()
        self._next_observe_thread_id = 1

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
            current = threading.current_thread()
            with self._pending_lock:
                self._pending_ids.discard(request_key)
                self._observe_threads.discard(current)

    def _request_is_pending(self, request_key: str) -> bool:
        with self._pending_lock:
            return request_key in self._pending_ids

    @staticmethod
    def _is_async_observe(request: Any, request_id: Any) -> bool:
        return (
            isinstance(request, dict)
            and request.get("op")
            in {"observe", "sweep_observe", "file_transfer_observe"}
            and request_id is not None
        )

    def _start_observe(self, request: dict[str, Any], request_key: str) -> None:
        with self._pending_lock:
            self._pending_ids.add(request_key)
            thread_id = self._next_observe_thread_id
            self._next_observe_thread_id += 1
            thread = threading.Thread(
                target=self._finish_observe,
                args=(request, request_key),
                name=f"serialterminal-agent-observe-{thread_id}",
                daemon=True,
            )
            self._observe_threads.add(thread)
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
        # EOF не должен ждать user long-poll или многоминутный PHY deadline.
        # Сначала просим waits/jobs завершиться кооперативно, затем force-close
        # sessions разрывает оставшиеся adapter waits до закрытия RunLog.
        self.manager.cancel_observes()
        self.manager.cancel_file_transfers()
        self.manager.cancel_sweeps()
        self.manager.join_file_transfers(1.0)
        self.manager.join_sweeps(1.0)
        self.manager.close_all()
        self.manager.join_file_transfers(5.0)
        self.manager.join_sweeps(5.0)
        with self._pending_lock:
            observe_threads = list(self._observe_threads)
        for thread in observe_threads:
            thread.join(timeout=1.0)

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
    receive_dir: str | Path | None = None,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
) -> int:
    input_stream = sys.stdin if stdin is None else stdin
    output_stream = sys.stdout if stdout is None else stdout

    with RunLog(log_path) as run_log:
        manager = SessionManager(
            run_log=run_log,
            receive_dir=receive_dir,
        )
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
