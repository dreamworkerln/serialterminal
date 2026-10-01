from __future__ import annotations

from collections import deque
import curses
from dataclasses import dataclass
import json
import threading
import time
from pathlib import Path

from .file_browser import browse_file
from .file_transfer import FileTransferError, FileTransferManager
from .profiles import PROFILE_NAMES, TerminalProfile, resolve_profile
from .session import SessionLine, SessionTxFenceTimeout, SessionTxOutcomeUnknown
from .terminal import TerminalSession
from .transports.base import Transport, TransportError


@dataclass(frozen=True)
class TuiOutputLine:
    line_id: int
    text: str


@dataclass(frozen=True)
class TuiVisualRow:
    line_id: int
    char_start: int
    text: str
    logical_text: str


class TuiOutputBuffer:
    """Bounded logical-line buffer shared by session threads and the curses UI."""

    def __init__(self, max_lines: int = 10000) -> None:
        self._lines: deque[TuiOutputLine] = deque(maxlen=max_lines)
        self._partial = ""
        self._partial_id: int | None = None
        self._next_line_id = 1
        self._lock = threading.Lock()

    def _allocate_line_id(self) -> int:
        line_id = self._next_line_id
        self._next_line_id += 1
        return line_id

    def write(self, text: str) -> None:
        if not text:
            return
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        with self._lock:
            combined = self._partial + normalized
            current_id = self._partial_id
            parts = combined.split("\n")
            tail = parts.pop()

            for part in parts:
                if current_id is None:
                    current_id = self._allocate_line_id()
                self._lines.append(TuiOutputLine(current_id, part))
                current_id = None

            self._partial = tail
            if tail:
                if current_id is None:
                    current_id = self._allocate_line_id()
                self._partial_id = current_id
            else:
                self._partial_id = None

    def entries(self) -> list[TuiOutputLine]:
        with self._lock:
            lines = list(self._lines)
            if self._partial_id is not None:
                lines.append(TuiOutputLine(self._partial_id, self._partial))
            return lines

    def snapshot(self) -> list[str]:
        return [line.text for line in self.entries()]

    def latest_line_id(self) -> int | None:
        with self._lock:
            if self._partial_id is not None:
                return self._partial_id
            if self._lines:
                return self._lines[-1].line_id
            return None

    def visual_rows(self, width: int) -> list[TuiVisualRow]:
        wrap_width = max(1, width)
        rows: list[TuiVisualRow] = []
        for line in self.entries():
            if line.text == "":
                rows.append(
                    TuiVisualRow(
                        line_id=line.line_id,
                        char_start=0,
                        text="",
                        logical_text=line.text,
                    )
                )
                continue
            for start in range(0, len(line.text), wrap_width):
                rows.append(
                    TuiVisualRow(
                        line_id=line.line_id,
                        char_start=start,
                        text=line.text[start : start + wrap_width],
                        logical_text=line.text,
                    )
                )
        return rows

    def clear(self) -> None:
        with self._lock:
            self._lines.clear()
            self._partial = ""
            self._partial_id = None


