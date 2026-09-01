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

from .transports.base import ReceivedChunk, Transport, TransportError


CHATTER_ECHO_TOGGLE = "\x14e"
CHATTER_OUTPUT_MODE_COMMANDS = {
    "output_chat": "\x141",
    "output_telemetry": "\x142",
    "output_both": "\x143",
}
CHATTER_HELP_COMMAND = "/help"
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
        self._received_decoders = {}
        self._hidden_chat_line_buffer = ""

        # BLE defaults to BOTH so Chatter /chat /tele /both has the same
        # user-visible meaning as in a standard Android NUS terminal. The
        # Ctrl+T 1/2/3 view remains an optional local display filter.
        # Plain Serial/SPP use stream `main`, which is always visible because
        # their output is physically combined.
        self.view_mode = "both"

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

    def _decode_received(self, stream: str, data: bytes) -> str:
        """Decode one logical stream without breaking UTF-8 at chunk boundaries."""
        with self.decode_lock:
            decoder = self._received_decoders.get(stream)
            if decoder is None:
                decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
                self._received_decoders[stream] = decoder
            return decoder.decode(data, final=False)

    def _reset_received_decoders(self) -> None:
        """Discard incomplete characters when a transport connection changes."""
        with self.decode_lock:
            self._received_decoders.clear()
            self._hidden_chat_line_buffer = ""

    def _hidden_chat_system_text(self, stream: str, text: str) -> str:
        """Return complete [SYS] lines from a CHAT stream hidden by local view."""
        if stream != "chat" or not text:
            return ""

        with self.decode_lock:
            combined = self._hidden_chat_line_buffer + text
            lines = combined.splitlines(keepends=True)

            if lines and not lines[-1].endswith(("\n", "\r")):
                self._hidden_chat_line_buffer = lines.pop()
            else:
                self._hidden_chat_line_buffer = ""

        return "".join(
            line for line in lines if line.startswith(CHATTER_SYSTEM_PREFIX)
        )

    def write_received(self, chunk: ReceivedChunk) -> None:
        if not chunk.data:
            return

        text = self._decode_received(chunk.stream, chunk.data)
        if not text:
            return

        if self._received_visible(chunk.stream):
            visible_text = text
        else:
            # SYSTEM is intentionally higher priority than the local VIEW
            # filter. Firmware sends it on BLE primary/chat; inspect complete
            # lines so arbitrary BLE notification boundaries are harmless.
            visible_text = self._hidden_chat_system_text(chunk.stream, text)

        with self.output_lock:
            # Always retain all logical streams in the transcript, even when
            # one is hidden from the current screen view.
            self.log_file.write(text)
            self.log_file.flush()

            if visible_text:
                # Do not flush stdout for every transport chunk. BLE firmware
                # intentionally emits notifications in small MTU-safe pieces.
                # prompt_toolkit.patch_stdout buffers those pieces until a
                # newline so it can redraw the input prompt exactly once.
                sys.stdout.write(visible_text)

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

        # A reconnect is a new byte-stream boundary. Never let a partial UTF-8
        # sequence from the old link combine with bytes from the new link.
        self._reset_received_decoders()
        self.connected_event.set()
        self.write_output(f"\n[connected: {transport.description}]\n\n")
        return True

    def _disconnect(self) -> None:
        self.connected_event.clear()
        self._current_transport().disconnect()
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

        # Local terminal view. These never send bytes to the device.
        add_control("1", "chat")
        add_control("2", "telemetry")
        add_control("3", "both")

        # Chatter device controls. The user-facing keys are independent from
        # the stable raw Chatter opcodes (0x14 + '1'/'2'/'3').
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
        """Create the interactive chat prompt without committed local echo.

        Text remains visible while the user edits it. After Enter (or a local
        Ctrl+T action) prompt_toolkit removes that rendered prompt from the
        terminal and the next prompt is drawn normally. Menus use ordinary
        input() outside this PromptSession and keep their normal terminal echo.
        """
        return PromptSession(
            key_bindings=self._build_key_bindings(),
            erase_when_done=True,
        )

    def _set_view_mode(self, mode: str) -> None:
        transport = self._current_transport()
        if set(transport.stream_capabilities) == {"main"}:
            self.write_output(
                "\n[view: USB/Serial/SPP is physically combined; "
                "use Ctrl+T c/t/b to change Chatter device output]\n\n"
            )
            return

        with self.decode_lock:
            # Do not carry a partial line across a local visibility change.
            self._hidden_chat_line_buffer = ""

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
            "\n[serialterminal hotkeys]\n"
            "  VIEW default: BOTH; Ctrl+T 1/2/3 are local display filters only\n"
            "  /chat /tele /both /echo are sent unchanged to Chatter\n"
            "  Ctrl+C       quit immediately\n"
            "  Ctrl+T 1     local CHAT view (BLE)\n"
            "  Ctrl+T 2     local TELEMETRY view (BLE)\n"
            "  Ctrl+T 3     local BOTH view (BLE)\n"
            "  Ctrl+T c     Chatter device output: CHAT\n"
            "  Ctrl+T t     Chatter device output: TELEMETRY\n"
            "  Ctrl+T b     Chatter device output: BOTH\n"
            "  Ctrl+T e     Chatter echo mode toggle\n"
            "  Ctrl+T d     device chooser\n"
            "  Ctrl+T s     Bluetooth capability scanner\n"
            "  Ctrl+T i     connection/status\n"
            "  Ctrl+T ?     full help (this list + Chatter /help)\n"
            "\n"
        )

    def _show_full_help(self) -> None:
        # Local controls are useful immediately, even if the controller is
        # disconnected. Then request the controller-owned part through the
        # ordinary reconnect-safe line queue.
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
        self._reset_received_decoders()

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

    def _run_bluetooth_scanner(self) -> None:
        """Temporarily release the active target and run the interactive prober."""
        transport = self._current_transport()
        self.connection_paused.set()
        self.connected_event.clear()
        transport.disconnect()
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
            mode = action.removeprefix("output_").upper()
            self.write_output(f"\n[Chatter output {mode} queued]\n\n")
            return
        if action == "device":
            self._change_device()
            return
        if action == "scanner":
            self._run_bluetooth_scanner()
            return
        if action == "echo":
            # Chatter expects raw Ctrl+T,e. Send those bytes through the normal
            # reconnect-safe line queue, so the same hotkey works on USB Serial,
            # BLE NUS and Bluetooth SPP transports.
            self.send_line(CHATTER_ECHO_TOGGLE)
            self.write_output("\n[Chatter echo toggle queued]\n\n")
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
                    line = result
                    # Keep the full transcript even though the accepted prompt
                    # is erased from the interactive console.
                    self.log_input(line)
                    if line.strip() == CHATTER_HELP_COMMAND:
                        self._show_full_help()
                    else:
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