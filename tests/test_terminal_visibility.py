import serialterminal.terminal as terminal_module
from serialterminal.profiles.chatter import CHATTER_PROFILE
from serialterminal.terminal import TerminalSession
from serialterminal.transports.base import ReceivedChunk, Transport


class DummyBleLikeTransport(Transport):
    @property
    def is_connected(self):
        return False

    @property
    def description(self):
        return "visibility-test"

    @property
    def stream_capabilities(self):
        return ("chat", "telemetry")

    def connect(self):
        return False

    def disconnect(self):
        pass

    def read(self, size=512):
        return b""

    def write(self, data):
        pass


class FakeStdout:
    def __init__(self):
        self.writes = []

    def write(self, text):
        self.writes.append(text)
        return len(text)

    def flush(self):
        pass


def _session(tmp_path):
    return TerminalSession(
        DummyBleLikeTransport(),
        profile=CHATTER_PROFILE,
        log_path=tmp_path / "terminal.log",
    )


def test_console_stream_visibility_does_not_depend_on_line_prefix(tmp_path):
    session = _session(tmp_path)
    try:
        assert session._received_line_visible("chat", "ordinary output\n")
        assert session._received_line_visible("chat", "[SYS] controller status\n")
    finally:
        session.log_file.close()


def test_background_stream_stays_hidden_even_for_system_like_text(tmp_path):
    session = _session(tmp_path)
    try:
        assert not session._received_line_visible("telemetry", "ordinary telemetry\n")
        assert not session._received_line_visible(
            "telemetry",
            "[SYS] controller status\n",
        )
    finally:
        session.log_file.close()


def test_background_system_line_is_transcript_only(tmp_path, monkeypatch):
    fake_stdout = FakeStdout()
    monkeypatch.setattr(terminal_module.sys, "stdout", fake_stdout)

    log_path = tmp_path / "terminal.log"
    session = _session(tmp_path)
    try:
        session.write_received(
            ReceivedChunk("telemetry", b"[SYS] background-only status\n")
        )
        session.write_received(
            ReceivedChunk("chat", b"[SYS] console-visible status\n")
        )

        assert "".join(fake_stdout.writes) == "[SYS] console-visible status\n"
        transcript = log_path.read_text()
        assert "[SYS] background-only status\n" in transcript
        assert "[SYS] console-visible status\n" in transcript
    finally:
        session.log_file.close()
