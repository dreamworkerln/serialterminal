from __future__ import annotations

import asyncio
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass
import queue
import threading
from typing import Any

from .base import ReceivedChunk, Transport, TransportError

NUS_RX_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"  # PC -> ESP32
NUS_CHAT_TX_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"  # ESP32 -> PC chat
NUS_TELEMETRY_TX_UUID = "6e400004-b5a3-f393-e0a9-e50e24dcca9e"  # engineering telemetry

# Backward-compatible alias used by older tests/callers.
NUS_TX_UUID = NUS_CHAT_TX_UUID

PINGER_NAME = "LoRa-Pinger"
REPEATER_NAME = "LoRa-Repeater"

try:
    from bleak import BleakClient, BleakScanner
except ImportError:  # Serial-only imports must still work before BLE is requested.
    BleakClient = None
    BleakScanner = None


@dataclass(frozen=True)
class BleDeviceIdentity:
    name: str
    address: str

    @property
    def key(self) -> str:
        return f"ble-address:{self.address.lower()}"


def _require_bleak() -> None:
    if BleakClient is None or BleakScanner is None:
        raise TransportError(
            "BLE support requires bleak. Install with: pip install -e '.[ble]'"
        )


def is_supported_ble_name(name: str | None) -> bool:
    """Accept current and future project BLE nodes using the LoRa-* namespace."""
    return bool(name and name.startswith("LoRa-"))


def normalize_ble_target(value: str) -> str | None:
    value = value.strip()
    lower = value.lower()
    if lower in {"p", "ping", "pinger", PINGER_NAME.lower()}:
        return PINGER_NAME
    if lower in {"r", "rep", "repeater", REPEATER_NAME.lower()}:
        return REPEATER_NAME
    if lower.startswith("lora-"):
        return value
    return None


def ble_log_slug(target_name: str) -> str:
    slug = target_name.replace("LoRa-", "").lower()
    return "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in slug)


async def _scan_raw_devices(timeout: float = 3.0) -> list[Any]:
    _require_bleak()
    return list(await BleakScanner.discover(timeout=timeout))


async def scan_nus_devices(timeout: float = 3.0) -> list[BleDeviceIdentity]:
    """Return visible project BLE devices, preserving multiple devices per name."""
    devices = await _scan_raw_devices(timeout)
    result: list[BleDeviceIdentity] = []
    seen: set[str] = set()

    for device in devices:
        name = getattr(device, "name", None)
        address = getattr(device, "address", None)
        if not is_supported_ble_name(name) or not address:
            continue

        key = str(address).lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(BleDeviceIdentity(str(name), str(address)))

    result.sort(key=lambda item: (item.name.lower(), item.address.lower()))
    return result


def discover_nus_devices(timeout: float = 3.0) -> list[BleDeviceIdentity]:
    """Synchronous discovery helper used by the interactive device chooser."""
    return asyncio.run(scan_nus_devices(timeout))


def discover_echo_nodes(timeout: float = 3.0) -> dict[str, Any]:
    """Legacy helper: visible Pinger/Repeater identities keyed by advertised name."""
    found: dict[str, Any] = {}
    for item in discover_nus_devices(timeout):
        if item.name in {PINGER_NAME, REPEATER_NAME}:
            found[item.name] = item
    return found


