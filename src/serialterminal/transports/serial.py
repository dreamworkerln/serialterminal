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


def discover_serial_devices() -> list[SerialDeviceIdentity]:
    """Discover USB serial devices with stable `/dev/serial/by-id` paths first."""
    infos = list(list_ports.comports())
    info_by_real: dict[str, object] = {}

    for info in infos:
        device = getattr(info, "device", None)
        if device:
            info_by_real.setdefault(os.path.realpath(device), info)

    by_id_by_real: dict[str, list[str]] = {}
    for path in sorted(glob.glob("/dev/serial/by-id/*")):
        by_id_by_real.setdefault(os.path.realpath(path), []).append(path)

    candidate_paths: list[str] = []
    candidate_paths.extend(path for paths in by_id_by_real.values() for path in paths)
    candidate_paths.extend(
        getattr(info, "device", "") for info in infos if getattr(info, "device", "")
    )
    candidate_paths.extend(sorted(glob.glob("/dev/ttyUSB*")))
    candidate_paths.extend(sorted(glob.glob("/dev/ttyACM*")))

    real_paths: list[str] = []
    seen_real: set[str] = set()
    for path in candidate_paths:
        real = os.path.realpath(path)
        if real in seen_real:
            continue
        seen_real.add(real)
        real_paths.append(real)

    devices: list[SerialDeviceIdentity] = []
    for real in real_paths:
        info = info_by_real.get(real)
        by_id_paths = by_id_by_real.get(real, [])
        preferred_path = by_id_paths[0] if by_id_paths else (
            getattr(info, "device", None) if info is not None else None
        )
        if not preferred_path:
            preferred_path = real

        vid = getattr(info, "vid", None) if info is not None else None
        pid = getattr(info, "pid", None) if info is not None else None
        serial_number = (
            getattr(info, "serial_number", None) if info is not None else None
        )
        location = getattr(info, "location", None) if info is not None else None
        description = getattr(info, "description", "") if info is not None else ""
        hwid = getattr(info, "hwid", "") if info is not None else ""

        devices.append(
            SerialDeviceIdentity(
                key=_stable_serial_key(
                    preferred_path,
                    real,
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
        )

    # Stable order: by-id paths naturally win because they were discovered first.
    return devices


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
        with self._lock:
            ser = self._serial
            self._serial = None

        if ser is not None:
            try:
                ser.close()
            except Exception:
                pass

    def read(self, size: int = 512) -> bytes:
        with self._lock:
            ser = self._serial

        if ser is None or not ser.is_open:
            raise TransportError("serial device is not connected")

        try:
            return ser.read(size)
        except (SerialException, OSError) as exc:
            raise TransportError(str(exc)) from exc

    def write(self, data: bytes) -> None:
        with self._lock:
            ser = self._serial

        if ser is None or not ser.is_open:
            raise TransportError("serial device is not connected")

        try:
            ser.write(data)
            ser.flush()
        except (SerialException, OSError) as exc:
            raise TransportError(str(exc)) from exc
