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
    """Discover terminal-capable devices and create sticky transports."""

    def __init__(
        self,
        scope: str,
        baud: int = 115200,
        scan_seconds: float = 3.0,
    ):
        if scope not in {"auto", "serial", "ble", "spp"}:
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

                port_kind = "USB" if item.is_usb else "SERIAL"
                candidates.append(
                    DeviceCandidate(
                        kind="serial",
                        key=item.key,
                        label=f"{port_kind}  {item.label}",
                        detail="  ".join(meta),
                        identity=item,
                    )
                )

        if self.scope in {"auto", "ble"}:
            try:
                from .ble_discovery import discover_terminal_ble_devices

                for item in discover_terminal_ble_devices(
                    self.scan_seconds
                ):
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

        if self.scope in {"auto", "spp"}:
            try:
                from .transports.bluetooth_spp import discover_spp_devices

                for item in discover_spp_devices(self.scan_seconds):
                    candidates.append(
                        DeviceCandidate(
                            kind="spp",
                            key=item.key,
                            label=f"SPP  {item.name}",
                            detail=(
                                f"{item.address}  "
                                f"RFCOMM channel={item.channel}"
                            ),
                            identity=item,
                        )
                    )
            except TransportError:
                if self.scope == "spp":
                    raise

        kind_order = {"serial": 0, "ble": 1, "spp": 2}
        candidates.sort(
            key=lambda item: (
                kind_order.get(item.kind, 99),
                item.label.lower(),
                item.detail.lower(),
            )
        )
        return candidates

    def make_transport(self, candidate: DeviceCandidate) -> Transport:
        if candidate.kind == "serial":
            if not isinstance(candidate.identity, SerialDeviceIdentity):
                raise TypeError("invalid serial device identity")
            return SerialTransport(
                identity=candidate.identity,
                baud=self.baud,
            )

        if candidate.kind == "ble":
            from .transports.ble_nus import BleNusTransport

            return BleNusTransport(
                candidate.identity,
                scan_timeout=self.scan_seconds,
            )

        if candidate.kind == "spp":
            from .transports.bluetooth_spp import (
                BluetoothSppTransport,
                SppDeviceIdentity,
            )

            if not isinstance(candidate.identity, SppDeviceIdentity):
                raise TypeError("invalid SPP device identity")
            return BluetoothSppTransport(candidate.identity)

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

    def choose_initial(
        self,
        name_filter: str | None = None,
    ) -> DeviceCandidate:
        """Wait for a target. Multiple visible devices require a menu."""
        while True:
            if self.scope == "auto":
                print("Scanning Serial/BLE/SPP devices...")
            elif self.scope == "ble":
                print("Scanning BLE devices...")
            elif self.scope == "spp":
                print(
                    "Scanning cached/confirmed Bluetooth SPP devices..."
                )
            else:
                print("Scanning serial devices...")

            candidates = self.discover()
            if name_filter is not None:
                wanted = name_filter.lower()
                candidates = [
                    item
                    for item in candidates
                    if item.kind == "ble"
                    and getattr(
                        item.identity,
                        "name",
                        "",
                    ).lower()
                    == wanted
                ]

            if not candidates:
                print(
                    "No matching devices found; scanning again... "
                    "(Ctrl+C to exit)"
                )
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
        """Explicit hotkey menu: always show choices and allow cancel."""
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
        description="Nordic UART Service terminal",
    )
    parser.add_argument(
        "target",
        nargs="?",
        default=None,
        help=(
            "optional exact advertised name; p/r aliases remain supported"
        ),
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


def _spp_parser(prog: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        description="Classic Bluetooth Serial Port Profile terminal",
    )
    parser.add_argument("--log", default="serialterminal-spp.log")
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


def _scan_parser(prog: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        description="Aggressive Bluetooth capability scanner/prober",
    )
    parser.add_argument(
        "mode",
        nargs="?",
        choices=("ble", "spp", "all"),
        default=None,
    )
    parser.add_argument(
        "--scan-seconds",
        type=float,
        default=5.0,
    )
    parser.add_argument(
        "--probe-timeout",
        type=float,
        default=8.0,
    )
    parser.add_argument(
        "--no-rfcomm-test",
        action="store_true",
        help=(
            "detect SPP by SDP but do not open a test RFCOMM connection"
        ),
    )
    return parser


def _auto_parser(prog: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        description=(
            "Unified Serial/BLE/SPP terminal. One visible device "
            "auto-connects; multiple devices require numbered selection."
        ),
    )
    parser.add_argument(
        "device",
        nargs="?",
        default=None,
        help=(
            "legacy explicit serial path; omit for unified discovery"
        ),
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
        help="List visible terminal-capable devices and exit",
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
    print(
        "After disconnect/reboot only this selected device "
        "will be retried.\n"
    )

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
        transport = SerialTransport(
            device=args.device,
            baud=args.baud,
        )
    else:
        transport = selector.make_transport(selector.choose_initial())

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
        from .transports.ble_nus import (
            ble_log_slug,
            normalize_ble_target,
        )
    except Exception as exc:
        parser.error(str(exc))

    name_filter = None
    if args.target is not None:
        # Preserve p/r aliases, but arbitrary exact advertised names are valid.
        name_filter = normalize_ble_target(args.target) or args.target

    selector = DeviceSelector(
        "ble",
        scan_seconds=args.scan_seconds,
    )
    try:
        candidate = selector.choose_initial(name_filter=name_filter)
        transport = selector.make_transport(candidate)
    except TransportError as exc:
        parser.error(str(exc))

    log_path = args.log
    if log_path is None:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        log_path = (
            f"nus-{ble_log_slug(candidate.identity.name)}-{stamp}.log"
        )

    return _run_session(
        transport,
        log_path=log_path,
        eol=args.eol,
        selector=selector,
        reconnect_delay=1.0,
    )


def _run_spp(argv: list[str], prog: str) -> int:
    parser = _spp_parser(prog)
    args = parser.parse_args(argv)
    selector = DeviceSelector(
        "spp",
        scan_seconds=args.scan_seconds,
    )

    try:
        candidate = selector.choose_initial()
        transport = selector.make_transport(candidate)
    except TransportError as exc:
        parser.error(str(exc))

    return _run_session(
        transport,
        log_path=args.log,
        eol=args.eol,
        selector=selector,
        reconnect_delay=1.0,
    )


def _choose_scan_mode() -> str:
    print("Bluetooth scanner")
    print("  1. Probe all BLE devices for NUS")
    print("  2. Probe Classic Bluetooth devices for SPP")
    print("  3. Probe all Bluetooth")

    mapping = {
        "1": "ble",
        "ble": "ble",
        "2": "spp",
        "spp": "spp",
        "3": "all",
        "all": "all",
    }
    while True:
        answer = input("Scan [1-3]: ").strip().lower()
        if answer in mapping:
            return mapping[answer]
        print("Please enter 1, 2 or 3.")


def _run_scan(argv: list[str], prog: str) -> int:
    parser = _scan_parser(prog)
    args = parser.parse_args(argv)
    mode = args.mode

    try:
        if mode is None:
            mode = _choose_scan_mode()

        from .bluetooth_scanner import run_scanner

        run_scanner(
            mode,
            scan_seconds=args.scan_seconds,
            probe_timeout=args.probe_timeout,
            connect_test=not args.no_rfcomm_test,
        )
        return 0
    except KeyboardInterrupt:
        print("\nScanner stopped.")
        return 130
    except TransportError as exc:
        parser.error(str(exc))


def _run_auto(argv: list[str], prog: str) -> int:
    args = _auto_parser(prog).parse_args(argv)

    if args.device is not None:
        selector = DeviceSelector("serial", baud=args.baud)
        return _run_session(
            SerialTransport(
                device=args.device,
                baud=args.baud,
            ),
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
            print("No supported Serial/BLE/SPP devices found.")
            return 1
        selector._print_menu(candidates)
        return 0

    transport = selector.make_transport(selector.choose_initial())
    return _run_session(
        transport,
        log_path=args.log,
        eol=args.eol,
        selector=selector,
    )


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)

    if args and args[0] == "scan":
        return _run_scan(args[1:], "serialterminal scan")

    if args and args[0] == "ble":
        return _run_ble(args[1:], "serialterminal ble")

    if args and args[0] == "spp":
        return _run_spp(args[1:], "serialterminal spp")

    if args and args[0] == "serial":
        return _run_serial(args[1:], "serialterminal serial")

    if args and args[0] == "auto":
        return _run_auto(args[1:], "serialterminal auto")

    return _run_auto(args, "serialterminal")
