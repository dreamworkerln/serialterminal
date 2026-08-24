from __future__ import annotations

import asyncio
from concurrent.futures import TimeoutError as FutureTimeoutError
import queue
import threading
from typing import Any

from .base import Transport, TransportError

NUS_RX_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"  # PC -> ESP32
NUS_TX_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"  # ESP32 -> PC notify

PINGER_NAME = "LoRa-Pinger"
REPEATER_NAME = "LoRa-Repeater"
TARGET_NAMES = (PINGER_NAME, REPEATER_NAME)

try:
    from bleak import BleakClient, BleakScanner
except ImportError:  # Serial-only installs must keep working without bleak.
    BleakClient = None
    BleakScanner = None


def _require_bleak() -> None:
    if BleakClient is None or BleakScanner is None:
        raise TransportError(
            "BLE support requires bleak. Install with: pip install -e '.[ble]'"
        )


def normalize_ble_target(value: str) -> str | None:
    value = value.strip().lower()
    if value in {"p", "ping", "pinger", PINGER_NAME.lower()}:
        return PINGER_NAME
    if value in {"r", "rep", "repeater", REPEATER_NAME.lower()}:
        return REPEATER_NAME
    return None


def ble_log_slug(target_name: str) -> str:
    return target_name.replace("LoRa-", "").lower()


async def scan_echo_nodes(timeout: float = 3.0) -> dict[str, Any]:
    """Return visible LoRa-Pinger / LoRa-Repeater devices by advertised name."""
    _require_bleak()
    devices = await BleakScanner.discover(timeout=timeout)
    found: dict[str, Any] = {}

    for device in devices:
        name = getattr(device, "name", None)
        if name in TARGET_NAMES:
            found[name] = device

    return found


def discover_echo_nodes(timeout: float = 3.0) -> dict[str, Any]:
    """Synchronous helper used before the interactive terminal starts."""
    return asyncio.run(scan_echo_nodes(timeout))


class BleNusTransport(Transport):
    """Nordic UART Service transport with a name-locked reconnect target."""

    def __init__(
        self,
        target_name: str,
        scan_timeout: float = 3.0,
        connect_timeout: float = 10.0,
        read_timeout: float = 0.20,
        write_timeout: float = 5.0,
    ):
        _require_bleak()

        if target_name not in TARGET_NAMES:
            raise ValueError(f"unsupported BLE target: {target_name}")

        self.target_name = target_name
        self.scan_timeout = scan_timeout
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout
        self.write_timeout = write_timeout

        self._connected = threading.Event()
        self._state_lock = threading.Lock()
        self._client: Any | None = None
        self._address: str | None = None

        self._rx_queue: queue.Queue[bytes] = queue.Queue()
        self._rx_lock = threading.Lock()
        self._rx_buffer = bytearray()

        self._loop_ready = threading.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._loop_thread = threading.Thread(
            target=self._loop_main,
            name=f"ble-nus-{ble_log_slug(target_name)}",
            daemon=True,
        )
        self._loop_thread.start()

        if not self._loop_ready.wait(timeout=2.0):
            raise TransportError("failed to start BLE event loop")

    @property
    def is_connected(self) -> bool:
        return self._connected.is_set()

    @property
    def description(self) -> str:
        address = self._address or "waiting"
        return f"ble:{self.target_name} {address}"

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
        with self._state_lock:
            if self._client is client:
                self._client = None

    def _on_notify(self, _characteristic, data: bytearray) -> None:
        if data:
            self._rx_queue.put(bytes(data))

    async def _connect_async(self) -> bool:
        if self._connected.is_set():
            return True

        found = await scan_echo_nodes(self.scan_timeout)
        device = found.get(self.target_name)
        if device is None:
            return False

        client = BleakClient(
            device,
            disconnected_callback=self._on_disconnect,
            timeout=self.connect_timeout,
        )

        try:
            await client.connect()
            await client.start_notify(NUS_TX_UUID, self._on_notify)
        except Exception:
            try:
                await client.disconnect()
            except Exception:
                pass
            self._connected.clear()
            return False

        with self._state_lock:
            self._client = client
            self._address = getattr(device, "address", None)

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

        if client is not None:
            try:
                await client.disconnect()
            except Exception:
                pass

    def disconnect(self) -> None:
        if self._loop is None or not self._loop.is_running():
            self._connected.clear()
            return

        try:
            future = self._submit(self._disconnect_async())
            future.result(timeout=5.0)
        except Exception:
            self._connected.clear()

    def _take_rx_bytes(self, size: int) -> bytes | None:
        with self._rx_lock:
            if not self._rx_buffer:
                return None
            data = bytes(self._rx_buffer[:size])
            del self._rx_buffer[:size]
            return data

    def read(self, size: int = 512) -> bytes:
        buffered = self._take_rx_bytes(size)
        if buffered is not None:
            return buffered

        try:
            chunk = self._rx_queue.get(timeout=self.read_timeout)
        except queue.Empty:
            if not self._connected.is_set():
                raise TransportError(f"{self.target_name} is disconnected")
            return b""

        if len(chunk) <= size:
            return chunk

        with self._rx_lock:
            self._rx_buffer.extend(chunk[size:])
        return chunk[:size]

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