class BleNusTransport(Transport):
    """NUS transport locked to one BLE address for all reconnect attempts."""

    def __init__(
        self,
        target: BleDeviceIdentity | str,
        scan_timeout: float = 3.0,
        connect_timeout: float = 10.0,
        read_timeout: float = 0.20,
        write_timeout: float = 5.0,
    ):
        _require_bleak()

        if isinstance(target, BleDeviceIdentity):
            self.target_name = target.name
            self.target_address: str | None = target.address
        else:
            # Compatibility path for old callers. CLI selection now always locks
            # a concrete address before constructing the transport.
            normalized = normalize_ble_target(target)
            if normalized is None:
                raise ValueError(f"unsupported BLE target: {target}")
            self.target_name = normalized
            self.target_address = None

        self.scan_timeout = scan_timeout
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout
        self.write_timeout = write_timeout

        self._connected = threading.Event()
        self._state_lock = threading.Lock()
        self._client: Any | None = None
        self._address: str | None = self.target_address
        self._telemetry_available = False

        self._rx_queue: queue.Queue[ReceivedChunk] = queue.Queue()

        self._loop_ready = threading.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._loop_thread = threading.Thread(
            target=self._loop_main,
            name=f"ble-nus-{ble_log_slug(self.target_name)}",
            daemon=True,
        )
        self._loop_thread.start()

        if not self._loop_ready.wait(timeout=2.0):
            raise TransportError("failed to start BLE event loop")

    @property
    def is_connected(self) -> bool:
        return self._connected.is_set()

    @property
    def device_key(self) -> str:
        if self.target_address:
            return f"ble-address:{self.target_address.lower()}"
        return f"ble-name:{self.target_name.lower()}"

    @property
    def stream_capabilities(self) -> tuple[str, ...]:
        return ("chat", "telemetry")

    @property
    def telemetry_available(self) -> bool:
        return self._telemetry_available

    @property
    def description(self) -> str:
        address = self._address or self.target_address or "waiting"
        suffix = " telemetry=on" if self._telemetry_available else " telemetry=off"
        return f"ble:{self.target_name} {address}{suffix}"

    def _loop_main(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        self._loop_ready.set()
        loop.run_forever()

        pending = asyncio.all_tasks(loop)
        for task in pending:
            task.cancel()
        if pending:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        loop.close()

    def _submit(self, coroutine):
        loop = self._loop
        if loop is None or not loop.is_running():
            raise TransportError("BLE event loop is not running")
        return asyncio.run_coroutine_threadsafe(coroutine, loop)

    def _on_disconnect(self, client) -> None:
        self._connected.clear()
        self._telemetry_available = False
        with self._state_lock:
            if self._client is client:
                self._client = None

    def _on_chat_notify(self, _characteristic, data: bytearray) -> None:
        if data:
            self._rx_queue.put(ReceivedChunk("chat", bytes(data)))

    def _on_telemetry_notify(self, _characteristic, data: bytearray) -> None:
        if data:
            self._rx_queue.put(ReceivedChunk("telemetry", bytes(data)))

    async def _find_target_device(self) -> Any | None:
        devices = await _scan_raw_devices(self.scan_timeout)

        if self.target_address:
            wanted = self.target_address.lower()
            for device in devices:
                address = getattr(device, "address", None)
                if address and str(address).lower() == wanted:
                    return device
            return None

        matches = [
            device
            for device in devices
            if getattr(device, "name", None) == self.target_name
        ]
        return matches[0] if len(matches) == 1 else None

    async def _connect_async(self) -> bool:
        if self._connected.is_set():
            return True

        device = await self._find_target_device()
        if device is None:
            return False

        client = BleakClient(
            device,
            disconnected_callback=self._on_disconnect,
            timeout=self.connect_timeout,
        )

        try:
            await client.connect()
            await client.start_notify(NUS_CHAT_TX_UUID, self._on_chat_notify)
        except Exception:
            try:
                await client.disconnect()
            except Exception:
                pass
            self._connected.clear()
            return False

        telemetry_available = False
        try:
            await client.start_notify(
                NUS_TELEMETRY_TX_UUID,
                self._on_telemetry_notify,
            )
            telemetry_available = True
        except Exception:
            # Echo-era firmware only exposes standard NUS TX (0003). That is
            # still a valid connection; only Chatter telemetry view is absent.
            telemetry_available = False

        with self._state_lock:
            self._client = client
            self._address = getattr(device, "address", None)
            if self.target_address is None and self._address:
                # Legacy name-only construction becomes sticky after first
                # unambiguous connection.
                self.target_address = str(self._address)

        self._telemetry_available = telemetry_available
        self._connected.set()
        return True

    def connect(self) -> bool:
        if self._connected.is_set():
            return True

        try:
            future = self._submit(self._connect_async())
            return bool(
                future.result(
                    timeout=self.scan_timeout + self.connect_timeout + 2.0
                )
            )
        except (FutureTimeoutError, TransportError):
            return False
        except Exception:
            return False

    async def _disconnect_async(self) -> None:
        with self._state_lock:
            client = self._client
            self._client = None

        self._connected.clear()
        self._telemetry_available = False

        if client is not None:
            try:
                await client.disconnect()
            except Exception:
                pass

    def disconnect(self) -> None:
        if self._loop is None or not self._loop.is_running():
            self._connected.clear()
            self._telemetry_available = False
            return

        try:
            future = self._submit(self._disconnect_async())
            future.result(timeout=5.0)
        except Exception:
            self._connected.clear()
            self._telemetry_available = False

    def close(self) -> None:
        self.disconnect()
        loop = self._loop
        if loop is not None and loop.is_running():
            loop.call_soon_threadsafe(loop.stop)
        if self._loop_thread.is_alive():
            self._loop_thread.join(timeout=1.0)

    def read_chunk(self, size: int = 512) -> ReceivedChunk:
        try:
            chunk = self._rx_queue.get(timeout=self.read_timeout)
        except queue.Empty:
            if not self._connected.is_set():
                raise TransportError(f"{self.target_name} is disconnected")
            return ReceivedChunk("chat", b"")

        if len(chunk.data) <= size:
            return chunk

        # BLE notifications are normally small, but preserve the Transport size
        # contract without losing the tail.
        head = chunk.data[:size]
        tail = chunk.data[size:]
        self._rx_queue.put(ReceivedChunk(chunk.stream, tail))
        return ReceivedChunk(chunk.stream, head)

    def read(self, size: int = 512) -> bytes:
        return self.read_chunk(size).data

    async def _write_async(self, data: bytes) -> None:
        with self._state_lock:
            client = self._client

        if client is None or not self._connected.is_set():
            raise TransportError(f"{self.target_name} is disconnected")

        await client.write_gatt_char(NUS_RX_UUID, data, response=False)

    def write(self, data: bytes) -> None:
        if not self._connected.is_set():
            raise TransportError(f"{self.target_name} is disconnected")

        try:
            future = self._submit(self._write_async(data))
            future.result(timeout=self.write_timeout)
        except Exception as exc:
            self._connected.clear()
            raise TransportError(str(exc)) from exc
