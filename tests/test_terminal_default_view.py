from serialterminal.profiles.chatter import CHATTER_PROFILE
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


def test_ble_session_uses_profile_console_streams(tmp_path):
    session = TerminalSession(
        DummyBleLikeTransport(),
        log_path=tmp_path / "terminal.log",
        profile=CHATTER_PROFILE,
    )
    try:
        assert not hasattr(session, "view_mode")
        assert session._received_visible("chat")
        assert not session._received_visible("telemetry")
        assert session._received_visible("main")
    finally:
        session.log_file.close()

def test_chatter_local_commands_are_echoed_and_queued_uniformly(
    tmp_path, capsys, monkeypatch
):
    session = TerminalSession(
        DummyBleLikeTransport(),
        log_path=tmp_path / "terminal.log",
        profile=CHATTER_PROFILE,
    )
    sent = []
    monkeypatch.setattr(
        session,
        "send_line",
        lambda line: sent.append(line) or True,
    )
    monkeypatch.setattr(
        session,
        "_show_full_help",
        lambda: (_ for _ in ()).throw(
            AssertionError("typed /help must not expand SerialTerminal help")
        ),
    )
    try:
        session._submit_interactive_line("/help")
        session._submit_interactive_line("/version")
        session._submit_interactive_line("/firmware")
        session._submit_interactive_line("/power")
        session._submit_interactive_line("/power 10")
        session._submit_interactive_line("/config reset")

        assert capsys.readouterr().out == (
            "/help\n/version\n/firmware\n"
            "/power\n/power 10\n/config reset\n"
        )
        assert sent == [
            "/help",
            "/version",
            "/firmware",
            "/power",
            "/power 10",
            "/config reset",
        ]
        assert session._presentation is not None
        assert session._presentation.pending_count() == 0
    finally:
        session.log_file.close()
