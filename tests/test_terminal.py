import serialterminal.terminal as terminal_module
from serialterminal.terminal import (
    CHATTER_ECHO_TOGGLE,
    CHATTER_HELP_COMMAND,
    CHATTER_OUTPUT_MODE_COMMANDS,
    TerminalSession,
    encode_line,
)
from serialterminal.transports.base import ReceivedChunk, Transport


class DummyTransport(Transport):
    @property
    def is_connected(self):
        return False

    @property
    def description(self):
        return "dummy"

    def connect(self):
        return False

    def disconnect(self):
        pass

    def read(self, size=512):
        return b""

    def write(self, data):
        pass


class DummyBleLikeTransport(DummyTransport):
    @property
    def stream_capabilities(self):
        return ("chat", "telemetry")


class FakeStdout:
    def __init__(self):
        self.writes = []
        self.flush_count = 0

    def write(self, text):
        self.writes.append(text)
        return len(text)

    def flush(self):
        self.flush_count += 1


def test_stream_visibility_and_hotkeys(tmp_path):
    session = TerminalSession(
        DummyBleLikeTransport(),
        log_path=tmp_path / "terminal.log",
    )
    try:
        assert session.view_mode == "chat"
        assert session._received_visible("chat")
        assert not session._received_visible("telemetry")
        assert session._received_visible("main")
        assert len(session._build_key_bindings().bindings) == 12

        # Legacy internal view switching remains available for compatibility,
        # but normal keybindings no longer expose it.
        session.view_mode = "telemetry"
        session.write_received(ReceivedChunk("chat", b"hidden chat\n"))
        assert "hidden chat" in (tmp_path / "terminal.log").read_text()
    finally:
        session.log_file.close()


def test_system_lines_bypass_local_telemetry_view(tmp_path, monkeypatch):
    fake_stdout = FakeStdout()
    monkeypatch.setattr(terminal_module.sys, "stdout", fake_stdout)

    log_path = tmp_path / "terminal.log"
    session = TerminalSession(DummyBleLikeTransport(), log_path=log_path)
    try:
        session.view_mode = "telemetry"

        session.write_received(ReceivedChunk("chat", b"> hidden\n[SY"))
        assert "".join(fake_stdout.writes) == ""

        session.write_received(
            ReceivedChunk(
                "chat",
                b"S] RADIO FATAL init (-2), rebooting\n< hidden too\n",
            )
        )

        assert "".join(fake_stdout.writes) == (
            "[SYS] RADIO FATAL init (-2), rebooting\n"
        )

        transcript = log_path.read_text()
        assert "> hidden\n" in transcript
        assert "< hidden too\n" in transcript
        assert "[SYS] RADIO FATAL init (-2), rebooting\n" in transcript
    finally:
        session.log_file.close()


def test_view_hotkeys_do_not_queue_chatter_commands(tmp_path):
    session = TerminalSession(
        DummyBleLikeTransport(),
        log_path=tmp_path / "terminal.log",
    )
    try:
        for mode in ("chat", "telemetry", "both"):
            session._handle_control(mode)
            assert session.view_mode == mode
            assert session.outgoing.empty()
    finally:
        session.log_file.close()


def test_device_output_hotkeys_queue_matching_chatter_commands(tmp_path):
    session = TerminalSession(
        DummyBleLikeTransport(),
        log_path=tmp_path / "terminal.log",
    )
    try:
        session.view_mode = "chat"
        for action in ("output_chat", "output_telemetry", "output_both"):
            session._handle_control(action)
            assert session.view_mode == "chat"
            assert session.outgoing.get_nowait() == CHATTER_OUTPUT_MODE_COMMANDS[action]

        transcript = (tmp_path / "terminal.log").read_text()
        assert "Chatter output" not in transcript
        assert "queued" not in transcript
    finally:
        session.log_file.close()


