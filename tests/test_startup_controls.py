import os
import pty
import termios

from serialterminal import startup_controls


def test_initial_control_reader_detects_scanner_hotkey_during_scan(monkeypatch):
    master_fd, slave_fd = pty.openpty()
    stdin = os.fdopen(os.dup(slave_fd), "r", encoding="utf-8", buffering=1)
    original = termios.tcgetattr(slave_fd)

    try:
        monkeypatch.setattr(startup_controls.sys, "stdin", stdin)

        with startup_controls.InitialControlReader() as controls:
            os.write(master_fd, b"\x14s")
            assert controls.read(0.1) == "scanner"

        assert termios.tcgetattr(slave_fd) == original
    finally:
        stdin.close()
        os.close(master_fd)
        os.close(slave_fd)
