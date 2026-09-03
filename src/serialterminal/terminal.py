from __future__ import annotations

import codecs
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

from .presentation import PresentationTracker, recognized_chatter_command
from .transports.base import ReceivedChunk, Transport, TransportError
from .transports.serial import SerialTransport


CHATTER_ECHO_TOGGLE = "\x14e"
CHATTER_OUTPUT_MODE_COMMANDS = {
    "output_chat": "\x141",
    "output_telemetry": "\x142",
    "output_both": "\x143",
}
CHATTER_HELP_COMMAND = "/help"
CHATTER_ID_COMMAND = "/id"
CHATTER_SYSTEM_PREFIX = "[SYS]"


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
        self.decode_lock = threading.Lock()
        self.outgoing: queue.Queue[str] = queue.Queue()
        self._presentation = PresentationTracker()
        self._received_decoders = {}
        self._received_line_buffers = {}
        self._hidden_chat_line_buffer = ""

        # Human console follows the primary/main stream. BLE 0004 telemetry is
        # still subscribed and retained in the transcript, but is background
        # machine data rather than a second user-visible VIEW.
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

    def _write_console_only(self, text: str) -> None:
        """Write local presentation text without duplicating the transcript."""
        with self.output_lock:
            sys.stdout.write(text)
            sys.stdout.flush()

    def _received_visible(self, stream: str) -> bool:
        if stream == "main":
            return True
        if self.view_mode == "both":
            return True
        return stream == self.view_mode

    def _decode_received(self, stream: str, data: bytes) -> str:
        """Decode one logical stream without breaking UTF-8 at chunk boundaries."""
        with self.decode_lock:
            decoder = self._received_decoders.get(stream)
            if decoder is None:
                decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
                self._received_decoders[stream] = decoder
            return decoder.decode(data, final=False)

    def _complete_received_lines(self, stream: str, text: str) -> list[str]:
        """Return complete decoded lines while retaining one partial tail per stream."""
        with self.decode_lock:
            combined = self._received_line_buffers.get(stream, "") + text
            lines = combined.splitlines(keepends=True)

            if lines and not lines[-1].endswith(("\n", "\r")):
                self._received_line_buffers[stream] = lines.pop()
            else:
                self._received_line_buffers[stream] = ""

            return lines

    def _reset_received_decoders(self) -> None:
        """Discard incomplete characters/lines when a transport connection changes."""
        with self.decode_lock:
            self._received_decoders.clear()
            self._received_line_buffers.clear()
            self._hidden_chat_line_buffer = ""

    def _hidden_chat_system_text(self, stream: str, text: str) -> str:
        """Compatibility helper for complete [SYS] lines from a hidden CHAT stream."""
        if stream != "chat" or not text:
            return ""
        return "".join(
            line
            for line in text.splitlines(keepends=True)
            if line.startswith(CHATTER_SYSTEM_PREFIX)
        )

    def _received_line_visible(self, stream: str, line: str) -> bool:
        if self._received_visible(stream):
            return True
        return stream == "chat" and line.startswith(CHATTER_SYSTEM_PREFIX)

    def write_received(self, chunk: ReceivedChunk) -> None:
        if not chunk.data:
            return

        text = self._decode_received(chunk.stream, chunk.data)
        if not text:
            return

        lines = self._complete_received_lines(chunk.stream, text)

        with self.output_lock:
            self.log_file.write(text)
            self.log_file.flush()

            for line in lines:
                # Only the human/main firmware stream owns presentation
                # outcomes. Background BLE 0004 telemetry must not resolve or
                # reject pending USER/ECHO presentation state.
                if chunk.stream != "telemetry":
                    reveal = self._presentation.consume_firmware_line(line)
                    if reveal is not None:
                        sys.stdout.write(reveal + "\n")

                if self._received_line_visible(chunk.stream, line):
                    sys.stdout.write(line)

    def log_input(self, line: str) -> None:
        with self.output_lock:
            self.log_file.write(line + "\n")
            self.log_file.flush()

    def _reveal_sent_presentations(self) -> None:
        reveal = self._presentation.consume_sent_on_disconnect()
        if not reveal:
            return
        with self.output_lock:
            for line in reveal:
                sys.stdout.write(line + "\n")
            sys.stdout.flush()

    def _connect(self) -> bool:
        if self.connection_paused.is_set():
            return False

        transport = self._current_transport()
        if not transport.connect():
            return False

        if self.connection_paused.is_set() or transport is not self._current_transport():
            transport.disconnect()
            return False

        if isinstance(transport, SerialTransport):
            try:
                transport.write(encode_line(CHATTER_ID_COMMAND, self.line_ending))
            except (TransportError, OSError):
                transport.disconnect()
                return False

        self._reset_received_decoders()
        self.connected_event.set()
        self.write_output(f"\n[connected: {transport.description}]\n\n")
        return True

    def _disconnect(self) -> None:
        self.connected_event.clear()
        self._current_transport().disconnect()
        self._reveal_sent_presentations()
        self._reset_received_decoders()

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
                self._reveal_sent_presentations()
                self._reset_received_decoders()
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
                        self._presentation.mark_sent(line)
                        break
                    except (TransportError, OSError):
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

    def _submit_interactive_line(self, line: str) -> None:
        """Log one accepted line and choose command or pending-payload presentation."""
        self.log_input(line)

        command = recognized_chatter_command(line)
        if command is not None:
            self._write_console_only(line + "\n")
            if command == CHATTER_HELP_COMMAND:
                self._show_full_help()
            elif not self.send_line(line):
                self.write_output("[Chatter command was not queued]\n")
            return

        if line == "":
            self.send_line(line)
            return

        if not self._presentation.submit_payload(line):
            self._write_console_only(line + "\n")
            self.write_output(
                "[serialterminal] pending presentation queue full; line not sent\n"
            )
            return

        if not self.send_line(line):
            self._presentation.cancel_unsent_payload(line)
            self._write_console_only(line + "\n")
            self.write_output("[serialterminal] line was not queued\n")

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

        add_control("1", "output_chat")
        add_control("2", "output_telemetry")
        add_control("3", "output_both")
        add_control("c", "output_chat")
        add_control("t", "output_telemetry")
        add_control("b", "output_both")
        add_control("e", "echo")
        add_control("d", "device")
        add_control("s", "scanner")
        add_control("i", "info")
        add_control("?", "help")

        @bindings.add("c-c", eager=True)
        def _quit(event) -> None:
            event.app.exit(exception=KeyboardInterrupt)

        return bindings

    def _make_prompt_session(self) -> PromptSession:
        return PromptSession(
            key_bindings=self._build_key_bindings(),
            erase_when_done=True,
        )

    def _set_view_mode(self, mode: str) -> None:
        # Retained as an internal compatibility helper for old callers/tests;
        # normal UI no longer exposes a local VIEW selector.
        self.view_mode = mode

    def _print_status(self) -> None:
        transport = self._current_transport()
        streams = ", ".join(transport.stream_capabilities)
        self.write_output(
            "\n[status]\n"
            f"  connected : {'yes' if self.connected_event.is_set() else 'no'}\n"
            f"  device    : {transport.description}\n"
            f"  device key: {transport.device_key}\n"
            f"  streams   : {streams}\n"
            "  telemetry : BLE 0004 is background/transcript-only\n"
            "\n"
        )

    def _print_hotkey_help(self) -> None:
        self.write_output(
            "\n[serialterminal hotkeys]\n"
            "  BLE 0004 telemetry is background/transcript-only; normal console follows 0003\n"
            "  /chat /tele /both /echo /reboot are sent unchanged to Chatter\n"
            "  /id requests the canonical Chatter node identity\n"
            "  /help shows this list and requests Chatter /help\n"
            "  Ctrl+C       quit immediately\n"
            "  Ctrl+T 1/c   Chatter human console: CHAT\n"
            "  Ctrl+T 2/t   Chatter human console: TELEMETRY\n"
            "  Ctrl+T 3/b   Chatter human console: BOTH\n"
            "  Ctrl+T e     Chatter echo mode toggle\n"
            "  Ctrl+T d     device chooser\n"
            "  Ctrl+T s     Bluetooth capability scanner\n"
            "  Ctrl+T i     connection/status\n"
            "  Ctrl+T ?     full help (this list + Chatter /help)\n"
            "\n"
        )

    def _show_full_help(self) -> None:
        self._print_hotkey_help()
        if not self.send_line(CHATTER_HELP_COMMAND):
            self.write_output("[Chatter help request was not queued]\n\n")

    def _change_device(self) -> None:
        if self.device_chooser is None:
            self.write_output("\n[device chooser is not available]\n\n")
            return

        old_transport = self._current_transport()
        self.connection_paused.set()
        self.connected_event.clear()
        old_transport.disconnect()
        self._reveal_sent_presentations()
        self._reset_received_decoders()

        try:
            new_transport = self.device_chooser()
        except KeyboardInterrupt:
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

    def _run_bluetooth_scanner(self) -> None:
        transport = self._current_transport()
        self.connection_paused.set()
        self.connected_event.clear()
        transport.disconnect()
        self._reveal_sent_presentations()
        self._reset_received_decoders()

        self.write_output(
            "\n[Bluetooth scanner: current connection paused]\n"
            "[the same locked target will be retried when scanner exits]\n\n"
        )

        try:
            from .bluetooth_scanner import run_interactive_scanner

            run_interactive_scanner()
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            self.write_output(f"\n[Bluetooth scanner failed: {exc}]\n\n")
        finally:
            self.connection_paused.clear()
            self.write_output("\n[Bluetooth scanner closed; reconnecting target]\n\n")

    def _handle_control(self, action: str) -> None:
        if action in {"chat", "telemetry", "both"}:
            self._set_view_mode(action)
            return
        if action in CHATTER_OUTPUT_MODE_COMMANDS:
            self.send_line(CHATTER_OUTPUT_MODE_COMMANDS[action])
            return
        if action == "device":
            self._change_device()
            return
        if action == "scanner":
            self._run_bluetooth_scanner()
            return
        if action == "echo":
            self.send_line(CHATTER_ECHO_TOGGLE)
            return
        if action == "info":
            self._print_status()
            return
        if action == "help":
            self._show_full_help()
            return

    def run(self) -> None:
        rx = threading.Thread(target=self.rx_loop, daemon=True)
        tx = threading.Thread(target=self.tx_loop, daemon=True)
        rx.start()
        tx.start()

        self.write_output("serialterminal\n")
        self.write_output("Type /help or press Ctrl+T ? for full help.\n")
        self.write_output("Ctrl+C exits immediately.\n")
        self.write_output("Commands are sent only after Enter and survive reconnects.\n")
        self.write_output(f"Log: {self.log_path}\n\n")

        prompt = self._make_prompt_session()
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
                    self._submit_interactive_line(result)
        except KeyboardInterrupt:
            self.write_output("\n[exit]\n")
        finally:
            self.stop_event.set()
            self.connection_paused.clear()
            self._reveal_sent_presentations()
            rx.join(timeout=1.0)
            tx.join(timeout=1.0)
            current = self._current_transport()
            current.close()
            with self.output_lock:
                self.log_file.flush()
                self.log_file.close()