def test_echo_hotkey_queues_chatter_control_sequence(tmp_path):
    session = TerminalSession(
        DummyBleLikeTransport(),
        log_path=tmp_path / "terminal.log",
    )
    try:
        session._handle_control("echo")
        assert session.outgoing.get_nowait() == CHATTER_ECHO_TOGGLE
        transcript = (tmp_path / "terminal.log").read_text()
        assert "Chatter echo toggle queued" not in transcript
    finally:
        session.log_file.close()


def test_full_help_prints_local_hotkeys_before_requesting_controller(tmp_path):
    session = TerminalSession(
        DummyBleLikeTransport(),
        log_path=tmp_path / "terminal.log",
    )
    order = []
    try:
        session._print_hotkey_help = lambda: order.append("local")

        def fake_send_line(line):
            order.append(line)
            return True

        session.send_line = fake_send_line
        session._show_full_help()
        assert order == ["local", CHATTER_HELP_COMMAND]
    finally:
        session.log_file.close()


def test_help_hotkey_is_equivalent_to_full_help(tmp_path):
    session = TerminalSession(
        DummyBleLikeTransport(),
        log_path=tmp_path / "terminal.log",
    )
    try:
        session._handle_control("help")
        assert session.outgoing.get_nowait() == CHATTER_HELP_COMMAND
        transcript = (tmp_path / "terminal.log").read_text()
        assert "[serialterminal hotkeys]" in transcript
        assert "/chat /tele /both /echo /reboot" in transcript
        assert "background/transcript-only" in transcript
        assert "full help (this list + Chatter /help)" in transcript
    finally:
        session.log_file.close()


def test_chat_prompt_erases_committed_console_echo(tmp_path, monkeypatch):
    captured = {}

    class FakePromptSession:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(terminal_module, "PromptSession", FakePromptSession)

    session = TerminalSession(
        DummyBleLikeTransport(),
        log_path=tmp_path / "terminal.log",
    )
    try:
        prompt = session._make_prompt_session()
        assert isinstance(prompt, FakePromptSession)
        assert captured["erase_when_done"] is True
        assert captured["key_bindings"] is not None
    finally:
        session.log_file.close()


def test_input_is_still_retained_in_transcript(tmp_path):
    log_path = tmp_path / "terminal.log"
    session = TerminalSession(
        DummyBleLikeTransport(),
        log_path=log_path,
    )
    try:
        session.log_input("hello over radio")
        assert "hello over radio\n" in log_path.read_text()
    finally:
        session.log_file.close()


def test_scanner_keeps_terminal_reconnect_paused(tmp_path, monkeypatch):
    from serialterminal import bluetooth_scanner

    observed = []
    session = TerminalSession(
        DummyBleLikeTransport(),
        log_path=tmp_path / "terminal.log",
    )

    def fake_scanner():
        observed.append(session.connection_paused.is_set())
        observed.append(session.connected_event.is_set())

    monkeypatch.setattr(
        bluetooth_scanner,
        "run_interactive_scanner",
        fake_scanner,
    )

    try:
        session.connected_event.set()
        session._run_bluetooth_scanner()
        assert observed == [True, False]
        assert not session.connection_paused.is_set()
        assert not session.connected_event.is_set()
    finally:
        session.log_file.close()


def test_received_ble_chunks_are_committed_as_complete_lines(tmp_path, monkeypatch):
    fake_stdout = FakeStdout()
    monkeypatch.setattr(terminal_module.sys, "stdout", fake_stdout)

    log_path = tmp_path / "terminal.log"
    session = TerminalSession(
        DummyBleLikeTransport(),
        log_path=log_path,
    )
    try:
        session.write_received(ReceivedChunk("telemetry", b"TX HEARTBEAT seq=18"))
        assert fake_stdout.writes == []

        session.write_received(ReceivedChunk("telemetry", b" frame=12B\n"))

        assert fake_stdout.writes == []
        assert "TX HEARTBEAT seq=18 frame=12B\n" in log_path.read_text()
        assert fake_stdout.flush_count == 0
    finally:
        session.log_file.close()


