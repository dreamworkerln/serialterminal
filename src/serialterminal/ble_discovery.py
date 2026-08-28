from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Iterable

from .device_cache import capability_confirmed, get_cached_device
from .transports import ble_nus
from .transports.ble_nus import (
    BleDeviceIdentity,
    NUS_CHAT_TX_UUID,
    NUS_RX_UUID,
    NUS_TELEMETRY_TX_UUID,
)

NUS_SERVICE_UUID = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"

# Debug/build policy. Normal discovery keeps unrelated BLE devices hidden.
# The aggressive scanner ignores this flag and always probes everything it sees.
SHOW_ALL_BLE_DEVICES = False


@dataclass(frozen=True)
class BleDiscoveryItem:
    identity: BleDeviceIdentity
    advertised_services: tuple[str, ...] = ()
    # Kept only as discovery metadata/debug context. Capability probing must not
    # connect through this object because BlueZ can retire its D-Bus object path
    # while the scanner is sequentially probing other devices.
    raw_device: Any = field(default=None, compare=False, repr=False)


@dataclass(frozen=True)
class BleProbeResult:
    status: str
    nus: bool | None
    chat: bool | None
    telemetry: bool | None
    error: str | None = None


def _normalize_uuid(value: str) -> str:
    return str(value).lower()


def _service_uuids_from_device(device: Any) -> tuple[str, ...]:
    metadata = getattr(device, "metadata", None)
    if isinstance(metadata, dict):
        uuids = metadata.get("uuids") or ()
        return tuple(sorted({_normalize_uuid(uuid) for uuid in uuids}))
    return ()


async def scan_all_ble_devices(timeout: float = 3.0) -> list[BleDiscoveryItem]:
    """Return every BLE device visible to Bleak, including unrelated devices."""
    ble_nus._require_bleak()
    scanner = ble_nus.BleakScanner

    try:
        discovered = await scanner.discover(timeout=timeout, return_adv=True)
    except TypeError:
        # Older Bleak versions do not expose return_adv. BLEDevice.metadata on
        # those versions normally still contains advertised service UUIDs.
        discovered = await scanner.discover(timeout=timeout)

    if isinstance(discovered, dict):
        iterable = []
        for device, advertisement in discovered.values():
            advertised = tuple(
                sorted(
                    {
                        _normalize_uuid(uuid)
                        for uuid in (
                            getattr(advertisement, "service_uuids", None) or ()
                        )
                    }
                )
            )
            iterable.append((device, advertised))
    else:
        iterable = [
            (device, _service_uuids_from_device(device))
            for device in discovered
        ]

    items: list[BleDiscoveryItem] = []
    seen: set[str] = set()
    for device, advertised in iterable:
        address = getattr(device, "address", None)
        if not address:
            continue
        key = str(address).lower()
        if key in seen:
            continue
        seen.add(key)
        name = getattr(device, "name", None) or "<unnamed>"
        items.append(
            BleDiscoveryItem(
                identity=BleDeviceIdentity(str(name), str(address)),
                advertised_services=advertised,
                raw_device=device,
            )
        )

    items.sort(
        key=lambda item: (
            item.identity.name.lower(),
            item.identity.address.lower(),
        )
    )
    return items


def _default_visible(item: BleDiscoveryItem) -> bool:
    if SHOW_ALL_BLE_DEVICES:
        return True
    if ble_nus.is_supported_ble_name(item.identity.name):
        return True
    if NUS_SERVICE_UUID in item.advertised_services:
        return True
    cached = get_cached_device("ble", item.identity.address)
    return capability_confirmed(cached, "nus")


def discover_terminal_ble_devices(
    timeout: float = 3.0,
) -> list[BleDeviceIdentity]:
    """Safe/default BLE discovery: known, advertised-NUS, or cached-NUS only."""
    return [
        item.identity
        for item in asyncio.run(scan_all_ble_devices(timeout))
        if _default_visible(item)
    ]


