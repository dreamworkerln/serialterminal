from serialterminal import ble_discovery, bluetooth_scanner
from serialterminal.device_cache import get_cached_device, update_cached_device
from serialterminal.transports.ble_nus import BleDeviceIdentity


def _item(address: str = "AA:BB:CC:DD:EE:10"):
    return ble_discovery.BleDiscoveryItem(
        BleDeviceIdentity("Cached NUS", address),
    )


def _configure_probe(monkeypatch, item, result):
    async def fake_scan(timeout):
        return [item]

    async def fake_probe(candidate, timeout):
        assert candidate is item
        return result

    monkeypatch.setattr(
        bluetooth_scanner,
        "scan_all_ble_devices",
        fake_scan,
    )
    monkeypatch.setattr(
        bluetooth_scanner,
        "probe_ble_nus_async",
        fake_probe,
    )


def test_unknown_probe_preserves_confirmed_nus_and_discoverability(
    tmp_path,
    monkeypatch,
):
    cache_path = tmp_path / "devices.json"
    monkeypatch.setenv("SERIALTERMINAL_CACHE_FILE", str(cache_path))
    item = _item()
    update_cached_device(
        kind="ble",
        address=item.identity.address,
        name=item.identity.name,
        capabilities={"nus": True},
        probe_status="ok",
        path=cache_path,
    )
    _configure_probe(
        monkeypatch,
        item,
        ble_discovery.BleProbeResult(
            status="unknown",
            nus=None,
            error="probe timed out",
        ),
    )

    summary = bluetooth_scanner.scan_ble(
        scan_seconds=0.01,
        probe_timeout=0.01,
    )

    record = get_cached_device("ble", item.identity.address, cache_path)
    assert record["capabilities"]["nus"] is True
    assert record["probe_status"] == "unknown"
    assert record["error"] == "probe timed out"
    assert summary.unknown == 1

    async def fake_discovery(timeout):
        return [item]

    monkeypatch.setattr(ble_discovery, "scan_all_ble_devices", fake_discovery)
    assert ble_discovery.discover_terminal_ble_devices(0.01) == [item.identity]


def test_definitive_negative_replaces_prior_positive_nus(
    tmp_path,
    monkeypatch,
):
    cache_path = tmp_path / "devices.json"
    monkeypatch.setenv("SERIALTERMINAL_CACHE_FILE", str(cache_path))
    item = _item("AA:BB:CC:DD:EE:11")
    update_cached_device(
        kind="ble",
        address=item.identity.address,
        name=item.identity.name,
        capabilities={"nus": True},
        probe_status="ok",
        path=cache_path,
    )
    _configure_probe(
        monkeypatch,
        item,
        ble_discovery.BleProbeResult(status="ok", nus=False),
    )

    bluetooth_scanner.scan_ble(scan_seconds=0.01, probe_timeout=0.01)

    record = get_cached_device("ble", item.identity.address, cache_path)
    assert record["capabilities"]["nus"] is False
    assert record["probe_status"] == "ok"
    assert record["error"] is None


def test_unknown_probe_without_prior_knowledge_does_not_invent_nus(
    tmp_path,
    monkeypatch,
):
    cache_path = tmp_path / "devices.json"
    monkeypatch.setenv("SERIALTERMINAL_CACHE_FILE", str(cache_path))
    item = _item("AA:BB:CC:DD:EE:12")
    _configure_probe(
        monkeypatch,
        item,
        ble_discovery.BleProbeResult(
            status="unknown",
            nus=None,
            error="authentication required",
        ),
    )

    bluetooth_scanner.scan_ble(scan_seconds=0.01, probe_timeout=0.01)

    record = get_cached_device("ble", item.identity.address, cache_path)
    assert record["capabilities"]["nus"] is None
    assert record["probe_status"] == "unknown"
    assert record["error"] == "authentication required"