def test_received_utf8_survives_ble_notification_boundary(tmp_path, monkeypatch):
    fake_stdout = FakeStdout()
    monkeypatch.setattr(terminal_module.sys, "stdout", fake_stdout)

    session = TerminalSession(
        DummyBleLikeTransport(),
        log_path=tmp_path / "terminal.log",
    )
    try:
        text = "[ME] апршщдзжзжзхэ\n"
        encoded = text.encode("utf-8")

        prefix = "[ME] апршщдз".encode("utf-8")
        cut = len(prefix) + 1
        session.write_received(ReceivedChunk("chat", encoded[:cut]))
        session.write_received(ReceivedChunk("chat", encoded[cut:]))

        rendered = "".join(fake_stdout.writes)
        assert rendered == text
        assert "�" not in rendered

        transcript = (tmp_path / "terminal.log").read_text()
        assert text in transcript
        assert "�" not in transcript
    finally:
        session.log_file.close()


def test_utf8_decoder_state_is_separate_per_ble_stream(tmp_path, monkeypatch):
    fake_stdout = FakeStdout()
    monkeypatch.setattr(terminal_module.sys, "stdout", fake_stdout)

    log_path = tmp_path / "terminal.log"
    session = TerminalSession(
        DummyBleLikeTransport(),
        log_path=log_path,
    )
    try:
        letter = "ж".encode("utf-8")

        session.write_received(ReceivedChunk("chat", letter[:1]))
        session.write_received(ReceivedChunk("telemetry", b"T\n"))
        session.write_received(ReceivedChunk("chat", letter[1:] + b"\n"))

        assert "".join(fake_stdout.writes) == "ж\n"
        assert "�" not in "".join(fake_stdout.writes)
        assert "T\n" in log_path.read_text()
    finally:
        session.log_file.close()


def test_trimmed_command_is_visible_and_queued_unchanged(tmp_path, monkeypatch):
    fake_stdout = FakeStdout()
    monkeypatch.setattr(terminal_module.sys, "stdout", fake_stdout)

    session = TerminalSession(DummyBleLikeTransport(), log_path=tmp_path / "terminal.log")
    try:
        session._submit_interactive_line("  /reboot  ")

        assert "".join(fake_stdout.writes) == "  /reboot  \n"
        assert session.outgoing.get_nowait() == "  /reboot  "
        assert session._presentation.pending_count() == 0
        assert "  /reboot  \n" in (tmp_path / "terminal.log").read_text()
    finally:
        session.log_file.close()


def test_unknown_command_like_text_remains_original_pending_payload(tmp_path, monkeypatch):
    fake_stdout = FakeStdout()
    monkeypatch.setattr(terminal_module.sys, "stdout", fake_stdout)

    session = TerminalSession(DummyBleLikeTransport(), log_path=tmp_path / "terminal.log")
    try:
        line = "  /echo x  "
        session._submit_interactive_line(line)

        assert fake_stdout.writes == []
        assert session.outgoing.get_nowait() == line
        assert session._presentation.pending_count() == 1
        assert line + "\n" in (tmp_path / "terminal.log").read_text()
    finally:
        session.log_file.close()


def test_successful_payload_appears_once_as_firmware_marker(tmp_path, monkeypatch):
    fake_stdout = FakeStdout()
    monkeypatch.setattr(terminal_module.sys, "stdout", fake_stdout)

    log_path = tmp_path / "terminal.log"
    session = TerminalSession(DummyBleLikeTransport(), log_path=log_path)
    try:
        session._submit_interactive_line("hello")
        assert fake_stdout.writes == []
        assert session.outgoing.get_nowait() == "hello"
        session._presentation.mark_sent("hello")

        session.write_received(ReceivedChunk("chat", b"> hello\n"))

        assert "".join(fake_stdout.writes) == "> hello\n"
        assert session._presentation.pending_count() == 0
        transcript = log_path.read_text()
        assert transcript.count("hello\n") == 2
    finally:
        session.log_file.close()


