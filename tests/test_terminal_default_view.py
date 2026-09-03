from serialterminal.terminal import TerminalSession
from serialterminal.transports.base import Transport


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


def test_ble_session_defaults_to_human_console_only(tmp_path):
    session = TerminalSession(
        DummyBleLikeTransport(),
        log_path=tmp_path / "terminal.log",
    )
    try:
        assert session.view_mode == "chat"
        assert session._received_visible("chat")
        assert not session._received_visible("telemetry")
        assert session._received_visible("main")
    finally:
        session.log_file.close()
