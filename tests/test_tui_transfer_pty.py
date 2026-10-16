"""Настоящий curses/PTY без открытия физических transport."""
import curses
import errno
import json
import locale
import os
from pathlib import Path
import pty
import select
import struct
import subprocess
import sys
import time
import fcntl
import termios
from types import SimpleNamespace

import pyte
import pytest

from serialterminal.profiles import GENERIC_PROFILE
from serialterminal.profiles.chatter import CHATTER_PROFILE
from serialterminal.transports.base import Transport
from serialterminal.tui import TerminalTui
from serialterminal.tui_text import cell_width
from serialterminal.tui_file_transfer import init_file_transfer_colors


class OfflineTransport(Transport):
    is_connected = False
    description = "OFFLINE TEST"

    def connect(self):
        raise AssertionError("PTY test must never connect hardware")

    def disconnect(self):
        pass

    def read(self, size=512):
        raise AssertionError("PTY test must never read hardware")

    def write(self, data):
        raise AssertionError("PTY test must never write hardware")


class Manager:
    busy = True

    def __init__(self):
        self.value = dict(transfer_id="0000000000000001", state="sending", direction="TX",
                          filename="проверка-界e\u0301👩\u200d💻🇷🇺.bin", percentage=42.5, elapsed=12,
                          bytes_completed=85, wire_bytes=200, chunks_completed=2, chunks_total=5)
        self.cancelled = []
        self.event_sink = None
        self.resumed = 0

    def display_snapshot(self):
        return {**self.value, "presentation": {
            "attempt": self.value["transfer_id"], "active": self.busy, "resume": self.resumed,
        }}

    def cancel(self, ident, *, expected_attempt=None):
        assert expected_attempt == self.value["transfer_id"]
        self.cancelled.append(ident)
        self.finish("cancelled")

    def finish(self, state, failure=None):
        self.value["state"] = state
        self.busy = False
        if failure:
            self.value["failure"] = failure
        self.event_sink({"kind": "transfer_" + state, "transfer_id": self.value["transfer_id"],
                         "direction": self.value["direction"], "filename": self.value["filename"],
                         "progress": self.display_snapshot()})