class TuiScrollback:
    """Stable viewport over wrapped output rows with explicit follow-tail mode."""

    def __init__(self, output: TuiOutputBuffer) -> None:
        self.output = output
        self.follow_tail = True
        self._anchor: tuple[int, int] | None = None
        self._seen_tail_id: int | None = None

    @staticmethod
    def _row_key(row: TuiVisualRow) -> tuple[int, int]:
        return (row.line_id, row.char_start)

    def _anchor_index(self, rows: list[TuiVisualRow], body_rows: int) -> int:
        tail_top = max(0, len(rows) - max(1, body_rows))
        if self.follow_tail or self._anchor is None:
            return tail_top
        if not rows:
            return 0

        line_id, char_start = self._anchor
        candidate: int | None = None
        for index, row in enumerate(rows):
            if row.line_id < line_id:
                continue
            if row.line_id > line_id:
                return candidate if candidate is not None else index
            candidate = index
            if row.char_start >= char_start:
                if row.char_start > char_start and index > 0:
                    previous = rows[index - 1]
                    if previous.line_id == line_id:
                        return index - 1
                return index
        if candidate is not None:
            return candidate
        if line_id < rows[0].line_id:
            return 0
        return tail_top

    def visible_rows(self, width: int, body_rows: int) -> list[TuiVisualRow]:
        rows = self.output.visual_rows(width)
        if not rows:
            return []
        start = self._anchor_index(rows, body_rows)
        if not self.follow_tail:
            self._anchor = self._row_key(rows[start])
        return rows[start : start + max(1, body_rows)]

    def _leave_follow(self) -> None:
        if self.follow_tail:
            self._seen_tail_id = self.output.latest_line_id()
        self.follow_tail = False

    def scroll_up(self, count: int, *, width: int, body_rows: int) -> None:
        rows = self.output.visual_rows(width)
        if not rows:
            return
        current = self._anchor_index(rows, body_rows)
        target = max(0, current - max(1, count))
        if target == current and not self.follow_tail:
            return
        self._leave_follow()
        self._anchor = self._row_key(rows[target])

    def scroll_down(self, count: int, *, width: int, body_rows: int) -> None:
        if self.follow_tail:
            return
        rows = self.output.visual_rows(width)
        if not rows:
            self.follow()
            return
        current = self._anchor_index(rows, body_rows)
        tail_top = max(0, len(rows) - max(1, body_rows))
        target = min(tail_top, current + max(1, count))
        if target >= tail_top:
            self.follow()
            return
        self._anchor = self._row_key(rows[target])

    def follow(self) -> None:
        self.follow_tail = True
        self._anchor = None
        self._seen_tail_id = self.output.latest_line_id()

    def new_line_count(self) -> int:
        if self.follow_tail:
            return 0
        latest = self.output.latest_line_id()
        if latest is None or self._seen_tail_id is None:
            return 0
        return max(0, latest - self._seen_tail_id)

    def rows_above_bottom(self, *, width: int, body_rows: int) -> int:
        if self.follow_tail:
            return 0
        rows = self.output.visual_rows(width)
        if not rows:
            return 0
        current = self._anchor_index(rows, body_rows)
        tail_top = max(0, len(rows) - max(1, body_rows))
        return max(0, tail_top - current)


    def viewport_metrics(
        self,
        *,
        width: int,
        body_rows: int,
    ) -> tuple[int, int, int]:
        rows = self.output.visual_rows(width)
        if not rows:
            return (0, 0, max(1, body_rows))
        return (
            len(rows),
            self._anchor_index(rows, body_rows),
            max(1, body_rows),
        )

    def scroll_to_row(
        self,
        target: int,
        *,
        width: int,
        body_rows: int,
    ) -> None:
        rows = self.output.visual_rows(width)
        if not rows:
            self.follow()
            return
        tail_top = max(0, len(rows) - max(1, body_rows))
        bounded = max(0, min(tail_top, target))
        if bounded >= tail_top:
            self.follow()
            return
        self._leave_follow()
        self._anchor = self._row_key(rows[bounded])


