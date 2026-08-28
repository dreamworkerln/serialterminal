import serialterminal.terminal as terminal_module
from serialterminal.terminal import TerminalSession, encode_line
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


def test_encode_line():
    assert encode_line("LC") == b"LC\n"
    assert encode_line("LC", "\r\n") == b"LC\r\n"


def test_stream_visibility_and_hotkeys(tmp_path):
    session = TerminalSession(
        DummyBleLikeTransport(),
        log_path=tmp_path / "terminal.log",
    )
    try:
        assert session._received_visible("chat")
        assert not session._received_visible("telemetry")
        session.view_mode = "both"
        assert session._received_visible("chat")
        assert session._received_visible("telemetry")
        assert session._received_visible("main")
        assert len(session._build_key_bindings().bindings) == 7

        session.view_mode = "telemetry"
        session.write_received(ReceivedChunk("chat", b"hidden chat\n"))
        assert "hidden chat" in (tmp_path / "terminal.log").read_text()
    finally:
        session.log_file.close()


def test_received_ble_chunks_do_not_force_stdout_flush(tmp_path, monkeypatch):
    class FakeStdout:
        def __init__(self):
            self.writes = []
            self.flush_count = 0

        def write(self, text):
            self.writes.append(text)
            return len(text)

        def flush(self):
            self.flush_count += 1

    fake_stdout = FakeStdout()
    monkeypatch.setattr(terminal_module.sys, "stdout", fake_stdout)

    session = TerminalSession(
        DummyBleLikeTransport(),
        log_path=tmp_path / "terminal.log",
    )
    try:
        session.view_mode = "both"
        session.write_received(ReceivedChunk("telemetry", b"TX HEARTBEAT seq=18"))
        session.write_received(ReceivedChunk("telemetry", b" frame=12B\n"))

        assert fake_stdout.writes == ["TX HEARTBEAT seq=18", " frame=12B\n"]
        assert fake_stdout.flush_count == 0
    finally:
        session.log_file.close()


def test_received_utf8_survives_ble_notification_boundary(tmp_path, monkeypatch):
    class FakeStdout:
        def __init__(self):
            self.writes = []

        def write(self, text):
            self.writes.append(text)
            return len(text)

        def flush(self):
            pass

    fake_stdout = FakeStdout()
    monkeypatch.setattr(terminal_module.sys, "stdout", fake_stdout)

    session = TerminalSession(
        DummyBleLikeTransport(),
        log_path=tmp_path / "terminal.log",
    )
    try:
        text = "[ME] апршщдзжзжзхэ\n"
        encoded = text.encode("utf-8")

        # Split after only the first byte of a two-byte Cyrillic code point,
        # matching an arbitrary BLE notification/MTU boundary.
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
    class FakeStdout:
        def __init__(self):
            self.writes = []

        def write(self, text):
            self.writes.append(text)
            return len(text)

        def flush(self):
            pass

    fake_stdout = FakeStdout()
    monkeypatch.setattr(terminal_module.sys, "stdout", fake_stdout)

    session = TerminalSession(
        DummyBleLikeTransport(),
        log_path=tmp_path / "terminal.log",
    )
    try:
        session.view_mode = "both"
        letter = "ж".encode("utf-8")

        session.write_received(ReceivedChunk("chat", letter[:1]))
        session.write_received(ReceivedChunk("telemetry", b"T\n"))
        session.write_received(ReceivedChunk("chat", letter[1:] + b"\n"))

        assert "".join(fake_stdout.writes) == "T\nж\n"
        assert "�" not in "".join(fake_stdout.writes)
    finally:
        session.log_file.close()
