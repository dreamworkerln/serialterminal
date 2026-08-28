from __future__ import annotations

from dataclasses import dataclass
import re
import shutil
import socket
import subprocess
import threading

from ..device_cache import confirmed_devices
from .base import Transport, TransportError

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_DEVICE_RE = re.compile(
    r"(?:\[NEW\]\s+)?Device\s+([0-9A-Fa-f:]{17})\s*(.*)$"
)
_CHANNEL_RE = re.compile(r"Channel:\s*(\d+)", re.IGNORECASE)


@dataclass(frozen=True)
class ClassicDevice:
    name: str
    address: str


@dataclass(frozen=True)
class SppDeviceIdentity:
    name: str
    address: str
    channel: int

    @property
    def key(self) -> str:
        return f"spp-address:{self.address.lower()}"


@dataclass(frozen=True)
class SppProbeResult:
    status: str
    spp: bool | None
    channel: int | None
    connect_test: str
    error: str | None = None


def _clean_output(text: str) -> str:
    return _ANSI_RE.sub("", text or "")


def _parse_devices(text: str) -> list[ClassicDevice]:
    found: dict[str, ClassicDevice] = {}
    for raw in _clean_output(text).splitlines():
        match = _DEVICE_RE.search(raw.strip())
        if not match:
            continue
        address = match.group(1).upper()
        name = match.group(2).strip() or "<unnamed>"
        found[address] = ClassicDevice(name=name, address=address)
    return sorted(
        found.values(),
        key=lambda item: (item.name.lower(), item.address),
    )


def _run(
    command: list[str],
    timeout: float,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=timeout,
        check=False,
    )


def discover_classic_devices(timeout: float = 5.0) -> list[ClassicDevice]:
    """Discover BR/EDR devices using BlueZ, with legacy hcitool fallback."""
    outputs: list[str] = []
    bluetoothctl = shutil.which("bluetoothctl")

    if bluetoothctl:
        seconds = max(1, int(round(timeout)))
        try:
            scan = _run(
                [
                    bluetoothctl,
                    "--timeout",
                    str(seconds),
                    "scan",
                    "bredr",
                ],
                timeout + 3.0,
            )
            outputs.append(scan.stdout)
        except (OSError, subprocess.TimeoutExpired):
            pass

        try:
            listed = _run([bluetoothctl, "devices"], 3.0)
            outputs.append(listed.stdout)
        except (OSError, subprocess.TimeoutExpired):
            pass

        devices = _parse_devices("\n".join(outputs))
        if devices:
            return devices

    hcitool = shutil.which("hcitool")
    if hcitool:
        try:
            result = _run(
                [hcitool, "scan", "--flush"],
                max(timeout, 8.0) + 2.0,
            )
        except (OSError, subprocess.TimeoutExpired):
            return []

        found = []
        for line in _clean_output(result.stdout).splitlines():
            match = re.match(
                r"\s*([0-9A-Fa-f:]{17})\s+(.+?)\s*$",
                line,
            )
            if match:
                found.append(
                    ClassicDevice(
                        match.group(2),
                        match.group(1).upper(),
                    )
                )
        return sorted(
            found,
            key=lambda item: (item.name.lower(), item.address),
        )

    return []


def _parse_sdptool_spp(text: str) -> int | None:
    """Return RFCOMM channel from an SDP Serial Port service record."""
    normalized = _clean_output(text).replace("\r\n", "\n")
    records = re.split(r"\n\s*\n", normalized)

    for record in records:
        lowered = record.lower()
        if not (
            "serial port" in lowered
            or "0x1101" in lowered
            or "00001101-0000-1000-8000-00805f9b34fb" in lowered
        ):
            continue

        channel = _CHANNEL_RE.search(record)
        if channel:
            return int(channel.group(1))

    return None


def probe_spp_channel(
    address: str,
    timeout: float = 8.0,
) -> SppProbeResult:
    """Use BlueZ SDP to decide whether one Classic device exposes SPP."""
    sdptool = shutil.which("sdptool")
    if not sdptool:
        return SppProbeResult(
            status="unknown",
            spp=None,
            channel=None,
            connect_test="not-run",
            error="sdptool not found (install BlueZ tools)",
        )

    try:
        result = _run([sdptool, "browse", address], timeout)
    except subprocess.TimeoutExpired:
        return SppProbeResult(
            "unknown",
            None,
            None,
            "not-run",
            "SDP timeout",
        )
    except OSError as exc:
        return SppProbeResult(
            "unknown",
            None,
            None,
            "not-run",
            str(exc),
        )

    if result.returncode != 0:
        message = (
            _clean_output(result.stdout).strip()
            or f"sdptool exit {result.returncode}"
        )
        return SppProbeResult(
            "unknown",
            None,
            None,
            "not-run",
            message,
        )

    channel = _parse_sdptool_spp(result.stdout)
    if channel is None:
        return SppProbeResult("ok", False, None, "not-run")

    return SppProbeResult("ok", True, channel, "not-run")


