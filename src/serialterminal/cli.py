from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from typing import Any

from .device_cache import confirmed_devices
from .profiles import (
    GENERIC_PROFILE,
    PROFILE_NAMES,
    TerminalProfile,
    resolve_profile,
)
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
        profile: TerminalProfile = GENERIC_PROFILE,
    ):
        if scope not in {"auto", "serial", "ble", "spp"}:
            raise ValueError(f"unknown device selector scope: {scope}")
        self.scope = scope
        self.baud = baud
        self.scan_seconds = scan_seconds
        self.profile = profile
        self._known_candidates: dict[str, DeviceCandidate] = {}

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

    def _remember_candidates(
        self,
        candidates: list[DeviceCandidate],
    ) -> None:
        # BLE/SPP discovery дорогой, поэтому уже найденные physical identities
        # живут в selector до конца процесса и доступны F2 без нового scan.
        for candidate in candidates:
            if candidate.kind in {"ble", "spp"}:
                self._known_candidates[candidate.key] = candidate

    def _cached_ble_candidates(self) -> list[DeviceCandidate]:
        from .transports.ble_nus import BleDeviceIdentity

        result: list[DeviceCandidate] = []
        for record in confirmed_devices("ble", "nus"):
            address = record.get("address")
            if not isinstance(address, str) or not address:
                continue
            name = record.get("name")
            identity = BleDeviceIdentity(
                str(name or "<unnamed>"),
                address,
            )
            result.append(
                DeviceCandidate(
                    kind="ble",
                    key=identity.key,
                    label=f"BLE  {identity.name}",
                    detail=identity.address,
                    identity=identity,
                )
            )
        return result

    def _cached_spp_candidates(self) -> list[DeviceCandidate]:
        from .transports.bluetooth_spp import SppDeviceIdentity

        result: list[DeviceCandidate] = []
        for record in confirmed_devices("classic", "spp"):
            address = record.get("address")
            channel = record.get("metadata", {}).get("rfcomm_channel")
            if (
                not isinstance(address, str)
                or not address
                or not isinstance(channel, int)
                or channel <= 0
            ):
                continue
            identity = SppDeviceIdentity(
                str(record.get("name") or "<unnamed>"),
                address,
                channel,
            )
            result.append(
                DeviceCandidate(
                    kind="spp",
                    key=identity.key,
                    label=f"SPP  {identity.name}",
                    detail=(
                        f"{identity.address}  RFCOMM channel={identity.channel}"
                    ),
                    identity=identity,
                )
            )
        return result

    def known_candidates(self) -> list[DeviceCandidate]:
        """Return known terminal targets without active Bluetooth discovery."""
        by_key: dict[str, DeviceCandidate] = {}

        if self.scope in {"auto", "serial"}:
            for candidate in self._discover_serial_candidates():
                by_key[candidate.key] = candidate

        allowed = {
            "auto": {"ble", "spp"},
            "ble": {"ble"},
            "spp": {"spp"},
            "serial": set(),
        }[self.scope]
        for candidate in self._known_candidates.values():
            if candidate.kind in allowed:
                by_key[candidate.key] = candidate

        if "ble" in allowed:
            for candidate in self._cached_ble_candidates():
                by_key.setdefault(candidate.key, candidate)
        if "spp" in allowed:
            for candidate in self._cached_spp_candidates():
                by_key.setdefault(candidate.key, candidate)

        result = list(by_key.values())
        result.sort(key=self._candidate_sort_key)
        return result

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
        self._remember_candidates(candidates)
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
        self._remember_candidates([candidate])

        if candidate.kind == "serial":
            if not isinstance(candidate.identity, SerialDeviceIdentity):
                raise TypeError("invalid serial device identity")
            return SerialTransport(
                identity=candidate.identity,
                baud=self.baud,
            )

        if candidate.kind == "ble":
            from .transports.ble_nus import BleNusTransport, BleReceiveStream

            config = self.profile.ble_config()
            if config is None:
                raise ValueError(
                    f"profile {self.profile.name!r} has no BLE configuration"
                )
            receive_streams = tuple(
                BleReceiveStream(item.uuid, item.stream, item.required)
                for item in config.receive_streams
            )
            return BleNusTransport(
                candidate.identity,
                scan_timeout=self.scan_seconds,
                write_characteristic=config.write_characteristic,
                receive_streams=receive_streams,
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

    def recreate_transport(
        self,
        transport: Transport,
        profile: TerminalProfile,
    ) -> Transport:
        """Build the same physical target with another controller profile."""
        builder = DeviceSelector(
            self.scope,
            baud=self.baud,
            scan_seconds=self.scan_seconds,
            profile=profile,
        )

        if isinstance(transport, SerialTransport):
            if transport.identity is not None:
                return SerialTransport(
                    identity=transport.identity,
                    baud=transport.baud,
                )
            return SerialTransport(
                device=transport.requested_device,
                baud=transport.baud,
            )

        from .transports.ble_nus import BleDeviceIdentity, BleNusTransport
        if isinstance(transport, BleNusTransport):
            if transport.target_address is None:
                raise TransportError(
                    "cannot switch profile before BLE physical identity is known"
                )
            identity = BleDeviceIdentity(
                transport.target_name,
                transport.target_address,
            )
            return builder.make_transport(
                DeviceCandidate(
                    kind="ble",
                    key=identity.key,
                    label=f"BLE  {identity.name}",
                    detail=identity.address,
                    identity=identity,
                )
            )

        from .transports.bluetooth_spp import BluetoothSppTransport
        if isinstance(transport, BluetoothSppTransport):
            identity = transport.identity
            return builder.make_transport(
                DeviceCandidate(
                    kind="spp",
                    key=identity.key,
                    label=f"SPP  {identity.name}",
                    detail=(
                        f"{identity.address}  RFCOMM channel={identity.channel}"
                    ),
                    identity=identity,
                )
            )

        raise TransportError(
            f"profile switching is unsupported for {type(transport).__name__}"
        )

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
        """Explicit hotkey menu over already known targets; no Bluetooth scan."""
        print("\nKnown devices for target selection:")
        candidates = self.known_candidates()
        if not candidates:
            print(
                "No known devices. Use the Bluetooth scanner to discover "
                "new targets first."
            )
            return None

        selected = self.choose_from(
            candidates,
            auto_single=False,
            allow_cancel=True,
        )
        if selected is None:
            return None
        return self.make_transport(selected)


def _add_profile_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--profile",
        choices=PROFILE_NAMES,
        default="generic",
        help="controller convenience profile; default: generic",
    )
    parser.add_argument(
        "--classic",
        action="store_true",
        help="use the legacy line-oriented human frontend instead of the TUI",
    )
    parser.add_argument(
        "--receive-dir",
        default=None,
        help="directory for verified incoming files in the TUI",
    )
    parser.add_argument(
        "--log-base64",
        action="store_true",
        help="include raw base64 payloads in log files (default: redact)",
    )


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
    _add_profile_argument(parser)
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
        help="optional exact advertised name",
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
    _add_profile_argument(parser)
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
    _add_profile_argument(parser)
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
    parser.add_argument(
        "--receive-dir",
        default=None,
        help="directory for verified incoming files",
    )
    parser.add_argument(
        "--log-base64",
        action="store_true",
        help="include raw base64 payloads in log files (default: redact)",
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
    _add_profile_argument(parser)
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
    profile: TerminalProfile = GENERIC_PROFILE,
    classic: bool = False,
    receive_dir: str | None = None,
    log_base64: bool = False,
) -> int:
    actual_log_path = str(default_log_path()) if log_path is None else log_path
    print(f"Locked target: {transport.description}")
    print(
        "After disconnect/reboot only this selected device "
        "will be retried.\n"
    )

    if not classic and sys.stdin.isatty() and sys.stdout.isatty():
        from .tui import run_terminal_tui

        return run_terminal_tui(
            transport=transport,
            log_path=actual_log_path,
            line_ending=_line_ending(eol),
            reconnect_delay=reconnect_delay,
            selector=selector,
            profile=profile,
            receive_dir=receive_dir,
            log_base64=log_base64,
        )

    TerminalSession(
        transport=transport,
        log_path=actual_log_path,
        line_ending=_line_ending(eol),
        reconnect_delay=reconnect_delay,
        device_chooser=selector.choose_transport_menu,
        profile=profile,
        log_base64=log_base64,
    ).run()
    return 0


