from serialterminal.profiles import SendBytes, SendLine
from serialterminal.profiles.chatter import (
    CHATTER_ECHO_TOGGLE,
    CHATTER_HELP_COMMAND,
    CHATTER_ID_COMMAND,
    CHATTER_OUTPUT_MODE_COMMANDS,
    CHATTER_PROFILE,
    CHATTER_TELEMETRY_TX_UUID,
)
from serialterminal.profiles.chatter.presentation import ChatterPresentation
from serialterminal.terminal import TerminalSession
from serialterminal.transports.base import Transport
from serialterminal.transports.ble_nus import NUS_RX_UUID, NUS_TX_UUID
from serialterminal.transports.serial import SerialTransport


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


def test_chatter_profile_preserves_current_controller_conveniences():
    assert CHATTER_PROFILE.name == "chatter"
    assert CHATTER_PROFILE.connect_preamble() == (SendLine(CHATTER_ID_COMMAND),)
    assert CHATTER_PROFILE.device_help_action() == SendLine(CHATTER_HELP_COMMAND)
    assert CHATTER_PROFILE.human_hotkeys() == (
        ("1", "output_chat"),
        ("2", "output_telemetry"),
        ("3", "output_both"),
        ("c", "output_chat"),
        ("t", "output_telemetry"),
        ("b", "output_both"),
        ("e", "echo"),
    )

    actions = CHATTER_PROFILE.human_actions()
    for action, command in CHATTER_OUTPUT_MODE_COMMANDS.items():
        assert actions[action] == SendBytes(command.encode("ascii"))
    assert actions["echo"] == SendBytes(CHATTER_ECHO_TOGGLE.encode("ascii"))

    assert CHATTER_PROFILE.recognized_command("  /reboot  ") == "/reboot"
    assert CHATTER_PROFILE.recognized_command("  /echo x  ") is None
    assert isinstance(CHATTER_PROFILE.make_presentation(), ChatterPresentation)


def test_chatter_raw_hotkey_actions_do_not_append_configured_eol(tmp_path):
    session = TerminalSession(
        DummyTransport(),
        log_path=tmp_path / "terminal.log",
        line_ending="\r\n",
        profile=CHATTER_PROFILE,
    )
    try:
        actions = CHATTER_PROFILE.human_actions()
        assert session._profile_action_bytes(actions["output_chat"]) == b"\x141"
        assert session._profile_action_bytes(actions["output_telemetry"]) == b"\x142"
        assert session._profile_action_bytes(actions["output_both"]) == b"\x143"
        assert session._profile_action_bytes(actions["echo"]) == b"\x14e"
    finally:
        session.log_file.close()


def test_chatter_profile_describes_existing_ble_layout():
    config = CHATTER_PROFILE.ble_config()
    assert config is not None
    assert config.write_characteristic == NUS_RX_UUID
    assert tuple(
        (item.uuid, item.stream, item.required)
        for item in config.receive_streams
    ) == (
        (NUS_TX_UUID, "chat", True),
        (CHATTER_TELEMETRY_TX_UUID, "telemetry", False),
    )


def test_terminal_defaults_to_chatter_profile_and_preserves_serial_preamble(tmp_path):
    session = TerminalSession(
        DummyTransport(),
        log_path=tmp_path / "terminal.log",
    )
    try:
        assert session.profile is CHATTER_PROFILE
        assert session._human_connect_preamble(DummyTransport()) is None
        assert session._human_connect_preamble(
            SerialTransport(device="/dev/ttyPROFILE-TEST")
        ) == b"/id\n"
    finally:
        session.log_file.close()
