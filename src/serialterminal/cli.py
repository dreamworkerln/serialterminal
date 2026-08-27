from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
import sys
import time
from typing import Any

from .terminal import TerminalSession
from .transports.base import Transport, TransportError
from .transports.serial import (
    SerialDeviceIdentity,
    SerialTransport,
    discover_serial_devices,
    find_ports,
)


@dataclass(frozen=True)
class DeviceCandidate:
    kind: str
    key: str
    label: str
    detail: str
    identity: Any


class DeviceSelector:
    """Discover devices for one CLI scope and create sticky transports."""

    def __init__(self, scope: str, baud: int = 115200, scan_seconds: float = 3.0):
        if scope not in {"auto", "serial", "ble"}:
            raise ValueError(f"unknown device selector scope: {scope}")
        self.scope = scope
        self.baud = baud
        self.scan_seconds = scan_seconds

    def discover(self) -> list[DeviceCandidate]:
        candidates: list[DeviceCandidate] = []

        if self.scope in {"auto", "serial"}:
            for item in discover_serial_devices():
                meta: list[str] = [item.path]
                if item.vid is not None and item.pid is not None:
                    meta.append(f"VID:PID={item.vid:04X}:{item.pid:04X}")
                if item.serial_number:
                    meta.append(f"serial={item.serial_number}")
                if item.location:
                    meta.append(f"location={item.location}")

                candidates.append(
                    DeviceCandidate(
                        kind="serial",
                        key=item.key,
                        label=f"USB  {item.label}",
                        detail="  ".join(meta),
                        identity=item,
                    )
                )

        if self.scope in {"auto", "ble"}:
            try:
                from .transports.ble_nus import discover_nus_devices

                for item in discover_nus_devices(self.scan_seconds):
                    candidates.append(
                        DeviceCandidate(
                            kind="ble",
                            key=item.key,
                            label=f"BLE  {item.name}",
                            detail=item.address,
                            identity=item,
                        )
                    )
            except TransportError:
                if self.scope == "ble":
                    raise

        candidates.sort(key=lambda item: (item.kind, item.label.lower(), item.detail.lower()))
        return candidates

    def make_transport(self, candidate: DeviceCandidate) -> Transport:
        if candidate.kind == "serial":
            if not isinstance(candidate.identity, SerialDeviceIdentity):
                raise TypeError("invalid serial device identity")
            return SerialTransport(identity=candidate.identity, baud=self.baud)

        if candidate.kind == "ble":
            from .transports.ble_nus import BleNusTransport

            return BleNusTransport(
                candidate.identity,
                scan_timeout=self.scan_seconds,
            )

        raise ValueError(f"unsupported candidate kind: {candidate.kind}")

    @staticmethod
    def _print_menu(candidates: list[DeviceCandidate]) -> None:
        print("Detected devices:")
        for index, candidate in enumerate(candidates, start=1):
            print(f"  {index}. {candidate.label}")
            print(f"     {candidate.detail}")

    def choose_from(
        self,
        candidates: list[DeviceCandidate],
        *,
        auto_single: bool,
        allow_cancel: bool,
    ) -> DeviceCandidate | None:
        if not candidates:
            return None

        if auto_single and len(candidates) == 1:
            candidate = candidates[0]
            print(f"Only one device is visible: {candidate.label}")
            print(f"  {candidate.detail}")
            return candidate

        self._print_menu(candidates)
        cancel_hint = ", Enter=cancel" if allow_cancel else ""

        while True:
            answer = input(
                f"Connect to [1-{len(candidates)}{cancel_hint}]: "
            ).strip()

            if allow_cancel and answer == "":
                return None

            try:
                index = int(answer)
            except ValueError:
                print("Please enter a device number.")
                continue

            if 1 <= index <= len(candidates):
                return candidates[index - 1]

            print("Device number is out of range.")

    def choose_initial(self, name_filter: str | None = None) -> DeviceCandidate:
        """Wait for a target. Multiple visible devices always require a menu."""
        while True:
            if self.scope in {"auto", "ble"}:
                print("Scanning USB/BLE devices..." if self.scope == "auto" else "Scanning BLE devices...")
            else:
                print("Scanning USB serial devices...")

            candidates = self.discover()
            if name_filter is not None:
                wanted = name_filter.lower()
                candidates = [
                    item
                    for item in candidates
                    if item.kind == "ble"
                    and getattr(item.identity, "name", "").lower() == wanted
                ]

            if not candidates:
                print("No matching devices found; scanning again... (Ctrl+C to exit)")
                time.sleep(0.5)
                continue

            selected = self.choose_from(
                candidates,
                auto_single=True,
                allow_cancel=False,
            )
            assert selected is not None
            return selected

    def choose_transport_menu(self) -> Transport | None:
        """Explicit hotkey menu: always show choices and allow Enter to cancel."""
        print("\nScanning devices for target selection...")
        candidates = self.discover()
        if not candidates:
            print("No devices are currently visible.")
            return None

        selected = self.choose_from(
            candidates,
            auto_single=False,
            allow_cancel=True,
        )
        if selected is None:
            return None
        return self.make_transport(selected)