_FILE_TRANSFER_CRITICAL_SCREEN_MARKERS = (
    "[SYS] RADIO FATAL ",
    "ESP-ROM:",
    "rst:0x",
    "[SYS] CHATTER READY",
    "[disconnected:",
    "[connected:",
    "[waiting for selected device",
)


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
        log_base64: bool = False,
    ) -> None:
        self.transport = transport
        self.log_path = log_path
        self.line_ending = line_ending
        self.reconnect_delay = reconnect_delay
        self.selector = selector
        self.profile = profile
        self.receive_dir = receive_dir
        self.log_base64 = bool(log_base64)
        self.output = TuiOutputBuffer()
        self.scrollback = TuiScrollback(self.output)
        self.input_text = ""
        self.input_cursor = 0
        self.command_history: list[str] = []
        self.history_index: int | None = None
        self.history_draft = ""
        self.status = ""
        self.running = True
        self.mouse_capture = True
        self.panel = profile.make_tui_panel()
        self._was_connected = False
        self._binary_adapter = None
        self._file_transfer: FileTransferManager | None = None
        self._file_transfer_screen_muted = threading.Event()
        self._file_rate_transfer_id: str | None = None
        self._file_rate_samples: deque[tuple[float, int]] = deque()
        self.session = self._make_session(transport, profile)
        self._sync_panel_transport_identity(transport)
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
            screen_writer=self._write_session_screen,
            line_observer=self._observe_line,
            log_base64=self.log_base64,
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
                release_transfer=self._release_file_transfer,
                event_sink=self._log_file_transfer_event,
            )
            if adapter is not None
            else None
        )

    def _log_file_transfer_event(self, event: dict) -> None:
        # Progress уже виден в dedicated TUI status и создаёт по записи на chunk.
        # Остальные FT1 lifecycle/send-stage события остаются в primary log.
        if event.get("kind") == "progress":
            return
        self.session._record_primary(
            "FT1",
            json.dumps(
                event,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ),
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

        # Во время FT1 protocol/session output остаётся доступен adapter/panel/log,
        # но BINARY/protocol flood не должен засорять human TUI. Critical reset/
        # reconnect lines проходят через mute, чтобы recovery не выглядел зависанием.
        self._file_transfer_screen_muted.set()

    def _release_file_transfer(
        self,
        transfer_id: int,
        direction: str,
    ) -> None:
        del transfer_id, direction
        self._file_transfer_screen_muted.clear()

    @staticmethod
    def _critical_file_transfer_screen_text(text: str) -> str:
        kept: list[str] = []
        for line in text.splitlines(keepends=True):
            if any(marker in line for marker in _FILE_TRANSFER_CRITICAL_SCREEN_MARKERS):
                kept.append(line)
        return "".join(kept)

    def _write_session_screen(self, text: str) -> None:
        if self._file_transfer_screen_muted.is_set():
            critical = self._critical_file_transfer_screen_text(text)
            if critical:
                self.output.write(critical)
            return
        self.output.write(text)

    def _sync_panel_transport_identity(self, transport: Transport) -> None:
        panel = self.panel
        if panel is None:
            return
        setter = getattr(panel, "set_transport_identity", None)
        if callable(setter):
            setter(transport.identity_label)

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

    def _file_wire_rate_kbit_s(
        self,
        snapshot: dict,
        *,
        now: float | None = None,
    ) -> float:
        transfer_id = str(snapshot.get("transfer_id", ""))
        current_bytes = max(0, int(snapshot.get("bytes_completed", 0)))
        current_time = time.monotonic() if now is None else float(now)

        if transfer_id != self._file_rate_transfer_id:
            self._file_rate_transfer_id = transfer_id
            self._file_rate_samples.clear()

        if self._file_rate_samples:
            previous_time, previous_bytes = self._file_rate_samples[-1]
            if current_time < previous_time or current_bytes < previous_bytes:
                self._file_rate_samples.clear()

        self._file_rate_samples.append((current_time, current_bytes))
        cutoff = current_time - 1.5
        while (
            len(self._file_rate_samples) > 2
            and self._file_rate_samples[1][0] <= cutoff
        ):
            self._file_rate_samples.popleft()

        if len(self._file_rate_samples) < 2:
            return 0.0
        first_time, first_bytes = self._file_rate_samples[0]
        elapsed = current_time - first_time
        if elapsed < 0.25:
            return 0.0
        delta_bytes = max(0, current_bytes - first_bytes)
        return delta_bytes * 8.0 / elapsed / 1000.0

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
        wire_rate = self._file_wire_rate_kbit_s(snapshot)
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
            f"{snapshot.get('wire_bytes', 0)} wire bytes  "
            f"{wire_rate:.1f} kbit/s"
        )
        failure = snapshot.get("failure")
        if isinstance(failure, dict):
            second += (
                f"  ERROR {failure.get('code', '?')}: "
                f"{failure.get('message', '')}"
            )
        elif snapshot.get("final_path"):
            second += f"  -> {Path(str(snapshot['final_path'])).name}"
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

    @staticmethod
    def _compose_header(left: str, right: str, width: int) -> str:
        width = max(1, width)
        right_block = f" {right} " if right else ""
        if len(right_block) >= width:
            return TerminalTui._fit(right_block, width)
        left_width = width - len(right_block)
        return (
            TerminalTui._fit(left, left_width).ljust(left_width)
            + right_block
        )

    @staticmethod
    def _output_width(width: int) -> int:
        # Reserve one visible column at the right edge for the application
        # scroll indicator. The terminal emulator's own scrollbar cannot
        # represent curses' alternate-screen viewport.
        return max(1, width - 2)

    @staticmethod
    def _scrollbar_geometry(
        total_rows: int,
        top_row: int,
        body_rows: int,
    ) -> tuple[int, int] | None:
        body_rows = max(1, body_rows)
        if total_rows <= body_rows:
            return None
        thumb_rows = max(
            1,
            min(body_rows, round(body_rows * body_rows / total_rows)),
        )
        max_top = total_rows - body_rows
        track_range = max(0, body_rows - thumb_rows)
        thumb_top = (
            0
            if max_top <= 0
            else round(track_range * top_row / max_top)
        )
        return (thumb_top, thumb_rows)

    @staticmethod
    def _mouse_mask() -> int:
        return (
            getattr(curses, "BUTTON1_PRESSED", 0)
            | getattr(curses, "BUTTON1_CLICKED", 0)
            | getattr(curses, "BUTTON4_PRESSED", 0)
            | getattr(curses, "BUTTON4_CLICKED", 0)
            | getattr(curses, "BUTTON5_PRESSED", 0)
            | getattr(curses, "BUTTON5_CLICKED", 0)
        )

    def _set_mouse_capture(self, enabled: bool) -> None:
        self.mouse_capture = enabled
        try:
            curses.mousemask(self._mouse_mask() if enabled else 0)
        except curses.error:
            pass

    def _remember_command(self, line: str) -> None:
        if line and (not self.command_history or self.command_history[-1] != line):
            self.command_history.append(line)
            if len(self.command_history) > 500:
                del self.command_history[:-500]
        self.history_index = None
        self.history_draft = ""

    def _history_up(self) -> None:
        if not self.command_history:
            return
        if self.history_index is None:
            self.history_draft = self.input_text
            self.history_index = len(self.command_history) - 1
        elif self.history_index > 0:
            self.history_index -= 1
        self.input_text = self.command_history[self.history_index]
        self.input_cursor = len(self.input_text)

    def _history_down(self) -> None:
        if self.history_index is None:
            return
        if self.history_index < len(self.command_history) - 1:
            self.history_index += 1
            self.input_text = self.command_history[self.history_index]
        else:
            self.history_index = None
            self.input_text = self.history_draft
            self.history_draft = ""
        self.input_cursor = len(self.input_text)

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
        connected = self.session.connected_event.is_set()
        connection = "CONNECTED" if connected else "WAITING"
        header_left = (
            f" SerialTerminal | {transport.description} | "
            f"profile:{self.profile.name}"
        )
        header_right = connection
        if connected and self.panel is not None:
            profile_status = self.panel.header_status()
            if profile_status:
                header_right += f" | {profile_status}"
        header = self._compose_header(
            header_left,
            header_right,
            width=max(1, width - 1),
        )
        self._safe_addstr(
            stdscr, 0, 0, header, colors["header"]
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
        output_width = self._output_width(width)
        visible_rows = self.scrollback.visible_rows(output_width, body_rows)
        for row, visual in enumerate(visible_rows):
            self._safe_addstr(
                stdscr,
                y + row,
                0,
                visual.text,
                self._line_attr(visual.logical_text, colors),
            )

        total_rows, top_row, _ = self.scrollback.viewport_metrics(
            width=output_width,
            body_rows=body_rows,
        )
        geometry = self._scrollbar_geometry(total_rows, top_row, body_rows)
        if geometry is not None:
            thumb_top, thumb_rows = geometry
            scrollbar_x = max(0, width - 2)
            for row in range(body_rows):
                character = (
                    "█"
                    if thumb_top <= row < thumb_top + thumb_rows
                    else "│"
                )
                attr = colors["status"] if character == "█" else colors["dim"]
                self._safe_addstr(stdscr, y + row, scrollbar_x, character, attr)

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
            "PgUp/PgDn scroll | ↑↓ history | F2 Device | F3 Profile | "
            "F4 Clear | F8 Mouse | F9 Help | Ctrl+Q Quit"
        )
        if self._file_transfer is not None:
            default_status = (
                "PgUp/PgDn/Wheel scroll | ↑↓ history | F2 Device | F3 Profile | "
                "F5 Send file | F6 Cancel | F8 Mouse | F9 Help | Ctrl+Q Quit"
            )
        status = self.status or default_status
        if not self.scrollback.follow_tail:
            rows_above = self.scrollback.rows_above_bottom(
                width=self._output_width(width),
                body_rows=body_rows,
            )
            new_lines = self.scrollback.new_line_count()
            scroll_status = f"SCROLL {rows_above} rows above bottom"
            if new_lines:
                scroll_status += f" | {new_lines} new ↓"
            scroll_status += " | PgUp/PgDn/Wheel | End: follow"
            status = (
                f"{scroll_status} | {self.status}"
                if self.status
                else scroll_status
            )
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
        self._remember_command(line)
        self.input_text = ""
        self.input_cursor = 0
        self.scrollback.follow()
        self.status = ""
        self.session._submit_interactive_line(line)

    def _choose_device(self, stdscr) -> None:
        if self._file_transfer_active():
            self.status = "Cancel or finish file transfer before changing device"
            return
        curses.endwin()
        try:
            self.session._change_device()
            self._sync_panel_transport_identity(
                self.session._current_transport()
            )
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
        self._sync_panel_transport_identity(new_transport)
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

        local_path = browse_file(stdscr, start_dir=Path.cwd())
        if local_path is None:
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

    @staticmethod
    def _mouse_wheel_direction(button_state: int) -> int:
        up_mask = (
            getattr(curses, "BUTTON4_PRESSED", 0)
            | getattr(curses, "BUTTON4_CLICKED", 0)
        )
        down_mask = (
            getattr(curses, "BUTTON5_PRESSED", 0)
            | getattr(curses, "BUTTON5_CLICKED", 0)
        )
        if up_mask and button_state & up_mask:
            return -1
        if down_mask and button_state & down_mask:
            return 1
        return 0

    def _handle_mouse(self, stdscr, body_rows: int) -> None:
        try:
            _mouse_id, _x, y, _z, button_state = curses.getmouse()
        except curses.error:
            return

        height, width = stdscr.getmaxyx()
        panel_rows = len(self.panel.status_lines()) if self.panel else 0
        file_rows = len(self._file_status_lines(width))
        body_top = 2 + panel_rows + file_rows
        body_bottom = min(height - 4, body_top + body_rows)
        if not body_top <= y < body_bottom:
            return

        output_width = self._output_width(width)
        direction = self._mouse_wheel_direction(button_state)
        step = 3
        if direction < 0:
            self.scrollback.scroll_up(
                step,
                width=output_width,
                body_rows=body_rows,
            )
            return
        if direction > 0:
            self.scrollback.scroll_down(
                step,
                width=output_width,
                body_rows=body_rows,
            )
            return

        left_mask = (
            getattr(curses, "BUTTON1_PRESSED", 0)
            | getattr(curses, "BUTTON1_CLICKED", 0)
        )
        if left_mask and button_state & left_mask and _x >= width - 2:
            total_rows, _top_row, _ = self.scrollback.viewport_metrics(
                width=output_width,
                body_rows=body_rows,
            )
            if total_rows <= body_rows:
                return
            relative_y = max(0, min(body_rows - 1, y - body_top))
            tail_top = max(0, total_rows - body_rows)
            target = round(
                tail_top * relative_y / max(1, body_rows - 1)
            )
            self.scrollback.scroll_to_row(
                target,
                width=output_width,
                body_rows=body_rows,
            )

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
            self.scrollback.follow()
            self.status = "Screen cleared; log files were not changed"
        elif key == curses.KEY_F5:
            self._choose_file(stdscr)
        elif key == curses.KEY_F6:
            self._cancel_file()
        elif key == curses.KEY_F8:
            self._set_mouse_capture(not self.mouse_capture)
            self.status = (
                "Mouse capture ON: wheel/scrollbar active; "
                "Shift+mouse reaches terminal"
                if self.mouse_capture
                else "Mouse capture OFF: terminal selection/RMB restored"
            )
        elif key == curses.KEY_F9:
            self.session._show_full_help()
            self.status = "Help added to terminal output"
        elif key == curses.KEY_PPAGE:
            self.scrollback.scroll_up(
                max(1, body_rows),
                width=self._output_width(stdscr.getmaxyx()[1]),
                body_rows=body_rows,
            )
        elif key == curses.KEY_NPAGE:
            self.scrollback.scroll_down(
                max(1, body_rows),
                width=self._output_width(stdscr.getmaxyx()[1]),
                body_rows=body_rows,
            )
        elif key == curses.KEY_END:
            self.scrollback.follow()
        elif key == curses.KEY_MOUSE:
            self._handle_mouse(stdscr, body_rows)
        elif key == curses.KEY_UP:
            self._history_up()
        elif key == curses.KEY_DOWN:
            self._history_down()
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
        self._set_mouse_capture(True)
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
    curses.wrapper(tui.run)
    return 0
