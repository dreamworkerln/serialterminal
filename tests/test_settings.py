from dataclasses import FrozenInstanceError
import inspect

import pytest

from serialterminal import cli
from serialterminal.agent_core import SessionManager
from serialterminal.cli import DeviceSelector
from serialterminal.profiles import GENERIC_PROFILE
from serialterminal.profiles.chatter import CHATTER_PROFILE
from serialterminal.settings import DEFAULTS, resolve_serial_baud
from serialterminal.transports.serial import SerialDeviceIdentity, SerialTransport


@pytest.mark.parametrize("profile,expected", [(GENERIC_PROFILE, 115200), (CHATTER_PROFILE, 921600)])
def test_profile_baud_and_explicit_override(profile, expected):
    assert resolve_serial_baud(profile) == expected
    assert DeviceSelector("serial", profile=profile).baud == expected
    assert resolve_serial_baud(profile, 57600) == 57600
    assert DeviceSelector("serial", baud=57600, profile=profile).baud == 57600


def test_defaults_are_immutable_and_runtime_override_is_local():
    with pytest.raises(FrozenInstanceError):
        DEFAULTS.serial.generic_baud = 9600
    with pytest.raises(FrozenInstanceError):
        DEFAULTS.serial = None
    first = DeviceSelector("serial", profile=CHATTER_PROFILE)
    first.baud = 460800
    assert first.baud == 460800
    assert DeviceSelector("serial", profile=CHATTER_PROFILE).baud == 921600
    assert SerialTransport(device="/dev/fake").baud == 115200


@pytest.mark.parametrize("entry", [cli._run_serial, cli._run_auto])
@pytest.mark.parametrize("discovered", [False, True])
@pytest.mark.parametrize("profile,override,expected", [
    ("generic", None, 115200), ("chatter", None, 921600),
    ("chatter", 115200, 115200), ("generic", 921600, 921600),
])
def test_serial_startup_paths_resolve_same_policy(monkeypatch, entry, discovered, profile, override, expected):
    identity = SerialDeviceIdentity("serial:test", "/dev/ttyFAKE")
    candidate = DeviceSelector._serial_candidate(identity)
    monkeypatch.setattr(DeviceSelector, "choose_initial", lambda self: candidate)
    captured = {}
    def run(transport, **kwargs):
        captured.update(kwargs)
        captured["transport"] = transport
        return 0
    monkeypatch.setattr(cli, "_run_session", run)
    args = ["--profile", profile]
    if not discovered:
        args.insert(0, identity.path)
    if override is not None:
        args += ["-b", str(override)]
    assert entry(args, "test") == 0
    assert captured["transport"].baud == expected
    assert captured["selector"].baud == expected
    assert captured["profile"].name == profile


@pytest.mark.parametrize("identity", [None, SerialDeviceIdentity("serial:test", "/dev/ttyFAKE")])
@pytest.mark.parametrize("explicit", [None, 115200, 460800])
def test_profile_recreation_retains_explicit_choice_and_resolves_implicit(identity, explicit):
    selector = DeviceSelector("serial", baud=explicit)
    original = SerialTransport(identity=identity, device=None if identity else "/dev/ttyFAKE", baud=selector.baud)
    changed = selector.recreate_transport(original, CHATTER_PROFILE)
    assert changed.device_key == original.device_key
    assert changed.baud == (921600 if explicit is None else explicit)
    selector.profile = CHATTER_PROFILE
    back = selector.recreate_transport(changed, GENERIC_PROFILE)
    assert back.device_key == original.device_key
    assert back.baud == (115200 if explicit is None else explicit)


def test_runtime_selector_override_survives_profile_switch():
    selector = DeviceSelector("serial", profile=CHATTER_PROFILE)
    selector.baud = 115200
    original = SerialTransport(device="/dev/ttyFAKE", baud=selector.baud)
    assert selector.recreate_transport(original, GENERIC_PROFILE).baud == 115200
    assert selector.recreate_transport(original, CHATTER_PROFILE).baud == 115200


