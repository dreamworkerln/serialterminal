from __future__ import annotations

from dataclasses import dataclass
import queue
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.patch_stdout import patch_stdout

from .transports.base import ReceivedChunk, Transport, TransportError


def encode_line(line: str, line_ending: str = "\n") -> bytes:
    return (line + line_ending).encode("utf-8")


@dataclass(frozen=True)
class _ControlRequest:
    action: str
    buffered_line: str


class TerminalSession:
    """Line-oriented terminal independent from the underlying transport."""

    def __init__(
        self,
        transport: Transport,
        log_path: str | Path = "serialterminal.log",
        line_ending: str = "\n",
        reconnect_delay: float = 0.5,
        device_chooser: Callable[[], Transport | None] | None = None,
    ):
        self.transport = transport
        self.log_path = Path(log_path)
        self.line_ending = line_ending
        self.reconnect_delay = reconnect_delay
        self.device_chooser = device_chooser

        self.stop_event = threading.Event()
        self.connected_event = threading.Event()
        self.connection_paused = threading.Event()
        self.output_lock = threading.Lock()
        self.transport_lock = threading.Lock()
        self.outgoing: queue.Queue[str] = queue.Queue()

        # BLE starts in compact CHAT view. Plain Serial uses stream `main`, which
        # is always visible because USB firmware output is physically combined.
        self.view_mode = "chat"

        self.log_file = self.log_path.open("a", encoding="utf-8", buffering=1)
        stamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z")
        self.log_file.write(f"\n===== serialterminal session {stamp} =====\n")
        self.log_file.flush()

    def _current_transport(self) -> Transport:
        with self.transport_lock:
            return self.transport

    def write_output(self, text: str) -> None:
        """Write local terminal/status output to both screen and transcript."""
        with self.output_lock:
            sys.stdout.write(text)
            sys.stdout.flush()
            self.log_file.write(text)
            self.log_file.flush()

    def _received_visible(self, stream: str) -> bool:
        if stream == "main":
            return True
        if self.view_mode == "both":
            return True
        return stream == self.view_mode

    def write_received(self, chunk: ReceivedChunk) -> None:
        if not chunk.data:
            return

        text = chunk.data.decode("utf-8", errors="replace")
        with self.output_lock:
            # Always retain both BLE streams in the transcript, even when one is
            # hidden from the current screen view.
            self.log_file.write(text)
            self.log_file.flush()

            if self._received_visible(chunk.stream):
                sys.stdout.write(text)
                sys.stdout.flush()

    def log_input(self, line: str) -> None:
        with self.output_lock:
            self.log_file.write(line + "\n")
            self.log_file.flush()

    def _connect(self) -> bool:
        if self.connection_paused.is_set():
            return False

        transport = self._current_transport()
        if not transport.connect():
            return False

        if self.connection_paused.is_set() or transport is not self._current_transport():
            transport.disconnect()
            return False

        self.connected_event.set()
        self.write_output(f"\n[connected: {transport.description}]\n\n")
        return True

    def _disconnect(self) -> None:
        self.connected_event.clear()
        self._current_transport().disconnect()

    def rx_loop(self) -> None:
        waiting_printed = False

        while not self.stop_event.is_set():
            if self.connection_paused.is_set():
                time.sleep(0.05)
                continue

            if not self.connected_event.is_set():
                if not waiting_printed:
                    self.write_output("[waiting for selected device...]\n")
                    waiting_printed = True

                if self._connect():
                    waiting_printed = False
                else:
                    time.sleep(self.reconnect_delay)
                    continue

            transport = self._current_transport()
            try:
                chunk = transport.read_chunk(512)
                self.write_received(chunk)
            except (TransportError, OSError):
                if self.stop_event.is_set():
                    break
                old = transport.description
                self.connected_event.clear()
                transport.disconnect()
                self.write_output(f"\n[disconnected: {old}]\n\n")
                time.sleep(0.3)

    def _write_line(self, line: str) -> None:
        self._current_transport().write(encode_line(line, self.line_ending))

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
                        # after reconnect to the currently locked target.
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

    def _build_key_bindings(self) -> KeyBindings:
        bindings = KeyBindings()

        def add_control(sequence: str, action: str) -> None:
            @bindings.add("c-t", sequence)
            def _handler(event) -> None:
                event.app.exit(
                    result=_ControlRequest(
                        action=action,
                        buffered_line=event.app.current_buffer.text,
                    )
                )

        add_control("1", "chat")
        add_control("2", "telemetry")
        add_control("3", "both")
        add_control("d", "device")
        add_control("i", "info")
        add_control("?", "help")

        @bindings.add("c-c", eager=True)
        def _quit(event) -> None:
            event.app.exit(exception=KeyboardInterrupt)

        return bindings

    def _set_view_mode(self, mode: str) -> None:
        transport = self._current_transport()
        capabilities = set(transport.stream_capabilities)

        if capabilities == {"main"}:
            self.write_output(
                "\n[stream: USB/Serial is physically combined; "
                "CHAT/TELEMETRY filtering is BLE-only]\n\n"
            )
            return

        self.view_mode = mode
        self.write_output(f"\n[view: {mode.upper()}]\n\n")

    def _print_status(self) -> None:
        transport = self._current_transport()
        streams = ", ".join(transport.stream_capabilities)
        self.write_output(
            "\n[status]\n"
            f"  connected : {'yes' if self.connected_event.is_set() else 'no'}\n"
            f"  device    : {transport.description}\n"
            f"  device key: {transport.device_key}\n"
            f"  view      : {self.view_mode.upper()}\n"
            f"  streams   : {streams}\n"
            "\n"
        )

    def _print_hotkey_help(self) -> None:
        self.write_output(
            "\n[hotkeys]\n"
            "  Ctrl+C       quit immediately\n"
            "  Ctrl+T 1     CHAT view\n"
            "  Ctrl+T 2     TELEMETRY view\n"
            "  Ctrl+T 3     BOTH views\n"
            "  Ctrl+T d     device chooser\n"
            "  Ctrl+T i     connection/status\n"
            "  Ctrl+T ?     this help\n"
            "\n"
        )

    def _change_device(self) -> None:
        if self.device_chooser is None:
            self.write_output("\n[device chooser is not available]\n\n")
            return

        old_transport = self._current_transport()
        self.connection_paused.set()
        self.connected_event.clear()
        old_transport.disconnect()

        try:
            new_transport = self.device_chooser()
        except KeyboardInterrupt:
            # Ctrl+C must remain a hard exit even while the numbered menu is up.
            raise
        except Exception as exc:
            self.write_output(f"\n[device chooser failed: {exc}]\n\n")
            new_transport = None

        if new_transport is None:
            self.write_output("\n[device selection cancelled; keeping current target]\n\n")
        elif new_transport.device_key == old_transport.device_key:
            new_transport.close()
            self.write_output("\n[selected the same device]\n\n")
        else:
            with self.transport_lock:
                self.transport = new_transport
            old_transport.close()
            self.write_output(
                f"\n[locked target: {new_transport.description}]\n"
                "[future reconnects will only retry this target]\n\n"
            )

        self.connection_paused.clear()

    def _handle_control(self, action: str) -> None:
        if action in {"chat", "telemetry", "both"}:
            self._set_view_mode(action)
            return
        if action == "device":
            self._change_device()
            return
        if action == "info":
            self._print_status()
            return
        if action == "help":
            self._print_hotkey_help()
            return

    def run(self) -> None:
        rx = threading.Thread(target=self.rx_loop, daemon=True)
        tx = threading.Thread(target=self.tx_loop, daemon=True)
        rx.start()
        tx.start()

        self.write_output("serialterminal\n")
        self.write_output("Ctrl-C to exit immediately.\n")
        self.write_output("Ctrl-T ? for local hotkeys.\n")
        self.write_output("Commands are sent only after Enter.\n")
        self.write_output("Typed commands are retained across reconnects.\n")
        self.write_output(f"Log: {self.log_path}\n\n")

        prompt = PromptSession(key_bindings=self._build_key_bindings())
        buffered_line = ""

        try:
            with patch_stdout():
                while not self.stop_event.is_set():
                    try:
                        result = prompt.prompt(default=buffered_line)
                    except EOFError:
                        break

                    if isinstance(result, _ControlRequest):
                        buffered_line = result.buffered_line
                        self._handle_control(result.action)
                        continue

                    buffered_line = ""
                    line = result
                    self.log_input(line)
                    self.send_line(line)
        except KeyboardInterrupt:
            self.write_output("\n[exit]\n")
        finally:
            self.stop_event.set()
            self.connection_paused.clear()
            rx.join(timeout=1.0)
            tx.join(timeout=1.0)
            current = self._current_transport()
            current.close()
            with self.output_lock:
                self.log_file.flush()
                self.log_file.close()
