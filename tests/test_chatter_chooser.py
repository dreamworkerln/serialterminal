from types import SimpleNamespace

import pytest

from serialterminal import ble_discovery
from serialterminal.cli import DeviceCandidate, DeviceSelector
from serialterminal.device_cache import update_cached_device
from serialterminal.profiles import GENERIC_PROFILE
from serialterminal.profiles.chatter import CHATTER_PROFILE
from serialterminal.transports import ble_nus


NUS = ble_discovery.NUS_SERVICE_UUID


@pytest.fixture
def chooser_lab(tmp_path, monkeypatch):
    monkeypatch.setenv("SERIALTERMINAL_CACHE_FILE", str(tmp_path / "devices.json"))
    state = SimpleNamespace(scanned=[], connected=[], scans=0, reads=0)

    class Scanner:
        @staticmethod
        async def discover(timeout, **kwargs):
            state.scans += 1
            assert kwargs == {"return_adv": True}
            return {
                address: (
                    SimpleNamespace(name=name, address=address),
                    SimpleNamespace(service_uuids=services),
                )
                for name, address, services in state.scanned
            }

    async def connected():
        state.reads += 1
        return state.connected

    def forbidden(*args, **kwargs):
        pytest.fail("chooser must not connect, disconnect or probe")

    monkeypatch.setattr(ble_nus, "BleakScanner", Scanner)
    monkeypatch.setattr(ble_nus, "BleakClient", forbidden)
    monkeypatch.setattr(ble_discovery, "connected_bluez_identities", connected)
    monkeypatch.setattr(ble_discovery, "probe_ble_nus_async", forbidden)
    return state


def cache(address, nus, status="ok"):
    update_cached_device(
        kind="ble", address=address, name="Cached",
        capabilities={"nus": nus}, probe_status=status,
    )


@pytest.mark.parametrize("profile", [GENERIC_PROFILE, CHATTER_PROFILE])
def test_profile_scan_filters_capability_not_name(chooser_lab, profile):
    chooser_lab.scanned = [
        (None, "AA:01", ()),
        ("[TV] Samsung 5 Series (40)", "AA:02", ()),
        ("LE_WH-1000XM5", "AA:03", ()),
        ("LoRa-Chatter-impostor", "AA:04", ()),
        ("Nordic", "AA:05", ()),
        (None, "AA:06", (NUS.upper(),)),
        ("Unrelated name", "AA:07", (NUS,)),
        ("Cached", "AA:08", ()),
    ]
    cache("AA:03", False)
    cache("AA:08", True)
    selector = DeviceSelector("ble", profile=profile)

    found = selector.discover()

    expected = {"AA:06", "AA:07", "AA:08"} if profile is CHATTER_PROFILE else {
        f"AA:{index:02}" for index in range(1, 9)
    }
    assert {item.identity.address for item in found} == expected
    assert chooser_lab.scans == 1


@pytest.mark.parametrize("source", ["cache", "remembered", "connected", "both"])
@pytest.mark.parametrize("nus,status", [(True, "ok"), (True, "unknown"),
                                         (False, "ok"), (None, "unknown")])
def test_known_sources_require_confirmed_nus_without_scan(
    chooser_lab, source, nus, status,
):
    selector = DeviceSelector("ble", profile=CHATTER_PROFILE)
    identity = ble_nus.BleDeviceIdentity("LoRa-Chatter", "AA:01")
    if source in {"remembered", "both"}:
        selector._remember_candidates([selector._ble_candidate(identity)])
    if source in {"connected", "both"}:
        chooser_lab.connected = [
            ble_nus.BleDeviceIdentity("LoRa-Chatter", "aa:01", "/node"),
        ]
    cache("AA:01", nus, status)

    found = selector.known_candidates()

    assert len(found) == int(nus is True)
    if found:
        assert found[0].busy == (source in {"connected", "both"})
    assert chooser_lab.scans == 0
    assert chooser_lab.reads == 1


def test_connected_merge_retains_advertised_nus_for_f2_and_profile_switch(chooser_lab):
    chooser_lab.scanned = [("No trusted prefix", "AA:01", (NUS,))]
    chooser_lab.connected = [
        ble_nus.BleDeviceIdentity("Connected alias", "aa:01", "/node"),
        ble_nus.BleDeviceIdentity("Headphones", "AA:02", "/headphones"),
    ]
    selector = DeviceSelector("ble")
    assert len(selector.discover()) == 2

    selector.profile = CHATTER_PROFILE
    for connected in (True, False, True):
        chooser_lab.connected = []
        if connected:
            chooser_lab.connected = [
                ble_nus.BleDeviceIdentity("Connected alias", "AA:01", "/node"),
                ble_nus.BleDeviceIdentity("Headphones", "AA:02", "/headphones"),
            ]
        found = selector.known_candidates()
        assert len(found) == 1
        assert found[0].key == "ble-address:aa:01"
        assert found[0].busy is connected

    selector.profile = GENERIC_PROFILE
    assert len(selector.known_candidates()) == 2
    assert chooser_lab.scans == 1