@pytest.mark.parametrize("profile,override,expected", [
    ("generic", None, 115200), ("chatter", None, 921600),
    ("chatter", 115200, 115200), ("generic", 921600, 921600),
])
def test_agent_discovery_defers_omitted_baud_until_profile_is_known(monkeypatch, profile, override, expected):
    import serialterminal.agent_core as agent
    identity = SerialDeviceIdentity("serial:test", "/dev/ttyFAKE")
    candidate = DeviceSelector._serial_candidate(identity)
    monkeypatch.setattr(DeviceSelector, "discover", lambda self: [candidate])
    class AdmissionObserved(Exception):
        pass
    def stop_before_session_start(transport, **kwargs):
        assert transport.baud == expected
        assert transport.device_key == identity.key
        raise AdmissionObserved
    monkeypatch.setattr(agent, "ManagedSession", stop_before_session_start)
    manager = SessionManager()
    try:
        manager.discover(scope="serial", baud=override)
        with pytest.raises(AdmissionObserved):
            manager.open(device_key=identity.key, profile=profile)
    finally:
        manager.close_all()


def test_agent_default_override_remains_authoritative(monkeypatch):
    captured = []
    class Selector:
        def discover(self):
            return []
    def factory(scope, baud, scan):
        captured.append((scope, baud, scan))
        return Selector()
    manager = SessionManager(default_baud=57600, selector_factory=factory)
    try:
        manager.discover(scope="serial")
        manager.discover(scope="auto", baud=9600, scan_seconds=2.5)
        assert captured == [("serial", 57600, 3.0), ("auto", 9600, 2.5)]
    finally:
        manager.close_all()


def test_non_serial_construction_does_not_pass_uart_baud(monkeypatch):
    from serialterminal.transports import bluetooth_spp as spp
    identity = spp.SppDeviceIdentity("test", "AA:BB:CC:DD:EE:FF", 1)
    captured = []
    monkeypatch.setattr(spp, "BluetoothSppTransport", lambda target: captured.append(target))
    candidate = cli.DeviceCandidate("spp", identity.key, "test", "test", identity)
    for profile in (GENERIC_PROFILE, CHATTER_PROFILE):
        DeviceSelector("spp", baud=1000000, profile=profile).make_transport(candidate)
    assert captured == [identity, identity]


def test_shared_scan_and_reconnect_defaults_reach_consumers():
    from serialterminal import ble_discovery, bluetooth_scanner
    from serialterminal.session import ManagedSession
    from serialterminal.terminal import TerminalSession
    from serialterminal.transports.ble_nus import BleNusTransport
    from serialterminal.transports.bluetooth_spp import discover_spp_devices, probe_spp_device
    assert DeviceSelector("auto").scan_seconds == DEFAULTS.discovery.terminal_scan_seconds
    for parser in (cli._auto_parser, cli._ble_parser, cli._spp_parser):
        assert parser("test").parse_args([]).scan_seconds == DEFAULTS.discovery.terminal_scan_seconds
    assert cli._scan_parser("test").parse_args([]).scan_seconds == DEFAULTS.discovery.scanner_scan_seconds
    assert cli._scan_parser("test").parse_args([]).probe_timeout == DEFAULTS.discovery.probe_timeout_seconds
    for target, param, expected in [
        (BleNusTransport, "scan_timeout", DEFAULTS.discovery.terminal_scan_seconds),
        (discover_spp_devices, "timeout", DEFAULTS.discovery.terminal_scan_seconds),
        (ble_discovery.scan_all_ble_devices, "timeout", DEFAULTS.discovery.terminal_scan_seconds),
        (bluetooth_scanner.scan_ble, "scan_seconds", DEFAULTS.discovery.scanner_scan_seconds),
        (probe_spp_device, "timeout", DEFAULTS.discovery.probe_timeout_seconds),
        (ManagedSession, "reconnect_delay", DEFAULTS.session.reconnect_delay),
        (TerminalSession, "reconnect_delay", DEFAULTS.session.reconnect_delay),
        (SessionManager, "reconnect_delay", DEFAULTS.session.reconnect_delay),
    ]:
        assert inspect.signature(target).parameters[param].default == expected