def test_rejected_payload_is_revealed_plain_before_firmware_failure(tmp_path, monkeypatch):
    fake_stdout = FakeStdout()
    monkeypatch.setattr(terminal_module.sys, "stdout", fake_stdout)

    log_path = tmp_path / "terminal.log"
    session = TerminalSession(DummyBleLikeTransport(), log_path=log_path)
    try:
        session._submit_interactive_line("hello")
        assert session.outgoing.get_nowait() == "hello"
        session._presentation.mark_sent("hello")

        session.write_received(
            ReceivedChunk(
                "chat",
                b"[SYS] RADIO UNAVAILABLE, message not sent\n",
            )
        )

        assert "".join(fake_stdout.writes) == (
            "hello\n[SYS] RADIO UNAVAILABLE, message not sent\n"
        )
        assert session._presentation.pending_count() == 0
        transcript = log_path.read_text()
        assert transcript.count("hello\n") == 1
        assert "[SYS] RADIO UNAVAILABLE, message not sent\n" in transcript
    finally:
        session.log_file.close()


def test_split_rejection_waits_for_complete_line_then_reveals_payload(tmp_path, monkeypatch):
    fake_stdout = FakeStdout()
    monkeypatch.setattr(terminal_module.sys, "stdout", fake_stdout)

    session = TerminalSession(DummyBleLikeTransport(), log_path=tmp_path / "terminal.log")
    try:
        session._submit_interactive_line("hello")
        assert session.outgoing.get_nowait() == "hello"
        session._presentation.mark_sent("hello")

        session.write_received(ReceivedChunk("chat", b"[SYS] RADIO UNAV"))
        assert fake_stdout.writes == []

        session.write_received(
            ReceivedChunk("chat", b"AILABLE, message not sent\n")
        )
        assert "".join(fake_stdout.writes) == (
            "hello\n[SYS] RADIO UNAVAILABLE, message not sent\n"
        )
    finally:
        session.log_file.close()


def test_interleaved_telemetry_does_not_duplicate_pending_payload(tmp_path, monkeypatch):
    fake_stdout = FakeStdout()
    monkeypatch.setattr(terminal_module.sys, "stdout", fake_stdout)

    log_path = tmp_path / "terminal.log"
    session = TerminalSession(DummyBleLikeTransport(), log_path=log_path)
    try:
        session._submit_interactive_line("hello")
        assert session.outgoing.get_nowait() == "hello"
        session._presentation.mark_sent("hello")

        session.write_received(ReceivedChunk("telemetry", b"TX USER seq=7 OK\n"))
        session.write_received(ReceivedChunk("chat", b"> hello\n"))

        assert "".join(fake_stdout.writes) == "> hello\n"
        assert "TX USER seq=7 OK\n" in log_path.read_text()
        assert session._presentation.pending_count() == 0
    finally:
        session.log_file.close()


def test_disconnect_reveals_sent_pending_payload_without_relogging(tmp_path, monkeypatch):
    fake_stdout = FakeStdout()
    monkeypatch.setattr(terminal_module.sys, "stdout", fake_stdout)

    log_path = tmp_path / "terminal.log"
    session = TerminalSession(DummyBleLikeTransport(), log_path=log_path)
    try:
        session._submit_interactive_line("hello")
        assert session.outgoing.get_nowait() == "hello"
        session._presentation.mark_sent("hello")

        session._reveal_sent_presentations()

        assert "".join(fake_stdout.writes) == "hello\n"
        assert session._presentation.pending_count() == 0
        assert log_path.read_text().count("hello\n") == 1
    finally:
        session.log_file.close()