def _child(folder, direction):
    folder = Path(folder)
    locale.setlocale(locale.LC_ALL, "")
    tui = TerminalTui(transport=OfflineTransport(), log_path=str(folder / "offline.log"),
                      line_ending="\n", reconnect_delay=1, profile=GENERIC_PROFILE,
                      selector=SimpleNamespace(choose_transport_menu=lambda: None))
    tui.profile = CHATTER_PROFILE
    manager = Manager()
    manager.value.update(direction=direction, state="sending" if direction == "TX" else "receiving")
    tui._file_transfer = manager
    manager.event_sink = lambda event: tui._log_file_transfer_event(event, manager=manager)
    tui._colors = lambda: {**{name: curses.A_REVERSE if name == "header" else 0
                             for name in ("normal", "header", "panel", "status", "error",
                                          "input", "error_badge", "dim")},
                           "normal": curses.color_pair(1),
                           **getattr(tui, "_file_colors", {})}
    sent = []
    tui.session._submit_interactive_line = sent.append
    frames = []

    def run(screen):
        screen.keypad(True)
        curses.init_pair(1, curses.COLOR_WHITE, curses.COLOR_BLACK)
        tui._file_colors = init_file_transfer_colors()
        assert curses.pair_content(8) == (255, 236)
        assert curses.pair_content(9) == (141, 236)
        def frame(label):
            reads = []
            original = manager.display_snapshot
            def read_once():
                reads.append(True)
                return original()
            manager.display_snapshot = read_once
            tui._render(screen)
            manager.display_snapshot = original
            rows, columns = screen.getmaxyx()
            if columns >= 60 and rows >= 12:
                assert len(reads) == 1
                assert screen.getyx()[0] == rows - 3
            lines = [screen.instr(row, 0).decode("utf-8", errors="replace") for row in range(rows)]
            for line in lines:
                if "проверка" in line and line.lstrip().startswith("│ "):
                    borders = [cell_width(line[:index]) for index, char in enumerate(line) if char == "│"]
                    assert 2 in borders and columns - 3 in borders, repr(line)
            frames.append(dict(label=label, rows=rows, columns=columns, lines=lines))
            return "\n".join(lines)
        def key(value):
            if isinstance(value, int):
                curses.ungetch(value)
            else:
                curses.unget_wch(value)
            tui._handle_key(screen, screen.get_wch(), 10)
        for rows, columns in [(24, 80), (32, 120), (48, 200), (12, 60), (8, 35), (24, 80)]:
            fcntl.ioctl(sys.stdout.fileno(), termios.TIOCSWINSZ, struct.pack("HHHH", rows, columns, 0, 0))
            curses.resizeterm(rows, columns)
            text = frame("resize")
            assert ("Передача файла" in text) == (columns >= 60 and rows >= 12)
            if columns >= 60 and rows >= 12:
                assert "F4 Clear" in text
            assert manager.value["transfer_id"] == "0000000000000001"
        key(curses.KEY_F7)
        tui.output.write("clear this output\n")
        tui.input_text = "/clear"
        tui.input_cursor = len(tui.input_text)
        before_log = Path(tui.session.log_path).read_bytes()
        key("\n")
        assert tui.output.snapshot() == []
        assert Path(tui.session.log_path).read_bytes() == before_log
        assert not manager.cancelled and not sent and manager.busy
        assert tui._file_window().visible is False
        assert "clear this output" not in frame("local_clear")
        tui.input_text = "/tele"
        key("\n")
        for _ in range(10000):
            for line in ("", "/m1 BASE64", "telemetry useful \x00\x1b[2J\x85"):
                if CHATTER_PROFILE.human_line_visible("chat", line):
                    tui.output.write(line + "\n")
        text = frame("flood_background")
        assert f"File {direction}" in text and "telemetry useful" in text
        assert "\\x00" in text and "\\x1b" in text
        key(curses.KEY_F7)
        assert "Передача файла" in frame("flood_foreground")
        key("\x1b")
        text = frame("confirmation")
        assert "[ Нет ]" in text and "[ Да ]" in text
        key(curses.KEY_LEFT)
        key("\n")
        assert not manager.cancelled
        key("\x1b")
        manager.value["percentage"] = 60
        key("\x1b")
        assert "60.0%" in frame("continued")
        key(curses.KEY_F10)
        assert "F10" not in frame("f10_ignored")
        assert tui._file_window().confirmation_id is None
        key("\x1b")
        curses.resizeterm(12, 60)
        assert "Подтверждение" in frame("confirmation_small")
        curses.resizeterm(24, 80)
        key("\n")
        assert manager.cancelled == ["0000000000000001"]
        text = frame("cancel_retained")
        assert "Передача файла" in text and f"File {direction}" not in text
        assert tui._file_window().confirmation_id is None
        assert "прервано пользователем" in text
        key(curses.KEY_F7)
        assert "Передача файла" in frame("cancel_f7_ignored")
        key("\x1b")
        assert "Передача файла" not in frame("cancel_closed")
        key(curses.KEY_F7)
        assert not tui._file_window().visible
        manager.value.update(transfer_id="0000000000000002", state="sending" if direction == "TX" else "receiving",
                             filename="next.bin")
        manager.busy = True
        assert "Передача файла" in frame("next_active")
        key(curses.KEY_F7)
        active_state = manager.value["state"]
        manager.value["state"] = "recovering_local_node"
        assert "Передача файла" not in frame("recovering_background")
        manager.value["state"] = active_state
        manager.resumed += 1
        assert "Передача файла" in frame("resumed_foreground")
        key(curses.KEY_F7)
        assert "Передача файла" not in frame("resumed_background_again")
        manager.finish("completed")
        text = frame("success_background")
        assert "успешно" in text and "Передача файла" not in text
        key(curses.KEY_F7)
        assert "Передача файла" not in frame("success_f7_ignored")
        manager.value.update(transfer_id="0000000000000003", state="sending" if direction == "TX" else "receiving",
                             filename="ERROR.bin")
        manager.busy = True
        assert "Передача файла" in frame("error_next_active")
        manager.finish("failed", {"code": "storage_failed", "message": "FAILED диск полон"})
        lines = [line for line in tui.output.snapshot() if line.startswith("[FT1] ")]
        assert len(lines) == 3
        assert "ошибка" in lines[-1] and "storage_failed" in lines[-1]
        assert "Передача файла" in frame("failure")
        key("\x1b")
        text = frame("failure_closed")
        assert "ошибка" in text and "Передача файла" not in text
        status_row = next(row for row in range(24)
                          if screen.instr(row, 0).decode("utf-8", errors="replace").startswith(f"[FT1] {direction} «ERROR.bin»"))
        assert screen.inch(status_row, 0) & curses.A_COLOR == curses.color_pair(1)
        key(curses.KEY_F7)
        assert "Передача файла" not in frame("failure_f7_ignored")
        assert sent == ["/tele"]
        assert tui._file_transfer is manager
    try:
        curses.wrapper(run)
        (folder / "frames.json").write_text(json.dumps(frames, ensure_ascii=False), encoding="utf-8")
    finally:
        tui.session.close_logs()


@pytest.mark.parametrize("direction", ["TX", "RX"])
def test_actual_curses_resize_flood_progress_and_confirmation(tmp_path, direction):
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 80, 0, 0))
    source = Path(__file__).resolve().parents[1] / "src"
    env = dict(os.environ, TERM="xterm-256color", LC_ALL="C.UTF-8",
               PYTHONPATH=str(source) + os.pathsep + os.environ.get("PYTHONPATH", ""))
    code = "import runpy,sys; runpy.run_path(sys.argv[1])['_child'](sys.argv[2], sys.argv[3])"
    child = subprocess.Popen([sys.executable, "-c", code, __file__, str(tmp_path), direction],
                             stdin=slave, stdout=slave, stderr=slave, env=env, cwd=tmp_path)
    os.close(slave)
    captured = bytearray()
    deadline = time.monotonic() + 30
    try:
        while time.monotonic() < deadline:
            readable, _, _ = select.select([master], [], [], .1)
            if readable:
                try:
                    data = os.read(master, 65536)
                except OSError as exc:
                    if exc.errno == errno.EIO:
                        break
                    raise
                if not data:
                    break
                captured.extend(data)
            elif child.poll() is not None:
                break
        child.wait(timeout=2)
    finally:
        if child.poll() is None:
            child.kill()
            child.wait()
        os.close(master)
    assert child.returncode == 0, captured.decode("utf-8", errors="replace")[-6000:]
    frames = json.loads((tmp_path / "frames.json").read_text())
    assert len(frames) == 26
    screen = pyte.Screen(200, 48)
    pyte.Stream(screen).feed(captured.decode("utf-8", errors="replace"))
    assert any("[FT1]" in line for line in screen.display)
