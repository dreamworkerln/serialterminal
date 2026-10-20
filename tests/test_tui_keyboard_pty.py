"""Проверка реального ncurses-ввода; физических transport в этом тесте нет."""
import curses
import fcntl
import json
import os
from pathlib import Path
import pty
import select
import struct
import subprocess
import sys
import termios
import threading
import time
from types import SimpleNamespace

from serialterminal.tui_core import TerminalTui


def _keyboard_child(result_fd):
    def emit(value):
        os.write(result_fd, (json.dumps(value) + "\n").encode())

    # Используем production run/get_wch и настоящий PTY, заменяя только
    # session и рисование: проверка клавиатуры не открывает USB/BLE.
    tui = object.__new__(TerminalTui)
    tui.running = True
    tui._application_error = False
    tui._file_transfer = None
    tui.session = SimpleNamespace(
        start=lambda: None, stop_event=threading.Event(),
        _reveal_sent_presentations=lambda: None,
        stop=lambda: None, close_logs=lambda: None,
    )
    tui.output = SimpleNamespace(write=lambda text: None)
    tui._set_mouse_capture = lambda enabled: None
    tui._run_connected_actions = lambda: None
    ready = False
    keys = []

    def render(screen):
        nonlocal ready
        if not ready:
            ready = True
            emit({"ready": True, "up": list(curses.tigetstr("kcuu1")),
                  "f6": list(curses.tigetstr("kf6"))})
        return 0

    def handle(screen, key, body_rows):
        keys.append(key)
        emit({"key": key, "at": time.monotonic(),
              "escape_delay_ms": curses.get_escdelay()})
        if len(keys) == 104:
            tui.running = False

    tui._render = render
    tui._handle_key = handle
    curses.wrapper(tui.run)


def test_escape_is_prompt_without_repeating_letters_or_breaking_function_keys(tmp_path):
    master, slave = pty.openpty()
    reader, writer = os.pipe()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 80, 0, 0))
    source = Path(__file__).resolve().parents[1] / "src"
    env = dict(os.environ, TERM="xterm-256color", LC_ALL="C.UTF-8", ESCDELAY="1000",
               PYTHONPATH=str(source) + os.pathsep + os.environ.get("PYTHONPATH", ""))
    code = "import runpy,sys; runpy.run_path(sys.argv[1])['_keyboard_child'](int(sys.argv[2]))"
    buffer = bytearray()
    child = None
    with (tmp_path / "keyboard.stderr").open("wb") as stderr:
        try:
            child = subprocess.Popen([sys.executable, "-c", code, __file__, str(writer)],
                                     stdin=slave, stdout=slave, stderr=stderr,
                                     pass_fds=(writer,), env=env, cwd=tmp_path)
            os.close(slave)
            os.close(writer)

            def receive():
                deadline = time.monotonic() + 5
                while b"\n" not in buffer:
                    remaining = deadline - time.monotonic()
                    assert remaining > 0, "ncurses keyboard child did not respond"
                    readable, _, _ = select.select([reader, master], [], [], remaining)
                    if master in readable:
                        os.read(master, 65536)
                    if reader in readable:
                        data = os.read(reader, 65536)
                        assert data, (tmp_path / "keyboard.stderr").read_text()
                        buffer.extend(data)
                raw, _, rest = buffer.partition(b"\n")
                buffer[:] = rest
                return json.loads(raw)

            ready = receive()
            assert ready["ready"]
            started = time.monotonic()
            os.write(master, b"\x1b")
            escape = receive()
            assert escape["key"] == "\x1b"
            delay = escape["at"] - started
            assert delay < 0.5, f"Standalone Esc took {delay:.3f}s"
            assert escape["escape_delay_ms"] == 25

            # Ускорение Esc не синтезирует повторные буквы: 100 отправленных
            # символов должны дать ровно 100 событий, а UTF-8 — один символ.
            os.write(master, b"a" * 100 + "я".encode())
            assert [receive()["key"] for _ in range(100)] == ["a"] * 100
            assert receive()["key"] == "я"
            # Проверяем не только уже готовую строку escape sequence:
            # небольшая фрагментация функциональных клавиш тоже допустима.
            for name, expected in (("up", curses.KEY_UP), ("f6", curses.KEY_F6)):
                for byte in ready[name]:
                    os.write(master, bytes([byte]))
                    time.sleep(.005)
                assert receive()["key"] == expected
            child.wait(timeout=5)
            assert child.returncode == 0, (tmp_path / "keyboard.stderr").read_text()
            (tmp_path / "keyboard_metrics.json").write_text(json.dumps({
                "escape_delay_seconds": delay, "escape_delay_ms": escape["escape_delay_ms"],
                "letters": 100, "unicode": True, "fragmented_arrows_and_f6": True,
            }))
        finally:
            if child is None:
                os.close(slave)
                os.close(writer)
            elif child.poll() is None:
                child.kill()
                child.wait()
            os.close(reader)
            os.close(master)
