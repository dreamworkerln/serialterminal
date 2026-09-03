from __future__ import annotations

import os
import select
import sys
import time


def read_initial_control(timeout: float = 0.5) -> str | None:
    """Read startup-only hotkeys while initial device discovery is retrying."""
    if timeout < 0:
        raise ValueError("timeout must be non-negative")

    if not sys.stdin.isatty():
        if timeout:
            time.sleep(timeout)
        return None

    try:
        import termios
        import tty
    except ImportError:
        if timeout:
            time.sleep(timeout)
        return None

    fd = sys.stdin.fileno()
    previous = termios.tcgetattr(fd)
    deadline = time.monotonic() + timeout
    control_t_pending = False

    try:
        # В initial discovery ещё нет prompt_toolkit session, поэтому коротко
        # переводим stdin в cbreak, чтобы Ctrl+T s можно было поймать до
        # подключения первого устройства. Состояние TTY всегда восстанавливаем
        # до запуска scanner/menu, чтобы вложенный prompt получил обычный TTY.
        tty.setcbreak(fd)

        while True:
            remaining = max(0.0, deadline - time.monotonic())
            readable, _, _ = select.select([fd], [], [], remaining)
            if not readable:
                return None

            data = os.read(fd, 1)
            if not data:
                return None
            key = data.decode("latin-1")

            if key == "\x03":
                raise KeyboardInterrupt

            if control_t_pending:
                if key.lower() == "s":
                    return "scanner"
                control_t_pending = key == "\x14"
                continue

            control_t_pending = key == "\x14"
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, previous)