def test_rfcomm_connection(
    address: str,
    channel: int,
    timeout: float = 3.0,
) -> tuple[str, str | None]:
    """Best-effort connection test; SPP capability remains valid if this fails."""
    if not hasattr(socket, "AF_BLUETOOTH") or not hasattr(
        socket,
        "BTPROTO_RFCOMM",
    ):
        return (
            "unknown",
            "Python socket has no Bluetooth RFCOMM support",
        )

    sock = None
    try:
        sock = socket.socket(
            socket.AF_BLUETOOTH,
            socket.SOCK_STREAM,
            socket.BTPROTO_RFCOMM,
        )
        sock.settimeout(timeout)
        sock.connect((address, channel))
        return "ok", None
    except (OSError, socket.timeout) as exc:
        return "failed", str(exc)
    finally:
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass


def probe_spp_device(
    address: str,
    timeout: float = 8.0,
    connect_test: bool = True,
) -> SppProbeResult:
    result = probe_spp_channel(address, timeout)
    if result.spp is not True or result.channel is None or not connect_test:
        return result

    status, error = test_rfcomm_connection(
        address,
        result.channel,
        min(timeout, 3.0),
    )
    return SppProbeResult(
        result.status,
        True,
        result.channel,
        status,
        error,
    )


def discover_spp_devices(
    timeout: float = 3.0,
) -> list[SppDeviceIdentity]:
    """Return visible Classic devices previously confirmed by scanner as SPP."""
    cached = confirmed_devices("classic", "spp")
    if not cached:
        return []

    by_address = {
        item["address"].lower(): item
        for item in cached
        if item.get("address")
    }
    visible = discover_classic_devices(timeout)
    result = []

    for device in visible:
        record = by_address.get(device.address.lower())
        if not record:
            continue

        channel = record.get("metadata", {}).get("rfcomm_channel")
        if not isinstance(channel, int) or channel <= 0:
            continue

        result.append(
            SppDeviceIdentity(
                device.name or record.get("name") or "<unnamed>",
                device.address,
                channel,
            )
        )

    return result


class BluetoothSppTransport(Transport):
    """Classic Bluetooth Serial Port Profile transport over RFCOMM."""

    def __init__(
        self,
        identity: SppDeviceIdentity,
        read_timeout: float = 0.20,
        connect_timeout: float = 5.0,
    ):
        self.identity = identity
        self.read_timeout = read_timeout
        self.connect_timeout = connect_timeout
        self._socket: socket.socket | None = None
        self._lock = threading.Lock()

    @property
    def is_connected(self) -> bool:
        with self._lock:
            return self._socket is not None

    @property
    def device_key(self) -> str:
        return self.identity.key

    @property
    def description(self) -> str:
        return (
            f"spp:{self.identity.name} {self.identity.address} "
            f"rfcomm={self.identity.channel}"
        )

    def connect(self) -> bool:
        if self.is_connected:
            return True

        if not hasattr(socket, "AF_BLUETOOTH") or not hasattr(
            socket,
            "BTPROTO_RFCOMM",
        ):
            return False

        sock = None
        try:
            sock = socket.socket(
                socket.AF_BLUETOOTH,
                socket.SOCK_STREAM,
                socket.BTPROTO_RFCOMM,
            )
            sock.settimeout(self.connect_timeout)
            sock.connect((self.identity.address, self.identity.channel))
            sock.settimeout(self.read_timeout)
            with self._lock:
                self._socket = sock
            return True
        except (OSError, socket.timeout):
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass
            return False

    def disconnect(self) -> None:
        with self._lock:
            sock = self._socket
            self._socket = None

        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass

    def read(self, size: int = 512) -> bytes:
        with self._lock:
            sock = self._socket

        if sock is None:
            raise TransportError("SPP device is not connected")

        try:
            data = sock.recv(size)
            if data == b"":
                raise TransportError(
                    "SPP peer closed the RFCOMM connection"
                )
            return data
        except socket.timeout:
            return b""
        except OSError as exc:
            raise TransportError(str(exc)) from exc

    def write(self, data: bytes) -> None:
        with self._lock:
            sock = self._socket

        if sock is None:
            raise TransportError("SPP device is not connected")

        try:
            sock.sendall(data)
        except (OSError, socket.timeout) as exc:
            raise TransportError(str(exc)) from exc
