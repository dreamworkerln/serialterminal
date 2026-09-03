from __future__ import annotations

import os
import select
import sys
import time


class InitialControlReader:
    """Temporarily expose startup hotkeys before prompt_toolkit is running."""

    def __init__(self):
        self.fd: int | None = None
        self._previous = None
        self._termios = None
        self._control_t_pending = False

    def __enter__(self) -> InitialControlReader:
        if not sys.stdin.isatty():
            return self

        try:
            import termios
            import tty
        except ImportError:
            return self

        fd = sys.stdin.fileno()
        previous = termios.tcgetattr(fd)

        # Initial discovery может занимать несколько секунд. Держим stdin в
        # cbreak на всём протяжении scan, чтобы Ctrl+T s, введённый во время
        # discovery, не застревал в canonical input до Enter. Перед scanner/menu
        # исходный режим TTY обязательно восстанавливается через __exit__().
        tty.setcbreak(fd)
        self.fd = fd
        self._previous = previous
        self._termios = termios
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.fd is None or self._termios is None or self._previous is None:
            return
        self._termios.tcsetattr(
            self.fd,
            self._termios.TCSADRAIN,
            self._previous,
        )

    def read(self, timeout: float = 0.0) -> str | None:
        if timeout < 0:
            raise ValueError("timeout must be non-negative")

        if self.fd is None:
            if timeout:
                time.sleep(timeout)
            return None

        deadline = time.monotonic() + timeout

        while True:
            remaining = max(0.0, deadline - time.monotonic())
            readable, _, _ = select.select([self.fd], [], [], remaining)
            if not readable:
                return None

            data = os.read(self.fd, 1)
            if not data:
                return None
            key = data.decode("latin-1")

            if key == "\x03":
                raise KeyboardInterrupt

            if self._control_t_pending:
                if key.lower() == "s":
                    self._control_t_pending = False
                    return "scanner"
                self._control_t_pending = key == "\x14"
                continue

            self._control_t_pending = key == "\x14"
