from __future__ import annotations

import asyncio
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass
import queue
import threading
from typing import Any

from .base import (
    ReceivedChunk,
    Transport,
    TransportError,
    TransportWriteOutcomeUnknown,
)

NUS_RX_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"  # стандартный NUS: host -> peripheral
NUS_TX_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"  # стандартный NUS: peripheral -> host

# BlueZ can keep Bleak's characteristic max_write_without_response_size at the
# ATT default (20) even after a larger ATT MTU is negotiated. On BlueZ, probe
# the current client's negotiated MTU through Bleak's backend helper first.
# Other backends, and BlueZ versions where that private helper is unavailable,
# retain the bounded characteristic-property resolver as a secondary source.
BLE_WRITE_SIZE_SAFE_DEFAULT_BYTES = 20
BLE_WRITE_SIZE_RESOLVE_INTERVAL_S = 0.05
BLE_WRITE_SIZE_RESOLVE_TIMEOUT_S = 0.75
BLE_BLUEZ_MTU_RESOLVE_TIMEOUT_S = 1.0
BLE_ATT_MTU_MIN_BYTES = 23
BLE_ATT_MTU_MAX_BYTES = 517
BLE_WRITE_COMMAND_OVERHEAD_BYTES = 3
BLE_GATT_ATTRIBUTE_VALUE_MAX_BYTES = 512

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


@dataclass(frozen=True)
class BleReceiveStream:
    uuid: str
    stream: str
    required: bool = True


def _require_bleak() -> None:
    if BleakClient is None or BleakScanner is None:
        raise TransportError(
            "BLE support requires bleak. Install with: pip install -e '.[ble]'"
        )


def ble_log_slug(target_name: str) -> str:
    slug = target_name.lower()
    return "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in slug)


async def _scan_raw_devices(timeout: float = 3.0) -> list[Any]:
    _require_bleak()
    return list(await BleakScanner.discover(timeout=timeout))


