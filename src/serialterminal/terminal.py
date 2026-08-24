from __future__ import annotations

import queue
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

try:
    import readline as _readline  # noqa: F401 - enables line editing/history
except ImportError:
    _readline = None

from .transports.base import Transport, TransportError


def encode_line(line: str, line_ending: str = "\n") -> bytes:
    return (line + line_ending).encode("utf-8")


class TerminalSession:
    """Line-oriented terminal independent from the underlying transport."""

    def __init__(
        self,
        transport: Transport,
        log_path: str | Path = "serialterminal.log",
        line_ending: str = "\n",
        reconnect_delay: float = 0.5,
    ):
        self.transport = transport
        self.log_path = Path(log_path)
        self.line_ending = line_ending
        self.reconnect_delay = reconnect_delay

        self.stop_event = threading.Event()
        self.connected_event = threading.Event()
        self.output_lock = threading.Lock()
        self.outgoing: queue.Queue[str] = queue.Queue()

        self.log_file = self.log_path.open("a", encoding="utf-8", buffering=1)
        stamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z")
        self.log_file.write(f"\n===== serialterminal session {stamp} =====\n")
        self.log_file.flush()

    def write_output(self, text: str) -> None:
        with self.output_lock:
            sys.stdout.write(text)
            sys.stdout.flush()
            self.log_file.write(text)
            self.log_file.flush()

    def log_input(self, line: str) -> None:
        with self.output_lock:
            self.log_file.write(line + "\n")
            self.log_file.flush()

    def _connect(self) -> bool:
        if not self.transport.connect():
            return False

        self.connected_event.set()
        self.write_output(f"\n[connected: {self.transport.description}]\n\n")
        return True

    def _disconnect(self) -> None:
        self.connected_event.clear()
        self.transport.disconnect()

    def rx_loop(self) -> None:
        waiting_printed = False

        while not self.stop_event.is_set():
            if not self.connected_event.is_set():
                if not waiting_printed:
                    self.write_output("[waiting for device...]\n")
                    waiting_printed = True

                if self._connect():
                    waiting_printed = False
                else:
                    time.sleep(self.reconnect_delay)
                    continue

            try:
                data = self.transport.read(512)
                if data:
                    self.write_output(data.decode("utf-8", errors="replace"))
            except (TransportError, OSError):
                if self.stop_event.is_set():
                    break
                old = self.transport.description
                self._disconnect()
                self.write_output(f"\n[disconnected: {old}]\n\n")
                time.sleep(0.3)

    def _write_line(self, line: str) -> None:
        self.transport.write(encode_line(line, self.line_ending))

    def tx_loop(self) -> None:
        """Send complete input lines in order, retaining them across reconnects."""
        while not self.stop_event.is_set():
            try:
                line = self.outgoing.get(timeout=0.1)
            except queue.Empty:
                continue

            try:
                while not self.stop_event.is_set():
                    if not self.connected_event.wait(timeout=0.1):
                        continue

                    try:
                        self._write_line(line)
                        break
                    except (TransportError, OSError):
                        # Keep `line` as the current item. It will be retried
                        # after rx_loop reconnects to the same transport target.
                        self._disconnect()
                        self.write_output("\n[send failed; reconnecting]\n")
                        time.sleep(self.reconnect_delay)
            finally:
                self.outgoing.task_done()

    def send_line(self, line: str) -> bool:
        """Queue one complete line; it is never split into per-key writes."""
        if self.stop_event.is_set():
            return False
        self.outgoing.put(line)
        return True

    def run(self) -> None:
        rx = threading.Thread(target=self.rx_loop, daemon=True)
        tx = threading.Thread(target=self.tx_loop, daemon=True)
        rx.start()
        tx.start()

        self.write_output("serialterminal\n")
        self.write_output("Ctrl-C to exit\n")
        self.write_output("Commands are sent only after Enter.\n")
        self.write_output("Typed commands are retained across reconnects.\n")
        self.write_output(f"Log: {self.log_path}\n\n")

        try:
            while not self.stop_event.is_set():
                try:
                    line = input()
                except EOFError:
                    break

                self.log_input(line)
                self.send_line(line)
        except KeyboardInterrupt:
            self.write_output("\n[exit]\n")
        finally:
            self.stop_event.set()
            rx.join(timeout=1.0)
            tx.join(timeout=1.0)
            self._disconnect()
            with self.output_lock:
                self.log_file.flush()
                self.log_file.close()
