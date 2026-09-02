from __future__ import annotations

from dataclasses import dataclass
import glob
import os
import threading

import serial
from serial import SerialException
from serial.tools import list_ports

from .base import Transport, TransportError


@dataclass(frozen=True)
class SerialDeviceIdentity:
    key: str
    path: str
    description: str = ""
    hwid: str = ""
    vid: int | None = None
    pid: int | None = None
    serial_number: str | None = None
    location: str | None = None

    @property
    def label(self) -> str:
        return self.description or os.path.basename(self.path) or self.path

    @property
    def is_usb(self) -> bool:
        path = self.path
        if path.startswith("/dev/serial/by-id/"):
            return True
        if path.startswith(("/dev/ttyUSB", "/dev/ttyACM")):
            return True
        if self.vid is not None and self.pid is not None:
            return True
        hwid = str(self.hwid or "").upper()
        return "USB" in hwid or "VID:PID" in hwid


def _stable_serial_key(
    preferred_path: str,
    real_path: str,
    *,
    vid: int | None,
    pid: int | None,
    serial_number: str | None,
    location: str | None,
) -> str:
    if preferred_path.startswith("/dev/serial/by-id/"):
        return f"serial-by-id:{preferred_path}"

    if serial_number and vid is not None and pid is not None:
        return f"serial-usb:{vid:04x}:{pid:04x}:{serial_number}"

    if location and vid is not None and pid is not None:
        return f"serial-location:{vid:04x}:{pid:04x}:{location}"

    return f"serial-path:{real_path}"


def _meaningful_port_text(value: object) -> bool:
    text = str(value or "").strip()
    return bool(text and text.lower() not in {"n/a", "unknown", "none"})


def _has_usb_port_metadata(info: object) -> bool:
    vid = getattr(info, "vid", None)
    pid = getattr(info, "pid", None)
    if vid is not None and pid is not None:
        return True

    hwid = str(getattr(info, "hwid", "") or "").upper()
    return "USB" in hwid or "VID:PID" in hwid


def _identified_ttys(info: object) -> bool:
    return _meaningful_port_text(
        getattr(info, "description", "")
    ) or _meaningful_port_text(getattr(info, "hwid", ""))


def _looks_like_useful_serial_info(info: object) -> bool:
    """Hide empty ttyS placeholders while retaining real serial hardware."""
    device = str(getattr(info, "device", "") or "")
    if not device:
        return False

    # On non-POSIX platforms list_ports is the portable source of truth.
    if os.name != "posix":
        return True

    if device.startswith(("/dev/ttyUSB", "/dev/ttyACM")):
        return True

    if _has_usb_port_metadata(info):
        return True

    # Linux commonly exposes /dev/ttyS0..31 even when most entries are only
    # unpopulated 8250 placeholders. Keep a ttyS port only when pyserial/udev
    # can identify it (for example PNP0501).
    if device.startswith("/dev/ttyS"):
        return _identified_ttys(info)

    # Other serial classes (ttyAMA, ttyTHS, platform UARTs, etc.) can be useful
    # even when they are not USB. Preserve pyserial's discovery for those.
    return True


def _useful_port_infos() -> list[object]:
    return [
        info
        for info in list_ports.comports()
        if _looks_like_useful_serial_info(info)
    ]


def _port_info_by_real_path(infos: list[object]) -> dict[str, object]:
    result: dict[str, object] = {}
    for info in infos:
        device = getattr(info, "device", None)
        if device:
            result.setdefault(os.path.realpath(device), info)
    return result


def _by_id_paths_by_real_path() -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for path in sorted(glob.glob("/dev/serial/by-id/*")):
        result.setdefault(os.path.realpath(path), []).append(path)
    return result


def _candidate_serial_paths(
    infos: list[object],
    by_id_by_real: dict[str, list[str]],
) -> list[str]:
    paths = [path for aliases in by_id_by_real.values() for path in aliases]
    paths.extend(
        getattr(info, "device", "")
        for info in infos
        if getattr(info, "device", "")
    )
    paths.extend(sorted(glob.glob("/dev/ttyUSB*")))
    paths.extend(sorted(glob.glob("/dev/ttyACM*")))
    return paths