def _iter_service_objects(services: Any) -> Iterable[Any]:
    service_map = getattr(services, "services", None)
    if isinstance(service_map, dict):
        return service_map.values()
    try:
        return iter(services)
    except TypeError:
        return ()


def _collect_gatt_uuids(services: Any) -> tuple[set[str], set[str]]:
    service_uuids: set[str] = set()
    characteristic_uuids: set[str] = set()

    for service in _iter_service_objects(services):
        uuid = getattr(service, "uuid", None)
        if uuid:
            service_uuids.add(_normalize_uuid(uuid))
        for characteristic in getattr(service, "characteristics", ()) or ():
            char_uuid = getattr(characteristic, "uuid", None)
            if char_uuid:
                characteristic_uuids.add(_normalize_uuid(char_uuid))

    char_map = getattr(services, "characteristics", None)
    if isinstance(char_map, dict):
        for characteristic in char_map.values():
            char_uuid = getattr(characteristic, "uuid", None)
            if char_uuid:
                characteristic_uuids.add(_normalize_uuid(char_uuid))

    return service_uuids, characteristic_uuids


async def _find_fresh_device_by_address(
    address: str,
    timeout: float,
) -> Any | None:
    """Resolve a fresh BLEDevice so BlueZ D-Bus paths cannot go stale."""
    scanner = ble_nus.BleakScanner
    finder = getattr(scanner, "find_device_by_address", None)

    if finder is not None:
        try:
            return await finder(address, timeout=timeout)
        except TypeError:
            # Compatibility with Bleak variants exposing a narrower signature.
            return await finder(address)

    # Older Bleak fallback: perform a fresh discovery and match the address.
    devices = await scanner.discover(timeout=timeout)
    wanted = address.lower()
    for device in devices:
        candidate = getattr(device, "address", None)
        if candidate and str(candidate).lower() == wanted:
            return device
    return None


async def _probe_ble_nus_async(
    item: BleDiscoveryItem,
    timeout: float,
) -> BleProbeResult:
    """Actively connect and inspect GATT capabilities of one BLE device."""
    ble_nus._require_bleak()

    try:
        # Never reuse the BLEDevice captured by the initial all-device scan.
        # On BlueZ its /org/bluez/hciX/dev_XX_... object can disappear while
        # earlier scanner entries are being probed. Resolve the MAC immediately
        # before connecting so Bleak gets a current D-Bus object path.
        fresh_device = await _find_fresh_device_by_address(
            item.identity.address,
            timeout,
        )
        if fresh_device is None:
            return BleProbeResult(
                "unknown",
                None,
                None,
                None,
                f"device {item.identity.address} is not visible now",
            )
    except Exception as exc:
        return BleProbeResult("unknown", None, None, None, str(exc))

    client = ble_nus.BleakClient(fresh_device, timeout=timeout)

    try:
        await client.connect()
        services = getattr(client, "services", None)
        if services is None and hasattr(client, "get_services"):
            services = await client.get_services()

        _service_uuids, characteristic_uuids = _collect_gatt_uuids(services)
        rx = _normalize_uuid(NUS_RX_UUID) in characteristic_uuids
        chat = _normalize_uuid(NUS_CHAT_TX_UUID) in characteristic_uuids
        telemetry = (
            _normalize_uuid(NUS_TELEMETRY_TX_UUID) in characteristic_uuids
        )

        # RX+CHAT is the actual terminal compatibility boundary. A few bridges
        # expose NUS-compatible characteristics below a vendor service UUID.
        nus = rx and chat
        return BleProbeResult("ok", nus, chat, telemetry)
    except Exception as exc:
        # Timeout/refusal/authentication is UNKNOWN, not proof of capability NO.
        return BleProbeResult("unknown", None, None, None, str(exc))
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass


def probe_ble_nus(
    item: BleDiscoveryItem,
    timeout: float = 8.0,
) -> BleProbeResult:
    return asyncio.run(_probe_ble_nus_async(item, timeout))