def test_f2_merges_new_busy_state_without_losing_remembered_advertisement(chooser_lab):
    chooser_lab.scanned = [(None, "AA:01", (NUS,))]
    selector = DeviceSelector("ble", profile=CHATTER_PROFILE)
    assert len(selector.discover()) == 1
    chooser_lab.connected = [ble_nus.BleDeviceIdentity("Alias", "aa:01", "/node")]

    found = selector.known_candidates()

    assert len(found) == 1 and found[0].busy
    assert found[0].identity.advertised_services == (NUS,)
    assert chooser_lab.scans == 1


def test_definitive_no_revokes_cached_target_even_if_remembered(chooser_lab):
    selector = DeviceSelector("ble", profile=CHATTER_PROFILE)
    cache("AA:01", True)
    chooser_lab.scanned = [("LoRa-Chatter", "AA:01", ())]
    assert len(selector.discover()) == 1
    cache("AA:01", False)
    assert selector.known_candidates() == []
    assert chooser_lab.scans == 1


@pytest.mark.parametrize("profile", [GENERIC_PROFILE, CHATTER_PROFILE])
def test_scan_failure_connected_only_respects_profile(chooser_lab, monkeypatch, profile):
    async def failed_scan(timeout):
        raise RuntimeError("scan unavailable")

    monkeypatch.setattr(ble_discovery, "scan_all_ble_devices", failed_scan)
    chooser_lab.connected = [
        ble_nus.BleDeviceIdentity("Node", "AA:01", "/node"),
        ble_nus.BleDeviceIdentity("TV", "AA:02", "/tv"),
    ]
    cache("AA:01", True)
    found = DeviceSelector("ble", profile=profile).discover()
    assert len(found) == (1 if profile is CHATTER_PROFILE else 2)
    assert all(item.busy for item in found)


def test_chatter_auto_preserves_serial_and_spp(chooser_lab, monkeypatch):
    selector = DeviceSelector("auto", profile=CHATTER_PROFILE)
    serial = DeviceCandidate("serial", "serial", "USB", "port", object())
    spp = DeviceCandidate("spp", "spp", "SPP", "channel", object())
    monkeypatch.setattr(selector, "_discover_serial_candidates", lambda: [serial])
    monkeypatch.setattr(selector, "_discover_spp_candidates", lambda: [spp])
    monkeypatch.setattr(selector, "_cached_spp_candidates", lambda: [])
    chooser_lab.scanned = [("TV", "AA:01", ())]

    assert selector.discover() == [serial, spp]
    assert selector.known_candidates() == [serial, spp]


def test_legacy_bleak_scan_preserves_nus_evidence(chooser_lab, monkeypatch):
    class LegacyScanner:
        @staticmethod
        async def discover(timeout, **kwargs):
            if kwargs:
                raise TypeError("return_adv unsupported")
            return [
                SimpleNamespace(name="Node", address="AA:01", metadata={"uuids": [NUS]}),
                SimpleNamespace(name="TV", address="AA:02", metadata={"uuids": []}),
            ]

    monkeypatch.setattr(ble_nus, "BleakScanner", LegacyScanner)
    found = DeviceSelector("ble", profile=CHATTER_PROFILE).discover()
    assert [item.identity.address for item in found] == ["AA:01"]


@pytest.mark.parametrize("has_nus", [False, True])
def test_f2_menu_after_profile_switch_does_not_scan_or_connect(
    chooser_lab, monkeypatch, has_nus,
):
    chooser_lab.scanned = [("Node", "AA:01", (NUS,) if has_nus else ()),
                           ("TV", "AA:02", ())]
    selector = DeviceSelector("ble")
    assert len(selector.discover()) == 2
    selector.profile = CHATTER_PROFILE
    menus = []

    def cancel(candidates, **kwargs):
        menus.append(candidates)
        assert kwargs == {"auto_single": False, "allow_cancel": True}
        return None

    monkeypatch.setattr(selector, "choose_from", cancel)
    assert selector.choose_transport_menu() is None
    assert len(menus) == int(has_nus)
    if menus:
        assert [item.identity.address for item in menus[0]] == ["AA:01"]
    assert chooser_lab.scans == 1