def _serial_parser(prog: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        description="Line-oriented Serial Port terminal",
    )
    parser.add_argument(
        "device",
        nargs="?",
        default=None,
        help="Serial device; if omitted, discover and choose",
    )
    parser.add_argument("-b", "--baud", type=int, default=115200)
    parser.add_argument(
        "-l",
        "--list",
        action="store_true",
        help="List detected serial devices and exit",
    )
    parser.add_argument("--log", default="serialterminal.log")
    parser.add_argument(
        "--eol",
        choices=("lf", "crlf", "cr"),
        default="lf",
    )
    return parser


def _ble_parser(prog: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        description="Nordic UART Service terminal for LoRa-* BLE devices",
    )
    parser.add_argument(
        "target",
        nargs="?",
        default=None,
        help="optional advertised name; p/r aliases remain supported",
    )
    parser.add_argument("--log", default=None)
    parser.add_argument(
        "--eol",
        choices=("lf", "crlf", "cr"),
        default="lf",
    )
    parser.add_argument(
        "--scan-seconds",
        type=float,
        default=3.0,
    )
    return parser


def _auto_parser(prog: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        description=(
            "Unified USB/BLE terminal. One visible device auto-connects; "
            "multiple devices require numbered selection."
        ),
    )
    parser.add_argument(
        "device",
        nargs="?",
        default=None,
        help="legacy explicit serial path; omit for unified USB/BLE discovery",
    )
    parser.add_argument("-b", "--baud", type=int, default=115200)
    parser.add_argument("--log", default="serialterminal.log")
    parser.add_argument(
        "--eol",
        choices=("lf", "crlf", "cr"),
        default="lf",
    )
    parser.add_argument(
        "--scan-seconds",
        type=float,
        default=3.0,
    )
    parser.add_argument(
        "-l",
        "--list",
        action="store_true",
        help="List visible USB/BLE devices and exit",
    )
    return parser


def _line_ending(name: str) -> str:
    return {"lf": "\n", "crlf": "\r\n", "cr": "\r"}[name]


def _run_session(
    transport: Transport,
    *,
    log_path: str,
    eol: str,
    selector: DeviceSelector,
    reconnect_delay: float = 0.5,
) -> int:
    print(f"Locked target: {transport.description}")
    print("After disconnect/reboot only this selected device will be retried.\n")

    TerminalSession(
        transport=transport,
        log_path=log_path,
        line_ending=_line_ending(eol),
        reconnect_delay=reconnect_delay,
        device_chooser=selector.choose_transport_menu,
    ).run()
    return 0


def _run_serial(argv: list[str], prog: str) -> int:
    args = _serial_parser(prog).parse_args(argv)

    if args.list:
        devices = discover_serial_devices()
        if not devices:
            print("No serial devices found.")
            return 1
        for index, item in enumerate(devices, start=1):
            print(f"{index}. {item.path}  {item.description}")
        return 0

    selector = DeviceSelector("serial", baud=args.baud)

    if args.device is not None:
        transport = SerialTransport(device=args.device, baud=args.baud)
    else:
        candidate = selector.choose_initial()
        transport = selector.make_transport(candidate)

    return _run_session(
        transport,
        log_path=args.log,
        eol=args.eol,
        selector=selector,
    )


def _run_ble(argv: list[str], prog: str) -> int:
    parser = _ble_parser(prog)
    args = parser.parse_args(argv)

    try:
        from .transports.ble_nus import ble_log_slug, normalize_ble_target
    except Exception as exc:
        parser.error(str(exc))

    name_filter = None
    if args.target is not None:
        name_filter = normalize_ble_target(args.target)
        if name_filter is None:
            parser.error("unknown BLE target; use an advertised LoRa-* name or p/r")

    selector = DeviceSelector("ble", scan_seconds=args.scan_seconds)
    try:
        candidate = selector.choose_initial(name_filter=name_filter)
        transport = selector.make_transport(candidate)
    except TransportError as exc:
        parser.error(str(exc))

    log_path = args.log
    if log_path is None:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        log_path = f"nus-{ble_log_slug(candidate.identity.name)}-{stamp}.log"

    return _run_session(
        transport,
        log_path=log_path,
        eol=args.eol,
        selector=selector,
        reconnect_delay=1.0,
    )


def _run_auto(argv: list[str], prog: str) -> int:
    args = _auto_parser(prog).parse_args(argv)

    # Preserve the historical direct serial-path invocation.
    if args.device is not None:
        selector = DeviceSelector("serial", baud=args.baud)
        return _run_session(
            SerialTransport(device=args.device, baud=args.baud),
            log_path=args.log,
            eol=args.eol,
            selector=selector,
        )

    selector = DeviceSelector(
        "auto",
        baud=args.baud,
        scan_seconds=args.scan_seconds,
    )

    if args.list:
        candidates = selector.discover()
        if not candidates:
            print("No supported USB/BLE devices found.")
            return 1
        selector._print_menu(candidates)
        return 0

    candidate = selector.choose_initial()
    transport = selector.make_transport(candidate)
    return _run_session(
        transport,
        log_path=args.log,
        eol=args.eol,
        selector=selector,
    )


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)

    if args and args[0] == "ble":
        return _run_ble(args[1:], "serialterminal ble")

    if args and args[0] == "serial":
        return _run_serial(args[1:], "serialterminal serial")

    if args and args[0] == "auto":
        return _run_auto(args[1:], "serialterminal auto")

    # Default mode is now unified USB/BLE discovery. A legacy explicit serial
    # path still selects Serial directly.
    return _run_auto(args, "serialterminal")
