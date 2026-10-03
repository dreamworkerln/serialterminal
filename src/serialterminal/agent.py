from __future__ import annotations

from . import agent_core as _core


for _name, _value in vars(_core).items():
    if not _name.startswith("__"):
        globals()[_name] = _value


class SessionManager(_core.SessionManager):
    """Agent session manager with explicit Chatter controller observability."""

    @staticmethod
    def _controller_status(file_manager):
        if file_manager is None:
            return None
        reader = getattr(file_manager.transport, "controller_status", None)
        return reader() if callable(reader) else None

    def open(self, *args, **kwargs):
        result = super().open(*args, **kwargs)
        session_id = result["session"]
        with self._lock:
            file_manager = self._file_managers.get(session_id)
        result["controller"] = self._controller_status(file_manager)
        return result

    def status(self, session_id: str):
        result = super().status(session_id)
        with self._lock:
            file_manager = self._file_managers.get(session_id)
        result["controller"] = self._controller_status(file_manager)
        return result


def run_agent(
    *,
    log_path: str | None = None,
    receive_dir: str | _core.Path | None = None,
    stdin: _core.TextIO | None = None,
    stdout: _core.TextIO | None = None,
    log_base64: bool = False,
) -> int:
    input_stream = _core.sys.stdin if stdin is None else stdin
    output_stream = _core.sys.stdout if stdout is None else stdout

    with _core.RunLog(log_path, log_base64=log_base64) as run_log:
        manager = SessionManager(
            run_log=run_log,
            receive_dir=receive_dir,
        )
        protocol = _core.AgentProtocol(manager, run_log=run_log)
        run_log.record(
            "AGENT",
            {
                "event": "ready",
                "log_path": str(run_log.path),
                "console_log_path": str(run_log.console_path),
                "timing_log_path": str(run_log.timing_path),
            },
        )
        _core._AgentJsonlRunner(
            manager,
            protocol,
            run_log,
            input_stream,
            output_stream,
        ).run()
    return 0


del _name, _value
