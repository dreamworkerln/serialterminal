from serialterminal.presentation import recognized_chatter_command
from serialterminal.terminal import CHATTER_ID_COMMAND, TerminalSession
from serialterminal.transports.base import Transport
from serialterminal.transports.serial import SerialTransport


class FakeSerialTransport(SerialTransport):
    def __init__(self):
        super().__init__(device="/dev/fake")
        self.connected = False
        self.writes = []

    @property
    def description(self):
        return "serial:/dev/fake @ 115200"

    @property
    def is_connected(self):
        return self.connected

    def connect(self):
        self.connected = True
        return True

    def disconnect(self):
        self.connected = False

    def write(self, data):
        self.writes.append(data)


class FakeBluetoothTransport(Transport):
    def __init__(self):
        self.connected = False
        self.writes = []

    @property
    def description(self):
        return "bluetooth fake"

    @property
    def is_connected(self):
        return self.connected

    def connect(self):
        self.connected = True
        return True

    def disconnect(self):
        self.connected = False

    def read(self, size=512):
        return b""

    def write(self, data):
        self.writes.append(data)


def test_id_is_recognized_as_chatter_command():
    assert recognized_chatter_command("/id") == "/id"
    assert recognized_chatter_command("  /id  ") == "/id"


def test_serial_connect_requests_identity_before_user_tx_gate(tmp_path):
    transport = FakeSerialTransport()
    session = TerminalSession(transport, log_path=tmp_path / "terminal.log")
    try:
        assert not session.connected_event.is_set()
        assert session._connect()
        assert session.connected_event.is_set()
        assert transport.writes == [(CHATTER_ID_COMMAND + "\n").encode("utf-8")]
        assert session.outgoing.empty()
    finally:
        session.log_file.close()


def test_bluetooth_connect_does_not_auto_request_identity(tmp_path):
    transport = FakeBluetoothTransport()
    session = TerminalSession(transport, log_path=tmp_path / "terminal.log")
    try:
        assert session._connect()
        assert transport.writes == []
    finally:
        session.log_file.close()
