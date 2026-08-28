import subprocess

from serialterminal.device_cache import (
    capability_confirmed,
    confirmed_devices,
    get_cached_device,
    update_cached_device,
)
from serialterminal.transports import bluetooth_spp


def test_cache_roundtrip(tmp_path):
    path = tmp_path / "devices.json"
    update_cached_device(
        kind="ble",
        address="AA:BB",
        name="Thing",
        capabilities={"nus": True},
        probe_status="ok",
        path=path,
    )
    record = get_cached_device("ble", "aa:bb", path)
    assert capability_confirmed(record, "nus")
    assert confirmed_devices("ble", "nus", path)[0]["name"] == "Thing"


def test_parse_sdptool_serial_port_channel():
    text = '''Service Name: Serial Port
Service Class ID List:
  "Serial Port" (0x1101)
Protocol Descriptor List:
  "RFCOMM" (0x0003)
    Channel: 7
'''
    assert bluetooth_spp._parse_sdptool_spp(text) == 7


def test_parse_sdptool_non_spp():
    text = '''Service Name: Audio Sink
Service Class ID List:
  "Audio Sink" (0x110b)
Protocol Descriptor List:
  "L2CAP" (0x0100)
'''
    assert bluetooth_spp._parse_sdptool_spp(text) is None


def test_spp_probe_unknown_on_sdptool_failure(monkeypatch):
    monkeypatch.setattr(
        bluetooth_spp.shutil,
        "which",
        lambda name: "/usr/bin/sdptool" if name == "sdptool" else None,
    )

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(
            args[0],
            1,
            "Failed to connect to SDP server",
        )

    monkeypatch.setattr(bluetooth_spp, "_run", fake_run)
    result = bluetooth_spp.probe_spp_channel("AA:BB:CC:DD:EE:FF")
    assert result.status == "unknown"
    assert result.spp is None


def test_default_spp_discovery_uses_only_confirmed_cache(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv(
        "SERIALTERMINAL_CACHE_FILE",
        str(tmp_path / "devices.json"),
    )
    update_cached_device(
        kind="classic",
        address="AA:BB:CC:DD:EE:01",
        name="HC-05",
        capabilities={"spp": True},
        probe_status="ok",
        metadata={"rfcomm_channel": 1},
    )
    monkeypatch.setattr(
        bluetooth_spp,
        "discover_classic_devices",
        lambda timeout=3.0: [
            bluetooth_spp.ClassicDevice(
                "HC-05",
                "AA:BB:CC:DD:EE:01",
            ),
            bluetooth_spp.ClassicDevice(
                "Headphones",
                "AA:BB:CC:DD:EE:02",
            ),
        ],
    )

    found = bluetooth_spp.discover_spp_devices(0.01)
    assert found == [
        bluetooth_spp.SppDeviceIdentity(
            "HC-05",
            "AA:BB:CC:DD:EE:01",
            1,
        )
    ]
