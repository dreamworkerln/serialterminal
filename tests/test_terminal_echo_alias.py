from serialterminal.terminal import (
    CHATTER_ECHO_COMMAND,
    CHATTER_ECHO_TOGGLE,
    TerminalSession,
)
from serialterminal.transports.base import Transport


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


def test_typed_echo_alias_queues_raw_chatter_toggle(tmp_path):
    session = TerminalSession(
        DummyTransport(),
        log_path=tmp_path / "terminal.log",
    )
    try:
        assert session._handle_typed_command(CHATTER_ECHO_COMMAND)
        assert session.outgoing.get_nowait() == CHATTER_ECHO_TOGGLE
        assert "Chatter echo toggle queued" in (
            tmp_path / "terminal.log"
        ).read_text()
    finally:
        session.log_file.close()


def test_unknown_typed_line_is_not_consumed(tmp_path):
    session = TerminalSession(
        DummyTransport(),
        log_path=tmp_path / "terminal.log",
    )
    try:
        assert not session._handle_typed_command("ordinary USER text")
        assert session.outgoing.empty()
    finally:
        session.log_file.close()
