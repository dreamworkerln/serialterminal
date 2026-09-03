import os
import pty

from serialterminal import startup_controls


def test_read_initial_control_detects_buffered_scanner_hotkey(monkeypatch):
    master_fd, slave_fd = pty.openpty()
    stdin = os.fdopen(os.dup(slave_fd), "r", encoding="utf-8", buffering=1)

    try:
        monkeypatch.setattr(startup_controls.sys, "stdin", stdin)
        os.write(master_fd, b"\x14s")

        assert startup_controls.read_initial_control(0.1) == "scanner"
    finally:
        stdin.close()
        os.close(master_fd)
        os.close(slave_fd)
