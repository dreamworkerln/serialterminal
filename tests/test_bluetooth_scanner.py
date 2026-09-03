import asyncio
from types import SimpleNamespace

from serialterminal import ble_discovery, bluetooth_scanner
from serialterminal.transports.ble_nus import BleDeviceIdentity


def test_ble_scanner_uses_one_asyncio_loop(monkeypatch):
    item = ble_discovery.BleDiscoveryItem(
        BleDeviceIdentity("LoRa-Test", "AA:BB:CC:DD:EE:01")
    )
    loops = []

    async def fake_scan(timeout):
        loops.append(asyncio.get_running_loop())
        return [item]

    async def fake_probe(candidate, timeout):
        assert candidate is item
        loops.append(asyncio.get_running_loop())
        return ble_discovery.BleProbeResult(
            status="ok",
            nus=True,
            chat=True,
            telemetry=True,
        )

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
    monkeypatch.setattr(
        bluetooth_scanner,
        "update_cached_device",
        lambda **kwargs: None,
    )

    result = bluetooth_scanner.scan_ble(
        scan_seconds=0.01,
        probe_timeout=0.01,
    )

    assert result.ble_total == 1
    assert result.ble_nus == 1
    assert len(loops) == 2
    assert loops[0] is loops[1]


def test_scanner_numeric_keybindings_exit_immediately():
    bindings = bluetooth_scanner._scan_key_bindings()

    for key in ("1", "2", "3"):
        matches = bindings.get_bindings_for_keys((key,))
        assert matches

        results = []
        event = SimpleNamespace(
            app=SimpleNamespace(
                exit=lambda result=None: results.append(result),
            )
        )
        matches[-1].handler(event)
        assert results == [key]


def test_scanner_menu_flushes_before_prompt(monkeypatch):
    class FakeStdout:
        def __init__(self):
            self.text = []
            self.flush_count = 0

        def write(self, value):
            self.text.append(value)
            return len(value)

        def flush(self):
            self.flush_count += 1

    fake_stdout = FakeStdout()
    monkeypatch.setattr(bluetooth_scanner.sys, "stdout", fake_stdout)
    monkeypatch.setattr(
        bluetooth_scanner,
        "_read_scan_answer",
        lambda prompt: "3",
    )

    assert bluetooth_scanner.choose_scan_mode() == "all"
    assert fake_stdout.flush_count >= 1
