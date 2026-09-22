from __future__ import annotations

import codecs
from dataclasses import dataclass
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable

from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.patch_stdout import patch_stdout

from .runlog import console_log_path, format_console_record
from .profiles import (
    GENERIC_PROFILE,
    ProfileAction,
    SendBytes,
    SendLine,
    TerminalProfile,
)
from .session import ManagedSession, SessionClosedError, encode_line
from .transports.base import ReceivedChunk, Transport
from .transports.serial import SerialTransport


@dataclass(frozen=True)
class _ControlRequest:
    action: str
    buffered_line: str


class TerminalSession(ManagedSession):
    """Human line-oriented frontend over the shared managed session core."""

    def __init__(
        self,
        transport: Transport,
        log_path: str | Path = "serialterminal.log",
        line_ending: str = "\n",
        reconnect_delay: float = 0.5,
        device_chooser: Callable[[], Transport | None] | None = None,
        profile: TerminalProfile = GENERIC_PROFILE,
    ):
        self.profile = profile
        super().__init__(
            transport,
            line_ending=line_ending,
            reconnect_delay=reconnect_delay,
            connect_preamble=self._human_connect_preamble,
            line_notifier=self._record_console_output_line,
        )
        self.log_path = Path(log_path)
        self.console_path = console_log_path(self.log_path)
        self.console_session = "s1"
        self.device_chooser = device_chooser

        self.output_lock = threading.Lock()
        self.decode_lock = threading.Lock()
        self._presentation = self.profile.make_presentation()
        self._received_decoders = {}
        self._received_line_buffers = {}

        self.log_file = self.log_path.open("a", encoding="utf-8", buffering=1)
        # Human frontend сохраняет исторический transcript .log, а рядом создаёт
        # общий с agent timestamped console view для сопоставимого timing analysis.
        self.console_path.touch(exist_ok=True)
        stamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z")
        self.log_file.write(f"\n===== serialterminal session {stamp} =====\n")
        self.log_file.flush()

    def _profile_action_bytes(self, action: ProfileAction) -> bytes:
        if isinstance(action, SendLine):
            return encode_line(action.text, self.line_ending)
        if isinstance(action, SendBytes):
            return action.data
        raise TypeError(f"unsupported profile action: {type(action)!r}")

    def _human_connect_preamble(self, transport: Transport) -> bytes | None:
        # Human profile preamble выполняется только для Serial; BLE/SPP
        # не получают дополнительную controller-команду при connect.
        if not isinstance(transport, SerialTransport):
            return None
        payload = b"".join(
            self._profile_action_bytes(action)
            for action in self.profile.connect_preamble()
        )
        return payload or None

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

    def _record_console(
        self,
        direction: str,
        text: str,
        *,
        timestamp: float | None = None,
    ) -> None:
        with self.output_lock:
            with self.console_path.open("a", encoding="utf-8", buffering=1) as file:
                file.write(
                    format_console_record(
                        self.console_session,
                        direction,
                        text,
                        timestamp=timestamp,
                    )
                )

    def _record_console_output_line(self, line) -> None:
        if line.stream not in self.profile.human_console_streams():
            return
        self._record_console("<", line.text, timestamp=line.timestamp)

    def _received_visible(self, stream: str) -> bool:
        return stream in self.profile.human_console_streams()

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

    def _received_line_visible(self, stream: str, _line: str) -> bool:
        return self._received_visible(stream)

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
                # Presentation outcomes принадлежат только human-console streams
                # выбранного profile. Background streams остаются transcript-only.
                if (
                    self._presentation is not None
                    and chunk.stream in self.profile.human_console_streams()
                ):
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
        if self._presentation is None:
            return
        reveal = self._presentation.consume_sent_on_disconnect()
        if not reveal:
            return
        with self.output_lock:
            for line in reveal:
                sys.stdout.write(line + "\n")
            sys.stdout.flush()

    # ManagedSession hooks keep reconnect/TX/RX mechanics out of the human UI.
    def on_waiting(self) -> None:
        self.write_output("[waiting for selected device...]\n")

    def on_connected(self, transport: Transport) -> None:
        self._reset_received_decoders()
        self.write_output(f"\n[connected: {transport.description}]\n\n")

    def on_received(self, chunk: ReceivedChunk) -> None:
        self.write_received(chunk)

    def on_disconnected(self, description: str, error: str | None) -> None:
        self._reveal_sent_presentations()
        self._reset_received_decoders()
        self.write_output(f"\n[disconnected: {description}]\n\n")

    def on_tx_written(self, item) -> None:
        if self._presentation is not None and isinstance(item, str):
            self._presentation.mark_sent(str(item))

    def on_send_failed(self, error: str | None) -> None:
        self.write_output("\n[send failed; reconnecting]\n")

    def send_line(self, line: str) -> bool:
        """Queue one complete line; it is never split into per-key writes."""
        try:
            self.queue_line(line)
        except SessionClosedError:
            return False
        self._record_console(">", line)
        return True

    def _queue_profile_action(self, action: ProfileAction) -> bool:
        if isinstance(action, SendLine):
            return self.send_line(action.text)
        if isinstance(action, SendBytes):
            try:
                self.queue_bytes(action.data)
                return True
            except SessionClosedError:
                return False
        raise TypeError(f"unsupported profile action: {type(action)!r}")

    def _submit_interactive_line(self, line: str) -> None:
        """Log one accepted line and choose command or pending-payload presentation."""
        self.log_input(line)

        command = self.profile.recognized_command(line)
        if command is not None:
            self._write_console_only(line + "\n")
            if not self.send_line(line):
                self.write_output("[serialterminal] command was not queued\n")
            return

        if line == "":
            self.send_line(line)
            return

        if self._presentation is None:
            if not self.send_line(line):
                self._write_console_only(line + "\n")
                self.write_output("[serialterminal] line was not queued\n")
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

        for sequence, action in self.profile.human_hotkeys():
            add_control(sequence, action)
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

    def _print_status(self) -> None:
        transport = self._current_transport()
        streams = ", ".join(transport.stream_capabilities)
        self.write_output(
            "\n[status]\n"
            f"  profile   : {self.profile.name}\n"
            f"  connected : {'yes' if self.connected_event.is_set() else 'no'}\n"
            f"  device    : {transport.description}\n"
            f"  device key: {transport.device_key}\n"
            f"  streams   : {streams}\n"
            "\n"
        )

    def _print_hotkey_help(self) -> None:
        lines = [
            "\n[serialterminal hotkeys]",
            f"  profile       {self.profile.name}",
        ]
        lines.extend(f"  {line}" for line in self.profile.human_help_lines())
        lines.extend(
            (
                "  Ctrl+C       quit immediately",
                "  Ctrl+T d     device chooser",
                "  Ctrl+T s     Bluetooth capability scanner",
                "  Ctrl+T i     connection/status",
            )
        )
        if self.profile.device_help_action() is None:
            lines.append("  Ctrl+T ?     SerialTerminal help")
        else:
            lines.append("  Ctrl+T ?     SerialTerminal help + device help")
        self.write_output("\n".join(lines) + "\n\n")

    def _show_full_help(self) -> None:
        self._print_hotkey_help()
        action = self.profile.device_help_action()
        if action is not None and not self._queue_profile_action(action):
            self.write_output("[serialterminal] device help request was not queued\n\n")

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
        profile_action = self.profile.human_actions().get(action)
        if profile_action is not None:
            self._queue_profile_action(profile_action)
            return

        if action == "device":
            self._change_device()
            return
        if action == "scanner":
            self._run_bluetooth_scanner()
            return
        if action == "info":
            self._print_status()
            return
        if action == "help":
            self._show_full_help()
            return

    def run(self) -> None:
        self.start()

        self.write_output("serialterminal\n")
        self.write_output(f"Profile: {self.profile.name}\n")
        self.write_output("Press Ctrl+T ? for SerialTerminal help.\n")
        self.write_output("Ctrl+C exits immediately.\n")
        self.write_output("Input is sent only after Enter and survives reconnects.\n")
        self.write_output(f"Log: {self.log_path}\n")
        self.write_output(f"Console log: {self.console_path}\n\n")

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
            self._reveal_sent_presentations()
            self.stop()
            with self.output_lock:
                self.log_file.flush()
                self.log_file.close()
