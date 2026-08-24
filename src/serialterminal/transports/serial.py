from __future__ import annotations

import glob
import os
import threading

import serial
from serial import SerialException

from .base import Transport, TransportError


def find_ports() -> list[str]:
    """Prefer stable /dev/serial/by-id names, then ttyUSB/ttyACM."""
    groups = [
        sorted(glob.glob("/dev/serial/by-id/*")),
        sorted(glob.glob("/dev/ttyUSB*")),
        sorted(glob.glob("/dev/ttyACM*")),
    ]

    result: list[str] = []
    seen_real: set[str] = set()

    for group in groups:
        for path in group:
            real = os.path.realpath(path)
            if real not in seen_real:
                result.append(path)
                seen_real.add(real)

    return result


class SerialTransport(Transport):
    """Serial transport with reconnect support and ESP32-friendly control lines."""

    def __init__(self, device: str | None = None, baud: int = 115200):
        self.requested_device = device
        self.baud = baud
        self.last_device: str | None = None
        self._serial: serial.Serial | None = None
        self._lock = threading.Lock()

    @property
    def is_connected(self) -> bool:
        with self._lock:
            return bool(self._serial is not None and self._serial.is_open)

    @property
    def description(self) -> str:
        device = self.last_device or self.requested_device or "auto"
        return f"serial:{device} @ {self.baud}"

    def _choose_device(self) -> str | None:
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
            # pySerial applies DTR before RTS while opening on Linux.  Request a
            # safe intermediate state, then leave both lines deasserted.
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
