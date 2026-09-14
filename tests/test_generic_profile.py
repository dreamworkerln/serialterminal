from __future__ import annotations

import serialterminal.cli as cli_module
import serialterminal.terminal as terminal_module
import serialterminal.transports.ble_nus as ble_nus_module
from serialterminal.cli import DeviceCandidate, DeviceSelector
from serialterminal.profiles import GENERIC_PROFILE
from serialterminal.profiles.chatter import CHATTER_PROFILE
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


class FakeStdout:
    def __init__(self):
        self.writes = []

    def write(self, text):
        self.writes.append(text)
        return len(text)

    def flush(self):
        pass


def test_generic_profile_is_transport_only_by_default():
    assert GENERIC_PROFILE.name == "generic"
    assert GENERIC_PROFILE.connect_preamble() == ()
    assert GENERIC_PROFILE.human_hotkeys() == ()
    assert dict(GENERIC_PROFILE.human_actions()) == {}
    assert GENERIC_PROFILE.human_help_lines() == ()
    assert GENERIC_PROFILE.device_help_action() is None
    assert GENERIC_PROFILE.make_presentation() is None
    assert GENERIC_PROFILE.recognized_command("/help") is None

    config = GENERIC_PROFILE.ble_config()
    assert config is not None
    assert config.write_characteristic == NUS_RX_UUID
    assert tuple((item.uuid, item.stream) for item in config.receive_streams) == (
        (NUS_TX_UUID, "main"),
    )


def test_generic_human_profile_sends_no_connect_preamble(tmp_path):
    session = TerminalSession(
        DummyTransport(),
        log_path=tmp_path / "terminal.log",
        profile=GENERIC_PROFILE,
    )
    try:
        assert session._human_connect_preamble(DummyTransport()) is None
        assert session._human_connect_preamble(
            SerialTransport(device="/dev/ttyGENERIC-TEST")
        ) is None
    finally:
        session.log_file.close()


def test_generic_typed_help_is_sent_unchanged(tmp_path, monkeypatch):
    fake_stdout = FakeStdout()
    monkeypatch.setattr(terminal_module.sys, "stdout", fake_stdout)
    session = TerminalSession(
        DummyTransport(),
        log_path=tmp_path / "terminal.log",
        profile=GENERIC_PROFILE,
    )
    try:
        session._submit_interactive_line("/help")
        assert session.outgoing.get_nowait() == "/help"
        assert "[serialterminal hotkeys]" not in "".join(fake_stdout.writes)
    finally:
        session.log_file.close()


def test_generic_help_is_local_only_and_device_neutral(tmp_path, monkeypatch):
    fake_stdout = FakeStdout()
    monkeypatch.setattr(terminal_module.sys, "stdout", fake_stdout)
    session = TerminalSession(
        DummyTransport(),
        log_path=tmp_path / "terminal.log",
        profile=GENERIC_PROFILE,
    )
    try:
        session._show_full_help()
        rendered = "".join(fake_stdout.writes)
        assert session.outgoing.empty()
        assert "profile       generic" in rendered
        assert "Ctrl+T ?     SerialTerminal help" in rendered
        assert "Chatter" not in rendered
        assert "LoRa" not in rendered
        assert "0004" not in rendered
        assert len(session._build_key_bindings().bindings) == 5
    finally:
        session.log_file.close()


def test_human_cli_defaults_to_generic_and_accepts_chatter():
    assert cli_module._auto_parser("serialterminal").parse_args([]).profile == "generic"
    assert (
        cli_module._auto_parser("serialterminal")
        .parse_args(["--profile", "chatter"])
        .profile
        == "chatter"
    )
    assert cli_module._ble_parser("serialterminal ble").parse_args([]).profile == "generic"
    assert cli_module._serial_parser("serialterminal serial").parse_args([]).profile == "generic"
    assert cli_module._spp_parser("serialterminal spp").parse_args([]).profile == "generic"


def test_generic_ble_selector_passes_standard_nus_layout(monkeypatch):
    captured = {}

    class FakeBleNusTransport:
        def __init__(self, identity, **kwargs):
            captured["identity"] = identity
            captured.update(kwargs)

    monkeypatch.setattr(
        ble_nus_module,
        "BleNusTransport",
        FakeBleNusTransport,
    )

    candidate = DeviceCandidate(
        kind="ble",
        key="device-1",
        label="Device 1",
        detail="detail-1",
        identity=object(),
    )
    selector = DeviceSelector("ble", profile=GENERIC_PROFILE)
    transport = selector.make_transport(candidate)

    assert isinstance(transport, FakeBleNusTransport)
    assert captured["write_characteristic"] == NUS_RX_UUID
    assert tuple(
        (item.uuid, item.stream, item.required)
        for item in captured["receive_streams"]
    ) == ((NUS_TX_UUID, "main", True),)


def test_device_selector_accepts_explicit_chatter_profile():
    assert DeviceSelector("ble", profile=CHATTER_PROFILE).profile is CHATTER_PROFILE
