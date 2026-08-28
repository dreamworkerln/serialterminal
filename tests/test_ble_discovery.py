from serialterminal import ble_discovery
from serialterminal.device_cache import update_cached_device
from serialterminal.transports import ble_nus


class Dev:
    def __init__(self, name, address, uuids=()):
        self.name = name
        self.address = address
        self.metadata = {"uuids": list(uuids)}


class Scanner:
    devices = []

    @staticmethod
    async def discover(timeout=3.0, **kwargs):
        if kwargs.get("return_adv"):
            # Exercise compatibility path for older Bleak.
            raise TypeError("return_adv not supported")
        return list(Scanner.devices)


class Char:
    def __init__(self, uuid):
        self.uuid = uuid


class Service:
    def __init__(self, uuid, chars):
        self.uuid = uuid
        self.characteristics = [Char(value) for value in chars]


class Client:
    def __init__(self, device, timeout=8.0):
        self.device = device
        self.services = [
            Service(
                ble_discovery.NUS_SERVICE_UUID,
                [
                    ble_nus.NUS_RX_UUID,
                    ble_nus.NUS_CHAT_TX_UUID,
                    ble_nus.NUS_TELEMETRY_TX_UUID,
                ],
            )
        ]

    async def connect(self):
        pass

    async def disconnect(self):
        pass


def test_default_visibility_known_advertised_and_cached(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv(
        "SERIALTERMINAL_CACHE_FILE",
        str(tmp_path / "cache.json"),
    )
    Scanner.devices = [
        Dev("LoRa-A", "AA:01"),
        Dev("Nordic", "AA:02", [ble_discovery.NUS_SERVICE_UUID]),
        Dev("Cached", "AA:03"),
        Dev("Headphones", "AA:04"),
    ]
    monkeypatch.setattr(ble_nus, "BleakScanner", Scanner)
    monkeypatch.setattr(ble_nus, "BleakClient", Client)
    update_cached_device(
        kind="ble",
        address="AA:03",
        name="Cached",
        capabilities={"nus": True},
        probe_status="ok",
    )

    found = ble_discovery.discover_terminal_ble_devices(0.01)
    assert {item.address for item in found} == {
        "AA:01",
        "AA:02",
        "AA:03",
    }


def test_probe_nus(monkeypatch):
    monkeypatch.setattr(ble_nus, "BleakScanner", Scanner)
    monkeypatch.setattr(ble_nus, "BleakClient", Client)
    item = ble_discovery.BleDiscoveryItem(
        ble_nus.BleDeviceIdentity("Any", "AA:05"),
        raw_device=Dev("Any", "AA:05"),
    )
    result = ble_discovery.probe_ble_nus(item, 0.1)
    assert result.nus is True
    assert result.chat is True
    assert result.telemetry is True