def _run_serial(argv: list[str], prog: str) -> int:
    args = _serial_parser(prog).parse_args(argv)
    profile = resolve_profile(args.profile)

    if args.list:
        devices = discover_serial_devices()
        if not devices:
            print("No serial devices found.")
            return 1
        for index, item in enumerate(devices, start=1):
            print(f"{index}. {item.path}  {item.description}")
        return 0

    selector = DeviceSelector("serial", baud=args.baud, profile=profile)
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
        profile=profile,
        classic=args.classic,
        receive_dir=args.receive_dir,
        log_base64=args.log_base64,
    )


def _run_ble(argv: list[str], prog: str) -> int:
    parser = _ble_parser(prog)
    args = parser.parse_args(argv)
    profile = resolve_profile(args.profile)

    selector = DeviceSelector(
        "ble",
        scan_seconds=args.scan_seconds,
        profile=profile,
    )
    try:
        candidate = selector.choose_initial(name_filter=args.target)
        transport = selector.make_transport(candidate)
    except TransportError as exc:
        parser.error(str(exc))

    return _run_session(
        transport,
        log_path=args.log,
        eol=args.eol,
        selector=selector,
        reconnect_delay=1.0,
        profile=profile,
        classic=args.classic,
        receive_dir=args.receive_dir,
        log_base64=args.log_base64,
    )


def _run_spp(argv: list[str], prog: str) -> int:
    parser = _spp_parser(prog)
    args = parser.parse_args(argv)
    profile = resolve_profile(args.profile)
    selector = DeviceSelector(
        "spp",
        scan_seconds=args.scan_seconds,
        profile=profile,
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
        profile=profile,
        classic=args.classic,
        receive_dir=args.receive_dir,
        log_base64=args.log_base64,
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

    return run_agent(
        log_path=args.log,
        receive_dir=args.receive_dir,
        log_base64=args.log_base64,
    )


def _run_auto(argv: list[str], prog: str) -> int:
    args = _auto_parser(prog).parse_args(argv)
    profile = resolve_profile(args.profile)

    if args.device is not None:
        selector = DeviceSelector(
            "serial",
            baud=args.baud,
            profile=profile,
        )
        return _run_session(
            SerialTransport(
                device=args.device,
                baud=args.baud,
            ),
            log_path=args.log,
            eol=args.eol,
            selector=selector,
            profile=profile,
            classic=args.classic,
            receive_dir=args.receive_dir,
            log_base64=args.log_base64,
        )

    selector = DeviceSelector(
        "auto",
        baud=args.baud,
        scan_seconds=args.scan_seconds,
        profile=profile,
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
        profile=profile,
        classic=args.classic,
        receive_dir=args.receive_dir,
        log_base64=args.log_base64,
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
