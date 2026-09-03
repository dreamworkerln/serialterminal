from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from typing import Any

from .runlog import default_log_path
from .startup_controls import InitialControlReader
from .terminal import TerminalSession
from .transports.base import Transport, TransportError
from .transports.serial import (
    SerialDeviceIdentity,
    SerialTransport,
    discover_serial_devices,
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

    @staticmethod
    def _serial_candidate(item: SerialDeviceIdentity) -> DeviceCandidate:
        meta: list[str] = [item.path]
        if item.vid is not None and item.pid is not None:
            meta.append(f"VID:PID={item.vid:04X}:{item.pid:04X}")
        if item.serial_number:
            meta.append(f"serial={item.serial_number}")
        if item.location:
            meta.append(f"location={item.location}")

        port_kind = "USB" if item.is_usb else "SERIAL"
        return DeviceCandidate(
            kind="serial",
            key=item.key,
            label=f"{port_kind}  {item.label}",
            detail="  ".join(meta),
            identity=item,
        )

    def _discover_serial_candidates(self) -> list[DeviceCandidate]:
        return [
            self._serial_candidate(item)
            for item in discover_serial_devices()
        ]

    def _discover_ble_candidates(self) -> list[DeviceCandidate]:
        try:
            from .ble_discovery import discover_terminal_ble_devices

            return [
                DeviceCandidate(
                    kind="ble",
                    key=item.key,
                    label=f"BLE  {item.name}",
                    detail=item.address,
                    identity=item,
                )
                for item in discover_terminal_ble_devices(self.scan_seconds)
            ]
        except TransportError:
            if self.scope == "ble":
                raise
            return []

    def _discover_spp_candidates(self) -> list[DeviceCandidate]:
        try:
            from .transports.bluetooth_spp import discover_spp_devices

            return [
                DeviceCandidate(
                    kind="spp",
                    key=item.key,
                    label=f"SPP  {item.name}",
                    detail=f"{item.address}  RFCOMM channel={item.channel}",
                    identity=item,
                )
                for item in discover_spp_devices(self.scan_seconds)
            ]
        except TransportError:
            if self.scope == "spp":
                raise
            return []

    @staticmethod
    def _candidate_sort_key(candidate: DeviceCandidate) -> tuple[int, str, str]:
        kind_order = {"serial": 0, "ble": 1, "spp": 2}
        return (
            kind_order.get(candidate.kind, 99),
            candidate.label.lower(),
            candidate.detail.lower(),
        )

    def discover(self) -> list[DeviceCandidate]:
        candidates: list[DeviceCandidate] = []

        if self.scope in {"auto", "serial"}:
            candidates.extend(self._discover_serial_candidates())
        if self.scope in {"auto", "ble"}:
            candidates.extend(self._discover_ble_candidates())
        if self.scope in {"auto", "spp"}:
            candidates.extend(self._discover_spp_candidates())

        candidates.sort(key=self._candidate_sort_key)
        return candidates

    @staticmethod
    def _run_initial_scanner() -> None:
        try:
            from .bluetooth_scanner import run_interactive_scanner

            run_interactive_scanner()
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            print(f"\n[Bluetooth scanner failed: {exc}]\n")

    def _handle_initial_control(self, control: str | None) -> bool:
        if control != "scanner":
            return False
        self._run_initial_scanner()
        return True

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

    @staticmethod
    def _read_single_key_choice(
        prompt_text: str,
        candidate_count: int,
        allow_cancel: bool,
    ) -> str:
        """Read a 1..9 menu choice immediately on an interactive POSIX TTY."""
        if not sys.stdin.isatty():
            return input(prompt_text).strip()

        try:
            import termios
            import tty
        except ImportError:
            return input(prompt_text).strip()

        valid_keys = {str(index) for index in range(1, candidate_count + 1)}
        fd = sys.stdin.fileno()
        previous = termios.tcgetattr(fd)
        print(prompt_text, end="", flush=True)

        try:
            tty.setcbreak(fd)
            while True:
                key = sys.stdin.read(1)

                if key in valid_keys:
                    print(key)
                    return key

                if key in {"\r", "\n"}:
                    if allow_cancel:
                        print()
                        return ""
                    print("\a", end="", flush=True)
                    continue

                if key == "\x03":
                    raise KeyboardInterrupt

                print("\a", end="", flush=True)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, previous)

    def _read_menu_answer(
        self,
        prompt_text: str,
        candidate_count: int,
        allow_cancel: bool,
    ) -> str:
        if candidate_count < 10:
            return self._read_single_key_choice(
                prompt_text,
                candidate_count,
                allow_cancel,
            )
        return input(prompt_text).strip()

    @staticmethod
    def _parse_candidate_index(answer: str, candidate_count: int) -> int | None:
        try:
            index = int(answer)
        except ValueError:
            print("Please enter a device number.")
            return None

        if not 1 <= index <= candidate_count:
            print("Device number is out of range.")
            return None
        return index - 1

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
        prompt_text = f"Connect to [1-{len(candidates)}{cancel_hint}]: "

        while True:
            answer = self._read_menu_answer(
                prompt_text,
                len(candidates),
                allow_cancel,
            )
            if allow_cancel and answer == "":
                return None

            index = self._parse_candidate_index(answer, len(candidates))
            if index is not None:
                return candidates[index]

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

            with InitialControlReader() as controls:
                candidates = self.discover()
                control = controls.read(0.0)
            if self._handle_initial_control(control):
                continue

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
                    "(Ctrl+T s scanner, Ctrl+C exit)"
                )
                with InitialControlReader() as controls:
                    control = controls.read(0.5)
                self._handle_initial_control(control)
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
    parser.add_argument("--log", default=None)
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


def _agent_parser(prog: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        description="Machine-facing JSON Lines interface over SerialTerminal sessions",
    )
    parser.add_argument(
        "--log",
        default=None,
        help="explicit log path; default creates a unique logs/serialterminal-*.log",
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
    log_path: str | None,
    eol: str,
    selector: DeviceSelector,
    reconnect_delay: float = 0.5,
) -> int:
    actual_log_path = str(default_log_path()) if log_path is None else log_path
    print(f"Locked target: {transport.description}")
    print(
        "After disconnect/reboot only this selected device "
        "will be retried.\n"
    )

    TerminalSession(
        transport=transport,
        log_path=actual_log_path,
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
        from .transports.ble_nus import normalize_ble_target
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

    return _run_session(
        transport,
        log_path=args.log,
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


def _run_agent(argv: list[str], prog: str) -> int:
    args = _agent_parser(prog).parse_args(argv)
    from .agent import run_agent

    return run_agent(log_path=args.log)


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

    if args and args[0] == "agent":
        return _run_agent(args[1:], "serialterminal agent")

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
