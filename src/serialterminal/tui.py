from __future__ import annotations

from . import tui_core as _core


for _name, _value in vars(_core).items():
    if not _name.startswith("__"):
        globals()[_name] = _value


class TerminalTui(_core.TerminalTui):
    """TUI with controller recovery status and terminal-owned mouse by default."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # Обычный terminal selection/RMB должен работать сразу после запуска.
        # Первый startup-вызов base run() пытается включить curses mouse capture;
        # подавляем только его. F8 после старта остаётся обычным toggle и может
        # включить внутренние wheel/scrollbar события при необходимости.
        self.mouse_capture = False
        self._startup_mouse_mode_pending = True

    def _set_mouse_capture(self, enabled: bool) -> None:
        if self._startup_mouse_mode_pending:
            self._startup_mouse_mode_pending = False
            enabled = False
        super()._set_mouse_capture(enabled)

    def _controller_status_line(self) -> str | None:
        adapter = getattr(self, "_binary_adapter", None)
        reader = getattr(adapter, "controller_status", None)
        if not callable(reader):
            return None
        snapshot = reader()
        state = str(snapshot.get("state", "")).lower()
        if not state or state == "ready":
            return None
        epoch = snapshot.get("epoch", "?")
        generation = snapshot.get("connection_generation", "?")
        return (
            f" Controller {state} | epoch {epoch} | "
            f"transport generation {generation}"
        )

    def _file_status_lines(self, width: int) -> tuple[str, ...]:
        lines = super()._file_status_lines(width)
        controller = self._controller_status_line()
        if controller is None:
            return lines
        return (controller, *lines)


def run_terminal_tui(
    *,
    transport: _core.Transport,
    log_path: str,
    line_ending: str,
    reconnect_delay: float,
    selector,
    profile: _core.TerminalProfile,
    receive_dir: str | None = None,
    log_base64: bool = False,
) -> int:
    tui = TerminalTui(
        transport=transport,
        log_path=log_path,
        line_ending=line_ending,
        reconnect_delay=reconnect_delay,
        selector=selector,
        profile=profile,
        receive_dir=receive_dir,
        log_base64=log_base64,
    )
    _core.curses.wrapper(tui.run)
    return 0


del _name, _value