def _unique_real_paths(paths: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for path in paths:
        real = os.path.realpath(path)
        if real in seen:
            continue
        seen.add(real)
        result.append(real)
    return result


def _preferred_serial_path(
    real_path: str,
    info: object | None,
    by_id_paths: list[str],
) -> str:
    if by_id_paths:
        return by_id_paths[0]
    if info is not None:
        device = getattr(info, "device", None)
        if device:
            return str(device)
    return real_path


def _serial_identity_from_real_path(
    real_path: str,
    info_by_real: dict[str, object],
    by_id_by_real: dict[str, list[str]],
) -> SerialDeviceIdentity:
    info = info_by_real.get(real_path)
    preferred_path = _preferred_serial_path(
        real_path,
        info,
        by_id_by_real.get(real_path, []),
    )

    vid = getattr(info, "vid", None) if info is not None else None
    pid = getattr(info, "pid", None) if info is not None else None
    serial_number = (
        getattr(info, "serial_number", None) if info is not None else None
    )
    location = getattr(info, "location", None) if info is not None else None
    description = getattr(info, "description", "") if info is not None else ""
    hwid = getattr(info, "hwid", "") if info is not None else ""

    return SerialDeviceIdentity(
        key=_stable_serial_key(
            preferred_path,
            real_path,
            vid=vid,
            pid=pid,
            serial_number=serial_number,
            location=location,
        ),
        path=preferred_path,
        description=description or "",
        hwid=hwid or "",
        vid=vid,
        pid=pid,
        serial_number=serial_number,
        location=location,
    )


def discover_serial_devices() -> list[SerialDeviceIdentity]:
    """Discover useful serial devices with stable `/dev/serial/by-id` paths first."""
    infos = _useful_port_infos()
    info_by_real = _port_info_by_real_path(infos)
    by_id_by_real = _by_id_paths_by_real_path()
    candidate_paths = _candidate_serial_paths(infos, by_id_by_real)
    real_paths = _unique_real_paths(candidate_paths)

    return [
        _serial_identity_from_real_path(real, info_by_real, by_id_by_real)
        for real in real_paths
    ]


def find_ports() -> list[str]:
    """Backward-compatible list of preferred serial paths."""
    return [device.path for device in discover_serial_devices()]


class SerialTransport(Transport):
    """Serial transport with sticky reconnect and ESP32-friendly control lines."""

    def __init__(
        self,
        device: str | None = None,
        baud: int = 115200,
        identity: SerialDeviceIdentity | None = None,
    ):
        if device is not None and identity is not None:
            raise ValueError("use either device or identity, not both")

        self.requested_device = device
        self.identity = identity
        self.baud = baud
        self.last_device: str | None = None
        self._serial: serial.Serial | None = None
        self._lock = threading.Lock()

    @property
    def is_connected(self) -> bool:
        with self._lock:
            return bool(self._serial is not None and self._serial.is_open)

    @property
    def device_key(self) -> str:
        if self.identity is not None:
            return self.identity.key
        return f"serial-explicit:{self.requested_device or 'auto'}"

    @property
    def description(self) -> str:
        device = self.last_device
        if device is None and self.identity is not None:
            device = self.identity.path
        if device is None:
            device = self.requested_device or "auto"
        return f"serial:{device} @ {self.baud}"

    def _choose_device(self) -> str | None:
        if self.identity is not None:
            for candidate in discover_serial_devices():
                if candidate.key == self.identity.key:
                    return candidate.path
            return None

        if self.requested_device:
            return self.requested_device if os.path.exists(self.requested_device) else None

        ports = find_ports()
        return ports[0] if ports else None

    @staticmethod
    def _disable_hupcl(ser: serial.Serial) -> None:
        try:
            import termios
        except ImportError:
            return

        try:
            attrs = termios.tcgetattr(ser.fileno())
            attrs[2] &= ~termios.HUPCL
            termios.tcsetattr(ser.fileno(), termios.TCSANOW, attrs)
        except (OSError, termios.error):
            pass

    def connect(self) -> bool:
        device = self._choose_device()
        if not device:
            return False

        try:
            ser = serial.Serial()
            ser.port = device
            ser.baudrate = self.baud
            ser.bytesize = serial.EIGHTBITS
            ser.parity = serial.PARITY_NONE
            ser.stopbits = serial.STOPBITS_ONE
            ser.timeout = 0.20
            ser.write_timeout = 1.0
            ser.rtscts = False
            ser.dsrdtr = False
            ser.xonxoff = False

            # Best-effort no-reset sequence for ESP32-style auto-reset circuits.
            ser.dtr = True
            ser.rts = False
            ser.open()
            ser.dtr = False
            ser.rts = False

            self._disable_hupcl(ser)

            with self._lock:
                self._serial = ser
            self.last_device = device
            return True
        except (SerialException, OSError):
            return False

    def disconnect(self) -> None:
        # read()/write() keep this lock for the complete pyserial operation.
        # Waiting for their bounded timeout is preferable to closing `ser.fd`
        # underneath an active os.read/os.write call.
        with self._lock:
            ser = self._serial
            self._serial = None

        if ser is not None:
            try:
                ser.close()
            except Exception:
                pass

    def read(self, size: int = 512) -> bytes:
        # Keep the transport lock across the blocking read. Ctrl+T d/scanner
        # intentionally disconnect from another thread; without this boundary
        # pyserial can observe fd=None in the middle of Serial.read().
        with self._lock:
            ser = self._serial
            if ser is None or not ser.is_open:
                raise TransportError("serial device is not connected")

            try:
                return ser.read(size)
            except (SerialException, OSError) as exc:
                raise TransportError(str(exc)) from exc

    def write(self, data: bytes) -> None:
        # The same lifetime rule applies to TX: disconnect cannot close the
        # descriptor between Serial.write() and flush().
        with self._lock:
            ser = self._serial
            if ser is None or not ser.is_open:
                raise TransportError("serial device is not connected")

            try:
                ser.write(data)
                ser.flush()
            except (SerialException, OSError) as exc:
                raise TransportError(str(exc)) from exc