class BleNusTransport(Transport):
    """NUS transport locked to one BLE address for all reconnect attempts."""

    def __init__(
        self,
        target: BleDeviceIdentity | str,
        scan_timeout: float = 3.0,
        connect_timeout: float = 10.0,
        read_timeout: float = 0.20,
        write_timeout: float = 5.0,
        write_characteristic: str = NUS_RX_UUID,
        receive_streams: tuple[BleReceiveStream, ...] | None = None,
    ):
        _require_bleak()

        if isinstance(target, BleDeviceIdentity):
            self.target_name = target.name
            self.target_address: str | None = target.address
        else:
            # Name-only construction treats the string as an exact advertised name.
            target_name = target.strip()
            if not target_name:
                raise ValueError("BLE target name must not be empty")
            self.target_name = target_name
            self.target_address = None

        configured_streams = (
            (BleReceiveStream(NUS_TX_UUID, "main"),)
            if receive_streams is None
            else tuple(receive_streams)
        )
        if not configured_streams:
            raise ValueError("BLE transport requires at least one receive stream")

        self.scan_timeout = scan_timeout
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout
        self.write_timeout = write_timeout
        self.write_characteristic = write_characteristic
        self.receive_streams = configured_streams
        self._default_stream = configured_streams[0].stream

        self._connected = threading.Event()
        self._state_lock = threading.Lock()
        self._client: Any | None = None
        self._address: str | None = self.target_address
        self._available_streams: set[str] = set()

        # Some BLE backends can keep an old notification callback alive across
        # an unexpected disconnect/reconnect. Give every connection a unique
        # generation so stale callbacks cannot enqueue duplicate bytes into the
        # new session even if the backend invokes them again later.
        self._connection_generation = 0
        self._active_generation: int | None = None
        self._write_size_generation: int | None = None
        self._write_size_bytes: int | None = None

        self._rx_queue: queue.Queue[ReceivedChunk] = queue.Queue()
        self._rx_pending: ReceivedChunk | None = None

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
    def identity_label(self) -> str | None:
        return self.target_name

    @property
    def stream_capabilities(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(item.stream for item in self.receive_streams))

    @property
    def available_streams(self) -> tuple[str, ...]:
        return tuple(
            stream
            for stream in self.stream_capabilities
            if stream in self._available_streams
        )

    @property
    def description(self) -> str:
        address = self._address or self.target_address or "waiting"
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

    def _clear_write_size_state_locked(self) -> None:
        self._write_size_generation = None
        self._write_size_bytes = None

    def _on_disconnect(self, client, generation: int) -> None:
        # A delayed disconnect callback from an older BleakClient must not tear
        # down a newer connection. Keep the old client reference until normal
        # cleanup gets a chance to retire its notify subscriptions explicitly.
        with self._state_lock:
            if self._client is not client or self._active_generation != generation:
                return
            self._active_generation = None
            self._clear_write_size_state_locked()
            self._connected.clear()
            self._available_streams.clear()

    def _queue_notify(self, generation: int, stream: str, data: bytearray) -> None:
        if not data:
            return

        with self._state_lock:
            if self._active_generation != generation:
                return

        payload = bytes(data)
        self._record_timing(
            "ble_notify",
            generation=generation,
            stream=stream,
            bytes=len(payload),
        )
        self._rx_queue.put(ReceivedChunk(stream, payload))

    def _notify_callback(self, generation: int, stream: str):
        return (
            lambda _characteristic, data, generation=generation, stream=stream:
                self._queue_notify(generation, stream, data)
        )

    async def _find_target_device(self) -> Any | None:
        if self.target_address:
            finder = getattr(BleakScanner, "find_device_by_address", None)
            if finder is not None:
                try:
                    return await finder(
                        self.target_address,
                        timeout=self.scan_timeout,
                    )
                except TypeError:
                    # Bleak variants may expose a narrower finder signature.
                    return await finder(self.target_address)

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

    async def _cleanup_client_async(self, client: Any) -> None:
        # stop_notify() is best-effort because an abrupt peripheral power loss
        # means the GATT link may already be gone. The generation guard above is
        # still the correctness boundary if the backend retains a stale callback.
        for receive_stream in self.receive_streams:
            try:
                await client.stop_notify(receive_stream.uuid)
            except Exception:
                pass

        try:
            await client.disconnect()
        except Exception:
            pass

    def _has_client(self) -> bool:
        with self._state_lock:
            return self._client is not None

    async def _retire_stale_client_async(self) -> None:
        if self._has_client():
            await self._disconnect_async()

    def _begin_connection(self, device: Any) -> tuple[Any, int]:
        with self._state_lock:
            self._connection_generation += 1
            generation = self._connection_generation
            self._active_generation = generation
            self._clear_write_size_state_locked()

        client = BleakClient(
            device,
            disconnected_callback=(
                lambda disconnected_client, generation=generation:
                    self._on_disconnect(disconnected_client, generation)
            ),
            timeout=self.connect_timeout,
        )

        with self._state_lock:
            self._client = client
        return client, generation

    async def _connect_receive_streams_async(
        self,
        client: Any,
        generation: int,
    ) -> set[str] | None:
        try:
            await client.connect()
        except Exception:
            return None

        available: set[str] = set()
        for receive_stream in self.receive_streams:
            try:
                await client.start_notify(
                    receive_stream.uuid,
                    self._notify_callback(generation, receive_stream.stream),
                )
            except Exception:
                if receive_stream.required:
                    return None
            else:
                available.add(receive_stream.stream)
        return available

    def _connection_is_current(self, client: Any, generation: int) -> bool:
        with self._state_lock:
            if self._client is not client or self._active_generation != generation:
                return False
            try:
                return bool(getattr(client, "is_connected", True))
            except Exception:
                return False

    def _reported_max_write_without_response_size(self, client: Any) -> int:
        services = getattr(client, "services", None)
        getter = getattr(services, "get_characteristic", None)
        characteristic = None
        if callable(getter):
            try:
                characteristic = getter(self.write_characteristic)
            except Exception:
                characteristic = None

        try:
            size = int(
                getattr(
                    characteristic,
                    "max_write_without_response_size",
                    0,
                )
            )
        except (TypeError, ValueError):
            size = 0
        return size if size > 0 else 0

    def _bluez_backend(self, client: Any) -> Any | None:
        backend = getattr(client, "_backend", None)
        if backend is None:
            return None
        backend_module = type(backend).__module__
        if backend_module == "bleak.backends.bluezdbus.client":
            return backend
        if backend_module.startswith("bleak.backends.bluezdbus."):
            return backend
        return None

    @staticmethod
    def _write_size_from_att_mtu(mtu: int) -> int | None:
        if mtu < BLE_ATT_MTU_MIN_BYTES or mtu > BLE_ATT_MTU_MAX_BYTES:
            return None
        payload_bytes = mtu - BLE_WRITE_COMMAND_OVERHEAD_BYTES
        return max(
            BLE_WRITE_SIZE_SAFE_DEFAULT_BYTES,
            min(payload_bytes, BLE_GATT_ATTRIBUTE_VALUE_MAX_BYTES),
        )

    async def _bluez_negotiated_mtu(
        self,
        client: Any,
        generation: int,
    ) -> tuple[int | None, str | None]:
        """Get the current BlueZ connection's negotiated ATT MTU, if possible.

        Bleak's BlueZ backend has no public negotiated-MTU API. Its own MTU
        example uses ``client._backend._acquire_mtu()``: BlueZ returns the MTU
        from AcquireWrite/AcquireNotify, Bleak immediately closes that acquired
        fd, and normal writes still use ``write_gatt_char(response=False)``.
        Keep this private/backend-specific dependency isolated and optional.
        """
        backend = self._bluez_backend(client)
        if backend is None:
            return None, None

        acquire_mtu = getattr(backend, "_acquire_mtu", None)
        if not callable(acquire_mtu):
            return None, "bluez_acquire_mtu_unavailable"
        if not self._connection_is_current(client, generation):
            return None, "connection_changed"

        try:
            await asyncio.wait_for(
                acquire_mtu(),
                timeout=BLE_BLUEZ_MTU_RESOLVE_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            return None, "bluez_acquire_mtu_timeout"
        except Exception as exc:
            return None, f"bluez_acquire_mtu_{type(exc).__name__}"

        if not self._connection_is_current(client, generation):
            return None, "connection_changed"

        try:
            mtu = int(getattr(client, "mtu_size"))
        except Exception as exc:
            return None, f"bluez_mtu_read_{type(exc).__name__}"

        if self._write_size_from_att_mtu(mtu) is None:
            return None, "bluez_mtu_invalid"
        return mtu, None

    def _record_write_size_aborted(
        self,
        *,
        generation: int,
        initial_size: int,
        last_size: int,
        rechecks: int,
        started: float,
        loop: asyncio.AbstractEventLoop,
        reason: str,
        source: str,
    ) -> None:
        self._record_timing(
            "ble_write_size_resolution_aborted",
            generation=generation,
            source=source,
            initial_size=initial_size,
            initial_characteristic_size=initial_size,
            last_size=last_size,
            rechecks=rechecks,
            wait_ms=round((loop.time() - started) * 1000.0, 3),
            reason=reason,
        )

    def _publish_write_size_resolution(
        self,
        client: Any,
        generation: int,
        size: int,
    ) -> bool:
        with self._state_lock:
            if self._client is not client or self._active_generation != generation:
                return False
            try:
                if not bool(getattr(client, "is_connected", True)):
                    return False
            except Exception:
                return False
            self._write_size_generation = generation
            self._write_size_bytes = size
            return True

    async def _resolve_write_size_async(self, client: Any, generation: int) -> bool:
        loop = asyncio.get_running_loop()
        started = loop.time()
        rechecks = 0

        if not self._connection_is_current(client, generation):
            return False

        initial_size = self._reported_max_write_without_response_size(client)
        current_size = initial_size
        mtu = None
        source = "characteristic_property"
        resolution_reason = ""

        mtu, backend_reason = await self._bluez_negotiated_mtu(client, generation)
        if backend_reason == "connection_changed":
            self._record_write_size_aborted(
                generation=generation,
                initial_size=initial_size,
                last_size=current_size,
                rechecks=rechecks,
                started=started,
                loop=loop,
                reason="connection_changed",
                source="bluez_mtu",
            )
            return False

        mtu_write_size = (
            self._write_size_from_att_mtu(mtu)
            if mtu is not None
            else None
        )
        if mtu_write_size is not None:
            final_size = mtu_write_size
            source = "bluez_mtu"
        else:
            resolution_reason = backend_reason or ""
            deadline = loop.time() + BLE_WRITE_SIZE_RESOLVE_TIMEOUT_S
            while current_size <= BLE_WRITE_SIZE_SAFE_DEFAULT_BYTES:
                if not self._connection_is_current(client, generation):
                    self._record_write_size_aborted(
                        generation=generation,
                        initial_size=initial_size,
                        last_size=current_size,
                        rechecks=rechecks,
                        started=started,
                        loop=loop,
                        reason="connection_changed",
                        source="characteristic_property",
                    )
                    return False

                remaining = deadline - loop.time()
                if remaining <= 0:
                    break

                await asyncio.sleep(
                    min(BLE_WRITE_SIZE_RESOLVE_INTERVAL_S, remaining)
                )
                if not self._connection_is_current(client, generation):
                    self._record_write_size_aborted(
                        generation=generation,
                        initial_size=initial_size,
                        last_size=current_size,
                        rechecks=rechecks,
                        started=started,
                        loop=loop,
                        reason="connection_changed",
                        source="characteristic_property",
                    )
                    return False

                rechecks += 1
                current_size = self._reported_max_write_without_response_size(client)

            if current_size > BLE_WRITE_SIZE_SAFE_DEFAULT_BYTES:
                final_size = current_size
                source = "characteristic_property"
            else:
                final_size = BLE_WRITE_SIZE_SAFE_DEFAULT_BYTES
                source = "fallback"
                if not resolution_reason:
                    resolution_reason = "characteristic_default_after_deadline"

        if not self._publish_write_size_resolution(
            client,
            generation,
            final_size,
        ):
            self._record_write_size_aborted(
                generation=generation,
                initial_size=initial_size,
                last_size=current_size,
                rechecks=rechecks,
                started=started,
                loop=loop,
                reason="stale_completion",
                source=source,
            )
            return False

        self._record_timing(
            "ble_write_size_resolved",
            generation=generation,
            source=source,
            mtu=mtu,
            initial_size=initial_size,
            initial_characteristic_size=initial_size,
            final_characteristic_size=current_size,
            final_size=final_size,
            rechecks=rechecks,
            wait_ms=round((loop.time() - started) * 1000.0, 3),
            fallback=(source == "fallback"),
            reason=resolution_reason,
        )
        return True

    def _publish_connected_state(
        self,
        device: Any,
        client: Any,
        generation: int,
        available_streams: set[str],
    ) -> bool:
        with self._state_lock:
            if self._client is not client:
                return False
            if self._active_generation != generation:
                return False
            if self._write_size_generation != generation:
                return False
            if self._write_size_bytes is None:
                return False
            if not bool(getattr(client, "is_connected", True)):
                return False

            self._address = getattr(device, "address", None)
            if self.target_address is None and self._address:
                # Name-only construction becomes sticky after first
                # unambiguous connection.
                self.target_address = str(self._address)
            self._available_streams = set(available_streams)
            self._connected.set()
            return True

    def _clear_connection_if_current(self, client: Any, generation: int) -> None:
        with self._state_lock:
            current = (
                self._client is client
                or self._active_generation == generation
            )
            if self._client is client:
                self._client = None
            if self._active_generation == generation:
                self._active_generation = None
            if current:
                self._clear_write_size_state_locked()

        if current:
            self._connected.clear()
            self._available_streams.clear()

    async def _fail_connection_async(self, client: Any, generation: int) -> bool:
        await self._cleanup_client_async(client)
        self._clear_connection_if_current(client, generation)
        return False

    async def _connect_async(self) -> bool:
        if self._connected.is_set():
            return True

        await self._retire_stale_client_async()

        device = await self._find_target_device()
        if device is None:
            return False

        client, generation = self._begin_connection(device)
        available_streams = await self._connect_receive_streams_async(
            client,
            generation,
        )
        if available_streams is None:
            return await self._fail_connection_async(client, generation)

        # Subscribe before the BlueZ MTU probe so controller READY/reset output
        # cannot be lost while resolving the current generation's write size.
        if not await self._resolve_write_size_async(client, generation):
            return await self._fail_connection_async(client, generation)

        if not self._publish_connected_state(
            device,
            client,
            generation,
            available_streams,
        ):
            return await self._fail_connection_async(client, generation)

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
            self._active_generation = None
            self._clear_write_size_state_locked()

        self._connected.clear()
        self._available_streams.clear()

        if client is not None:
            await self._cleanup_client_async(client)

    def disconnect(self) -> None:
        if self._loop is None or not self._loop.is_running():
            self._connected.clear()
            self._available_streams.clear()
            with self._state_lock:
                self._client = None
                self._active_generation = None
                self._clear_write_size_state_locked()
            return

        try:
            future = self._submit(self._disconnect_async())
            future.result(timeout=5.0)
        except Exception:
            self._connected.clear()
            self._available_streams.clear()
            with self._state_lock:
                self._client = None
                self._active_generation = None
                self._clear_write_size_state_locked()

    def close(self) -> None:
        self.disconnect()
        loop = self._loop
        if loop is not None and loop.is_running():
            loop.call_soon_threadsafe(loop.stop)
        if self._loop_thread.is_alive():
            self._loop_thread.join(timeout=1.0)

    def read_chunk(self, size: int = 512) -> ReceivedChunk:
        if self._rx_pending is not None:
            chunk = self._rx_pending
            self._rx_pending = None
        else:
            try:
                chunk = self._rx_queue.get(timeout=self.read_timeout)
            except queue.Empty:
                if not self._connected.is_set():
                    raise TransportError(f"{self.target_name} is disconnected")
                return ReceivedChunk(self._default_stream, b"")

        if len(chunk.data) <= size:
            return chunk

        # Непрочитанный tail той же notification остаётся впереди более поздних
        # notifications, чтобы small reads не меняли исходный byte/stream order.
        head = chunk.data[:size]
        tail = chunk.data[size:]
        self._rx_pending = ReceivedChunk(chunk.stream, tail)
        return ReceivedChunk(chunk.stream, head)

    def read(self, size: int = 512) -> bytes:
        return self.read_chunk(size).data

    async def _write_async(self, data: bytes) -> None:
        with self._state_lock:
            client = self._client
            generation = self._active_generation
            max_chunk_bytes = (
                self._write_size_bytes
                if self._write_size_generation == generation
                else None
            )

        if (
            client is None
            or generation is None
            or not self._connected.is_set()
        ):
            raise TransportError(f"{self.target_name} is disconnected")

        if max_chunk_bytes is None:
            # Defensive invariant fallback. Normal connected state is published
            # only after current-generation resolution has completed.
            max_chunk_bytes = BLE_WRITE_SIZE_SAFE_DEFAULT_BYTES
            self._record_timing(
                "ble_write_size_unresolved_fallback",
                generation=generation,
                final_size=max_chunk_bytes,
                fallback=True,
            )

        chunk_count = max(
            1,
            (len(data) + max_chunk_bytes - 1) // max_chunk_bytes,
        )
        self._record_timing(
            "ble_gatt_write_start",
            generation=generation,
            bytes=len(data),
            characteristic=self.write_characteristic,
            response=False,
            max_chunk_bytes=max_chunk_bytes,
            chunks=chunk_count,
        )

        completed_chunks = 0
        try:
            for chunk_index in range(chunk_count):
                offset = chunk_index * max_chunk_bytes
                chunk = (
                    data[offset : offset + max_chunk_bytes]
                    if data
                    else b""
                )
                self._record_timing(
                    "ble_gatt_write_chunk_start",
                    generation=generation,
                    bytes=len(chunk),
                    logical_bytes=len(data),
                    chunk_index=chunk_index,
                    chunks=chunk_count,
                    offset=offset,
                    characteristic=self.write_characteristic,
                    response=False,
                )
                await client.write_gatt_char(
                    self.write_characteristic,
                    chunk,
                    response=False,
                )
                completed_chunks += 1
                self._record_timing(
                    "ble_gatt_write_chunk_done",
                    generation=generation,
                    bytes=len(chunk),
                    logical_bytes=len(data),
                    chunk_index=chunk_index,
                    chunks=chunk_count,
                    offset=offset,
                    characteristic=self.write_characteristic,
                    response=False,
                )
        except Exception as exc:
            self._record_timing(
                "ble_gatt_write_error",
                generation=generation,
                bytes=len(data),
                characteristic=self.write_characteristic,
                error=type(exc).__name__,
                max_chunk_bytes=max_chunk_bytes,
                chunks=chunk_count,
                completed_chunks=completed_chunks,
                failed_chunk_index=completed_chunks,
            )
            if completed_chunks:
                raise TransportWriteOutcomeUnknown(
                    "BLE fragmented write failed after "
                    f"{completed_chunks}/{chunk_count} chunks; outcome unknown"
                ) from exc
            raise

        self._record_timing(
            "ble_gatt_write_done",
            generation=generation,
            bytes=len(data),
            characteristic=self.write_characteristic,
            response=False,
            max_chunk_bytes=max_chunk_bytes,
            chunks=chunk_count,
        )

    def write(self, data: bytes) -> None:
        if not self._connected.is_set():
            raise TransportError(f"{self.target_name} is disconnected")

        future = self._submit(self._write_async(data))
        try:
            future.result(timeout=self.write_timeout)
        except FutureTimeoutError as exc:
            # run_coroutine_threadsafe().cancel() requests Task cancellation but
            # cannot prove that a backend GATT command was not already accepted.
            # Mark the write outcome unknown so the session never auto-retries it.
            future.cancel()
            self._connected.clear()
            raise TransportWriteOutcomeUnknown(
                f"BLE write timed out after {self.write_timeout:g}s; outcome unknown"
            ) from exc
        except TransportWriteOutcomeUnknown:
            self._connected.clear()
            raise
        except Exception as exc:
            self._connected.clear()
            raise TransportError(str(exc)) from exc
