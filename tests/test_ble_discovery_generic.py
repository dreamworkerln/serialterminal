import asyncio

from serialterminal import ble_discovery
from serialterminal.transports import ble_nus


class Dev:
    def __init__(self, name, address):
        self.name = name
        self.address = address
        self.metadata = {"uuids": []}


class Scanner:
    devices = []

    @staticmethod
    async def discover(timeout=3.0, **kwargs):
        if kwargs.get("return_adv"):
            raise TypeError("return_adv not supported")
        return list(Scanner.devices)


def test_generic_ble_scan_preserves_multiple_devices_with_same_name(monkeypatch):
    Scanner.devices = [
        Dev("Controller", "AA:01"),
        Dev("Controller", "AA:02"),
        Dev("Other", "AA:03"),
    ]
    monkeypatch.setattr(ble_nus, "BleakScanner", Scanner)
    monkeypatch.setattr(ble_nus, "BleakClient", object)

    found = asyncio.run(ble_discovery.scan_all_ble_devices(0.01))

    assert [
        (item.identity.name, item.identity.address)
        for item in found
    ] == [
        ("Controller", "AA:01"),
        ("Controller", "AA:02"),
        ("Other", "AA:03"),
    ]
