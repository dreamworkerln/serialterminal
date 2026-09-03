import serialterminal.terminal as terminal_module
from serialterminal.terminal import TerminalSession
from serialterminal.transports.base import ReceivedChunk, Transport


class DummyBleLikeTransport(Transport):
    @property
    def is_connected(self):
        return False

    @property
    def description(self):
        return "dummy"

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


def test_background_telemetry_cannot_resolve_pending_presentation(
    tmp_path,
    monkeypatch,
):
    fake_stdout = FakeStdout()
    monkeypatch.setattr(terminal_module.sys, "stdout", fake_stdout)

    log_path = tmp_path / "terminal.log"
    session = TerminalSession(DummyBleLikeTransport(), log_path=log_path)
    try:
        session._submit_interactive_line("hello")
        assert session.outgoing.get_nowait() == "hello"
        session._presentation.mark_sent("hello")

        # This text matches a presentation failure prefix, but it arrived on
        # BLE 0004 and therefore must remain machine data only.
        session.write_received(
            ReceivedChunk("telemetry", b"TX FATAL state=-5\n")
        )

        assert fake_stdout.writes == []
        assert session._presentation.pending_count() == 1
        assert "TX FATAL state=-5\n" in log_path.read_text()

        session.write_received(ReceivedChunk("chat", b"> hello\n"))
        assert "".join(fake_stdout.writes) == "> hello\n"
        assert session._presentation.pending_count() == 0
    finally:
        session.log_file.close()
