from __future__ import annotations

from collections import deque
import curses
import threading

from .file_transfer import FileTransferError, FileTransferManager
from .profiles import PROFILE_NAMES, TerminalProfile, resolve_profile
from .session import SessionLine, SessionTxFenceTimeout, SessionTxOutcomeUnknown
from .terminal import TerminalSession
from .transports.base import Transport, TransportError


class TuiOutputBuffer:
    """Bounded logical-line buffer shared by session threads and the curses UI."""

    def __init__(self, max_lines: int = 4000) -> None:
        self._lines: deque[str] = deque(maxlen=max_lines)
        self._partial = ""
        self._lock = threading.Lock()

    def write(self, text: str) -> None:
        if not text:
            return
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        with self._lock:
            combined = self._partial + normalized
            parts = combined.split("\n")
            self._partial = parts.pop()
            self._lines.extend(parts)

    def snapshot(self) -> list[str]:
        with self._lock:
            lines = list(self._lines)
            if self._partial:
                lines.append(self._partial)
            return lines

    def clear(self) -> None:
        with self._lock:
            self._lines.clear()
            self._partial = ""


_FILE_STATE_LABELS = {
    "waiting_result": "waiting for remote verification",
    "repair_requested": "repair requested",
    "repairing": "repairing",
}


class TerminalTui:
    def __init__(
        self,
        *,
        transport: Transport,
        log_path: str,
        line_ending: str,
        reconnect_delay: float,
        selector,
        profile: TerminalProfile,
        receive_dir: str | None = None,
    ) -> None:
        self.transport = transport
        self.log_path = log_path
        self.line_ending = line_ending
        self.reconnect_delay = reconnect_delay
        self.selector = selector
        self.profile = profile
        self.receive_dir = receive_dir
        self.output = TuiOutputBuffer()
        self.input_text = ""
        self.input_cursor = 0
        self.scroll_offset = 0
        self.status = ""
        self.running = True
        self.panel = profile.make_tui_panel()
        self._was_connected = False
        self._binary_adapter = None
        self._file_transfer: FileTransferManager | None = None
        self.session = self._make_session(transport, profile)
        self._configure_file_transfer(profile)

    def _make_session(
        self,
        transport: Transport,
        profile: TerminalProfile,
    ) -> TerminalSession:
        return TerminalSession(
            transport=transport,
            log_path=self.log_path,
            line_ending=self.line_ending,
            reconnect_delay=self.reconnect_delay,
            device_chooser=self.selector.choose_transport_menu,
            profile=profile,
            screen_writer=self.output.write,
            line_observer=self._observe_line,
        )

    def _configure_file_transfer(self, profile: TerminalProfile) -> None:
        adapter = profile.make_binary_user_transport(
            lambda text: {
                "tx_id": self.session.queue_line(text),
                "state": "queued",
            },
            wait_tx_outcome=self.session.wait_tx_outcome,
            connection_generation=self.session.connection_generation,
        )
        self._binary_adapter = adapter
        self._file_transfer = (
            FileTransferManager(
                adapter,
                receive_dir=self.receive_dir,
                claim_transfer=self._claim_file_transfer,
            )
            if adapter is not None
            else None
        )

    def _claim_file_transfer(
        self,
        transfer_id: int,
        direction: str,
    ) -> None:
        del transfer_id, direction
        fence = self.session.capture_tx_fence()
        try:
            self.session.wait_tx_fence(fence, timeout=10.0)
        except SessionTxFenceTimeout as exc:
            raise FileTransferError(
                "session_fence_timeout",
                "pre-transfer TX fence timed out",
                phase="preparing",
            ) from exc
        except SessionTxOutcomeUnknown as exc:
            raise FileTransferError(
                "session_tx_unknown",
                "pre-transfer TX outcome is ambiguous; reconnect before file transfer",
                phase="preparing",
                details={"tx_id": exc.tx_id},
            ) from exc

    def _observe_line(self, line: SessionLine) -> None:
        if self.panel is not None:
            self.panel.consume_line(line.stream, line.text)
        adapter = self._binary_adapter
        if adapter is not None:
            adapter.feed_line(line.stream, line.text)

    def _file_snapshot(self) -> dict | None:
        manager = self._file_transfer
        return None if manager is None else manager.display_snapshot()

    def _file_transfer_active(self) -> bool:
        snapshot = self._file_snapshot()
        return (
            snapshot is not None
            and snapshot.get("state") not in {"completed", "failed", "cancelled"}
        )

    @staticmethod
    def file_state_label(state: str) -> str:
        return _FILE_STATE_LABELS.get(state, state)

    @staticmethod
    def render_progress_bar(percentage: float, width: int = 24) -> str:
        width = max(4, width)
        bounded = max(0.0, min(100.0, float(percentage)))
        filled = min(width, int(round(width * bounded / 100.0)))
        return "█" * filled + "░" * (width - filled)

    def _file_status_lines(self, width: int) -> tuple[str, ...]:
        snapshot = self._file_snapshot()
        if snapshot is None:
            return ()
        bar_width = max(10, min(30, width // 4))
        bar = self.render_progress_bar(
            float(snapshot.get("percentage", 0.0)),
            bar_width,
        )
        raw_state = str(snapshot.get("state", "?"))
        first = (
            f" File {snapshot.get('direction', '?')} "
            f"{snapshot.get('filename', '?')} [{bar}] "
            f"{float(snapshot.get('percentage', 0.0)):.1f}% "
            f"{self.file_state_label(raw_state)}"
        )
        second = (
            f"      {snapshot.get('chunks_completed', 0)}/"
            f"{snapshot.get('chunks_total', 0)} chunks  "
            f"{snapshot.get('bytes_completed', 0)}/"
            f"{snapshot.get('wire_bytes', 0)} wire bytes"
        )
        failure = snapshot.get("failure")
        if isinstance(failure, dict):
            second += (
                f"  ERROR {failure.get('code', '?')}: "
                f"{failure.get('message', '')}"
            )
        elif snapshot.get("final_path"):
            second += f"  -> {snapshot['final_path']}"
        return (first, second)

    @staticmethod
    def _safe_addstr(stdscr, y: int, x: int, text: str, attr: int = 0) -> None:
        height, width = stdscr.getmaxyx()
        if not (0 <= y < height and 0 <= x < width):
            return
        available = width - x
        if available <= 0:
            return
        try:
            stdscr.addnstr(y, x, text, max(1, available - 1), attr)
        except curses.error:
            pass

    @staticmethod
    def _fit(text: str, width: int) -> str:
        if width <= 0:
            return ""
        if len(text) <= width:
            return text
        if width == 1:
            return "…"
        return text[: width - 1] + "…"

    def _colors(self) -> dict[str, int]:
        return {
            "normal": curses.color_pair(1),
            "header": curses.color_pair(2) | curses.A_BOLD,
            "panel": curses.color_pair(3),
            "status": curses.color_pair(4),
            "error": curses.color_pair(5) | curses.A_BOLD,
            "input": curses.color_pair(6),
            "dim": curses.color_pair(1) | curses.A_DIM,
        }

    def _line_attr(self, line: str, colors: dict[str, int]) -> int:
        upper = line.upper()
        if "ERROR" in upper or "FAILED" in upper:
            return colors["error"]
        if line.startswith("[SYS]") or line.startswith("[serialterminal]"):
            return colors["status"]
        if line.startswith("<") or "RX USER" in line:
            return colors["panel"]
        return colors["normal"]

    def _render(self, stdscr) -> None:
        stdscr.erase()
        height, width = stdscr.getmaxyx()
        colors = self._colors()

        if height < 12 or width < 60:
            self._safe_addstr(
                stdscr, 0, 0,
                "Terminal is too small; resize to at least 60x12.",
            )
            stdscr.refresh()
            return

        transport = self.session._current_transport()
        connection = "CONNECTED" if self.session.connected_event.is_set() else "WAITING"
        header = (
            f" SerialTerminal | {transport.description} | "
            f"profile:{self.profile.name} | {connection} "
        )
        self._safe_addstr(
            stdscr, 0, 0, self._fit(header.ljust(width), width), colors["header"]
        )

        y = 1
        if self.panel is not None:
            for line in self.panel.status_lines():
                self._safe_addstr(
                    stdscr, y, 0,
                    self._fit((" " + line).ljust(width), width),
                    colors["panel"],
                )
                y += 1
        for line in self._file_status_lines(width):
            self._safe_addstr(
                stdscr,
                y,
                0,
                self._fit(line.ljust(width), width),
                colors["status"],
            )
            y += 1

        separator = "─" * max(1, width - 1)
        self._safe_addstr(stdscr, y, 0, separator, colors["dim"])
        y += 1

        footer_rows = 4
        body_rows = max(1, height - y - footer_rows)
        lines = self.output.snapshot()
        end = max(0, len(lines) - self.scroll_offset)
        start = max(0, end - body_rows)
        for row, line in enumerate(lines[start:end]):
            self._safe_addstr(
                stdscr, y + row, 0, self._fit(line, width - 1),
                self._line_attr(line, colors),
            )

        input_sep_y = height - footer_rows
        self._safe_addstr(stdscr, input_sep_y, 0, separator, colors["dim"])
        prompt = "> "
        input_width = max(1, width - len(prompt) - 1)
        input_start = (
            0 if self.input_cursor < input_width
            else self.input_cursor - input_width + 1
        )
        visible_input = self.input_text[input_start : input_start + input_width]
        self._safe_addstr(
            stdscr, input_sep_y + 1, 0, prompt + visible_input, colors["input"]
        )

        default_status = (
            "PgUp/PgDn scroll | Enter send | F2 Device | F3 Profile | "
            "F4 Clear | F9 Help | Ctrl+Q Quit"
        )
        if self._file_transfer is not None:
            default_status = (
                "Enter send | F2 Device | F3 Profile | F4 Clear | "
                "F5 Send file | F6 Cancel file | F9 Help | Ctrl+Q Quit"
            )
        status = self.status or default_status
        self._safe_addstr(
            stdscr, input_sep_y + 2, 0, self._fit(status, width - 1),
            colors["status"],
        )
        self._safe_addstr(
            stdscr, input_sep_y + 3, 0,
            self._fit(
                f"Log: {self.session.log_path}   Console: "
                f"{self.session.console_path}",
                width - 1,
            ),
            colors["dim"],
        )
        cursor_x = len(prompt) + self.input_cursor - input_start
        try:
            stdscr.move(input_sep_y + 1, min(width - 2, max(0, cursor_x)))
        except curses.error:
            pass
        stdscr.refresh()

    def _run_connected_actions(self) -> None:
        connected = self.session.connected_event.is_set()
        if connected and not self._was_connected and self.panel is not None:
            for action in self.panel.connected_actions():
                if not self.session._queue_profile_action(action):
                    self.status = "Profile status refresh could not be queued"
                    break
        self._was_connected = connected

    def _submit_input(self) -> None:
        if self._file_transfer_active():
            self.status = "Manual USER input is locked during active file transfer"
            return
        line = self.input_text
        self.input_text = ""
        self.input_cursor = 0
        self.scroll_offset = 0
        self.status = ""
        self.session._submit_interactive_line(line)

    def _choose_device(self, stdscr) -> None:
        if self._file_transfer_active():
            self.status = "Cancel or finish file transfer before changing device"
            return
        curses.endwin()
        try:
            self.session._change_device()
        finally:
            stdscr.refresh()
        self.status = "Device chooser closed"

    def _switch_profile(self) -> None:
        if self._file_transfer_active():
            self.status = "Cancel or finish file transfer before changing profile"
            return
        current = PROFILE_NAMES.index(self.profile.name)
        next_name = PROFILE_NAMES[(current + 1) % len(PROFILE_NAMES)]
        next_profile = resolve_profile(next_name)
        old_transport = self.session._current_transport()

        try:
            new_transport = self.selector.recreate_transport(
                old_transport, next_profile
            )
        except (TransportError, ValueError) as exc:
            self.status = f"Profile switch failed: {exc}"
            return

        fence = self.session.capture_tx_fence()
        try:
            self.session.wait_tx_fence(fence, timeout=2.0)
        except (SessionTxFenceTimeout, SessionTxOutcomeUnknown) as exc:
            new_transport.close()
            self.status = f"Profile switch blocked by unsettled TX: {exc}"
            return

        self.session._reveal_sent_presentations()
        if self._file_transfer is not None:
            self._file_transfer.close()
        self.session.stop()
        self.session.close_logs()
        self.selector.profile = next_profile
        self.profile = next_profile
        self.panel = next_profile.make_tui_panel()
        self.transport = new_transport
        self.session = self._make_session(new_transport, next_profile)
        self._configure_file_transfer(next_profile)
        self._was_connected = False
        self.session.start()
        self.status = f"Profile switched to {next_name}; reconnecting same target"

    def _choose_file(self, stdscr) -> None:
        manager = self._file_transfer
        if manager is None:
            self.status = "Selected profile does not support file transfer"
            return
        if self._file_transfer_active():
            self.status = "A file transfer is already active"
            return

        curses.endwin()
        try:
            local_path = input("File to send (Enter cancels): ").strip()
        finally:
            stdscr.refresh()
        if not local_path:
            self.status = "File selection cancelled"
            return
        try:
            result = manager.start_send(local_path)
        except FileTransferError as exc:
            self.status = f"File send failed to start: {exc.code}: {exc.message}"
            return
        self.status = (
            f"File transfer {result['transfer_id']} started: "
            f"{result['filename']}"
        )

    def _cancel_file(self) -> None:
        manager = self._file_transfer
        snapshot = self._file_snapshot()
        if manager is None or snapshot is None:
            self.status = "No file transfer to cancel"
            return
        if snapshot.get("state") in {"completed", "failed", "cancelled"}:
            self.status = "File transfer is already terminal"
            return
        try:
            result = manager.cancel(str(snapshot["transfer_id"]))
        except FileTransferError as exc:
            self.status = f"Cancel failed: {exc.code}: {exc.message}"
            return
        self.status = f"Cancellation requested for {result['transfer_id']}"

    def _handle_key(self, stdscr, key, body_rows: int) -> None:
        if key in ("\x11", "\x03"):
            self.running = False
        elif key in ("\n", "\r") or key == curses.KEY_ENTER:
            self._submit_input()
        elif key == curses.KEY_F2:
            self._choose_device(stdscr)
        elif key == curses.KEY_F3:
            self._switch_profile()
        elif key == curses.KEY_F4:
            self.output.clear()
            self.scroll_offset = 0
            self.status = "Screen cleared; log files were not changed"
        elif key == curses.KEY_F5:
            self._choose_file(stdscr)
        elif key == curses.KEY_F6:
            self._cancel_file()
        elif key == curses.KEY_F9:
            self.session._show_full_help()
            self.scroll_offset = 0
            self.status = "Help added to terminal output"
        elif key == curses.KEY_PPAGE:
            maximum = max(0, len(self.output.snapshot()) - 1)
            self.scroll_offset = min(
                maximum, self.scroll_offset + max(1, body_rows)
            )
        elif key == curses.KEY_NPAGE:
            self.scroll_offset = max(
                0, self.scroll_offset - max(1, body_rows)
            )
        elif key == curses.KEY_END:
            self.scroll_offset = 0
        elif key == curses.KEY_LEFT:
            self.input_cursor = max(0, self.input_cursor - 1)
        elif key == curses.KEY_RIGHT:
            self.input_cursor = min(len(self.input_text), self.input_cursor + 1)
        elif key == curses.KEY_HOME:
            self.input_cursor = 0
        elif key == curses.KEY_DC:
            if self.input_cursor < len(self.input_text):
                self.input_text = (
                    self.input_text[: self.input_cursor]
                    + self.input_text[self.input_cursor + 1 :]
                )
        elif key in (curses.KEY_BACKSPACE, "\x7f", "\b"):
            if self.input_cursor > 0:
                self.input_text = (
                    self.input_text[: self.input_cursor - 1]
                    + self.input_text[self.input_cursor :]
                )
                self.input_cursor -= 1
        elif isinstance(key, str) and key.isprintable():
            self.input_text = (
                self.input_text[: self.input_cursor]
                + key
                + self.input_text[self.input_cursor :]
            )
            self.input_cursor += len(key)

    def run(self, stdscr) -> None:
        curses.curs_set(1)
        stdscr.keypad(True)
        stdscr.timeout(100)
        if curses.has_colors():
            curses.start_color()
            try:
                curses.use_default_colors()
            except curses.error:
                pass
            curses.init_pair(1, curses.COLOR_WHITE, -1)
            curses.init_pair(2, curses.COLOR_WHITE, curses.COLOR_BLUE)
            curses.init_pair(3, curses.COLOR_CYAN, -1)
            curses.init_pair(4, curses.COLOR_YELLOW, -1)
            curses.init_pair(5, curses.COLOR_RED, -1)
            curses.init_pair(6, curses.COLOR_GREEN, -1)

        self.session.start()
        self.output.write(
            "SerialTerminal TUI started. F3 switches generic/chatter profile.\n"
        )
        try:
            while self.running and not self.session.stop_event.is_set():
                self._run_connected_actions()
                height, width = stdscr.getmaxyx()
                panel_rows = len(self.panel.status_lines()) if self.panel else 0
                file_rows = len(self._file_status_lines(width))
                body_rows = max(1, height - panel_rows - file_rows - 8)
                self._render(stdscr)
                try:
                    key = stdscr.get_wch()
                except curses.error:
                    continue
                self._handle_key(stdscr, key, body_rows)
        finally:
            self.session._reveal_sent_presentations()
            if self._file_transfer is not None:
                self._file_transfer.close()
            self.session.stop()
            self.session.close_logs()


def run_terminal_tui(
    *,
    transport: Transport,
    log_path: str,
    line_ending: str,
    reconnect_delay: float,
    selector,
    profile: TerminalProfile,
    receive_dir: str | None = None,
) -> int:
    tui = TerminalTui(
        transport=transport,
        log_path=log_path,
        line_ending=line_ending,
        reconnect_delay=reconnect_delay,
        selector=selector,
        profile=profile,
        receive_dir=receive_dir,
    )
    curses.wrapper(tui.run)
    return 0
