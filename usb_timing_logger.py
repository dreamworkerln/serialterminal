#!/usr/bin/env python3

from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
import sys
import threading
import time

import serial
from serial import SerialException


DEVICES = ("/dev/ttyACM0", "/dev/ttyACM1")
BAUDRATE = 115200
LOG_DIR = Path("logs")
READ_TIMEOUT_S = 0.20
RECONNECT_DELAY_S = 0.50
READ_SIZE = 4096


def _timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def build_log_paths(
    *,
    moment: datetime | None = None,
    pid: int | None = None,
    log_dir: Path = LOG_DIR,
) -> dict[str, Path]:
    """Build one ST-style basename with a distinct timing companion per USB node."""
    current = moment or datetime.now().astimezone()
    process_id = os.getpid() if pid is None else pid
    stamp = current.strftime("%Y%m%d-%H%M%S-%f")
    basename = f"serialterminal-{stamp}-p{process_id}"
    return {
        device: log_dir
        / f"{basename}.{Path(device).name}.timing.log"
        for device in DEVICES
    }


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


def _open_serial(device: str) -> serial.Serial:
    ser = serial.Serial()
    ser.port = device
    ser.baudrate = BAUDRATE
    ser.bytesize = serial.EIGHTBITS
    ser.parity = serial.PARITY_NONE
    ser.stopbits = serial.STOPBITS_ONE
    ser.timeout = READ_TIMEOUT_S
    ser.write_timeout = 1.0
    ser.rtscts = False
    ser.dsrdtr = False
    ser.xonxoff = False
    if os.name == "posix":
        ser.exclusive = True

    # Совпадает с SerialTerminal: стараемся открыть ESP32 USB CDC без
    # нежелательного auto-reset через DTR/RTS и не вешаем линию при close().
    ser.dtr = True
    ser.rts = False
    ser.open()
    ser.dtr = False
    ser.rts = False
    if os.name == "posix":
        _disable_hupcl(ser)
    return ser


def _write_status(handle, device: str, event: str, detail: str = "") -> None:
    suffix = f" detail={detail}" if detail else ""
    handle.write(
        f"{_timestamp()} [USB_TIMING_LOGGER] "
        f"device={device} event={event}{suffix}\n"
    )
    handle.flush()


def _write_payload_line(handle, raw_line: bytes) -> None:
    # Firmware timing records are ASCII, but replacement decoding keeps the logger
    # alive if unrelated diagnostic output contains a malformed UTF-8 byte.
    text = raw_line.rstrip(b"\r").decode("utf-8", errors="replace")
    handle.write(f"{_timestamp()} {text}\n")
    handle.flush()


def _extract_complete_lines(buffer: bytearray) -> list[bytes]:
    lines: list[bytes] = []
    while True:
        newline = buffer.find(b"\n")
        if newline < 0:
            return lines
        lines.append(bytes(buffer[:newline]))
        del buffer[: newline + 1]


def _reader(device: str, path: Path, stop: threading.Event) -> None:
    buffer = bytearray()
    with path.open("a", encoding="utf-8", buffering=1) as handle:
        _write_status(handle, device, "logger_start")
        while not stop.is_set():
            ser: serial.Serial | None = None
            try:
                ser = _open_serial(device)
                _write_status(handle, device, "connected")

                while not stop.is_set():
                    chunk = ser.read(READ_SIZE)
                    if not chunk:
                        continue
                    buffer.extend(chunk)
                    for line in _extract_complete_lines(buffer):
                        _write_payload_line(handle, line)
            except (SerialException, OSError) as exc:
                _write_status(
                    handle,
                    device,
                    "disconnected",
                    str(exc).replace("\r", " ").replace("\n", " "),
                )
                if stop.wait(RECONNECT_DELAY_S):
                    break
            finally:
                if ser is not None:
                    try:
                        ser.close()
                    except Exception:
                        pass

        if buffer:
            _write_payload_line(handle, bytes(buffer))
        _write_status(handle, device, "logger_stop")


def main() -> int:
    if len(sys.argv) != 1:
        print("usb_timing_logger.py takes no arguments", file=sys.stderr)
        return 2

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    paths = build_log_paths()
    stop = threading.Event()

    print("USB firmware timing logger")
    for device in DEVICES:
        print(f"  {device} -> {paths[device]}")
    print("Ctrl+C to stop")

    threads = [
        threading.Thread(
            target=_reader,
            args=(device, paths[device], stop),
            name=f"usb-timing-{Path(device).name}",
            daemon=False,
        )
        for device in DEVICES
    ]
    for thread in threads:
        thread.start()

    try:
        while all(thread.is_alive() for thread in threads):
            time.sleep(0.25)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        for thread in threads:
            thread.join(timeout=2.0)

    if any(thread.is_alive() for thread in threads):
        print("one or more reader threads did not stop cleanly", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
